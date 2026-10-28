import json
from pathlib import Path
import secrets
import sqlite3

import pytest

from app.db import database, now
from app.recovery import RecoveryError, create, restore, verify
from tests.test_recovery import fixture


def identify(path, company='atlas'):
    with database(path) as db:
        value = {'company_id': company, 'service_id': 1, 'fingerprint': 'isolated-test',
                 'configured': True, 'enabled': True, 'updated_at': now(), 'last_sample': ''}
        db.execute("INSERT OR REPLACE INTO settings VALUES('enterprise_monitoring_binding',?)", (json.dumps(value),))


def test_customer_archive_identity_restore_and_live_state_preservation(fixture, tmp_path):
    source, key = fixture
    identify(source)
    archive, manifest = create(source, key, 'atlas')
    assert manifest['installation_id'] == 'atlas'
    assert verify(archive, key, 'atlas')['verified'] is True
    assert b'installation_id' not in archive and b'atlas' not in archive
    target = tmp_path / 'isolated-restore'
    report = restore(archive, key, target, 'atlas')
    assert report['sessions_revoked'] and report['monitoring_paused']
    with database(target / 'nexo.db') as db:
        assert db.execute('SELECT count(*) FROM sessions').fetchone()[0] == 0
        binding = json.loads(db.execute("SELECT value FROM settings WHERE key='enterprise_monitoring_binding'").fetchone()[0])
        assert binding['company_id'] == 'atlas' and binding['enabled'] is False
    with database(source) as db:
        assert db.execute('SELECT count(*) FROM sessions').fetchone()[0] == 1
        assert json.loads(db.execute("SELECT value FROM settings WHERE key='enterprise_monitoring_binding'").fetchone()[0])['enabled'] is True
    with pytest.raises(RecoveryError):
        restore(archive, key, target, 'atlas')


def test_wrong_company_or_key_cannot_restore_even_in_new_destination(fixture, tmp_path):
    source, key = fixture
    identify(source)
    archive, _ = create(source, key, 'atlas')
    for company, candidate_key in [('boreal', key), ('atlas', secrets.token_bytes(32))]:
        destination = tmp_path / company
        with pytest.raises(RecoveryError):
            verify(archive, candidate_key, company)
        with pytest.raises(RecoveryError):
            restore(archive, candidate_key, destination, company)
        assert not destination.exists()
    with pytest.raises(RecoveryError):
        create(source, key, 'boreal')


def test_missing_or_legacy_identity_requires_explicit_customer_archive(fixture):
    source, key = fixture
    with pytest.raises(RecoveryError):
        create(source, key, 'atlas')
    identify(source)
    legacy, manifest = create(source, key)
    assert 'installation_id' not in manifest
    assert verify(legacy, key)['verified'] is True
    with pytest.raises(RecoveryError):
        verify(legacy, key, 'atlas')


@pytest.mark.parametrize('company', ['../atlas', '', 'Atlas', 'a' * 25, True])
def test_customer_identity_is_bounded_before_archive_creation(fixture, company):
    source, key = fixture
    identify(source)
    with pytest.raises(RecoveryError):
        create(source, key, company)


def test_archive_manifest_and_database_identity_must_both_match(fixture, tmp_path):
    from app import recovery
    import struct
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    source, key = fixture
    identify(source)
    archive, _ = create(source, key, 'atlas')
    raw, manifest = recovery.decode(archive, key)
    # A fixture signed with the test key simulates erroneous producer metadata.
    manifest['installation_id'] = 'boreal'
    metadata = json.dumps(manifest).encode()
    nonce = secrets.token_bytes(12)
    inconsistent = recovery.MAGIC + nonce + AESGCM(key).encrypt(nonce, struct.pack('!I',len(metadata)) + metadata + raw, recovery.MAGIC)
    with pytest.raises(RecoveryError):
        verify(inconsistent, key, 'boreal')
    with pytest.raises(RecoveryError):
        restore(inconsistent, key, tmp_path / 'wrong-owner', 'boreal')
    assert not (tmp_path / 'wrong-owner').exists()


def test_portable_customer_key_requires_matching_owner(fixture,tmp_path):
    from app import portable
    source,key=fixture
    identify(source)
    archive,_=create(source,key,'atlas')
    phrase='Frase apenas para o ensaio isolado 2026!'
    with pytest.raises(RecoveryError):
        portable.export(archive,key,phrase,'boreal')
    blob,report=portable.export(archive,key,phrase,'atlas')
    assert report['installation_id']=='atlas'
    recovered_key=portable.unwrap(blob,phrase)
    restored=restore(archive,recovered_key,tmp_path/'portable-customer','atlas')
    assert restored['restored'] and restored['sessions_revoked']
