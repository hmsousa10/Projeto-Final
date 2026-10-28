from contextlib import closing
import json
import sqlite3

import pytest

from app import recovery
from app.db import database
from app.maintenance import Maintenance, blocks_writes, fingerprint, require_ready
from tests.test_customer_recovery import identify
from tests.test_recovery import fixture


@pytest.fixture
def customer(fixture, tmp_path):
    source, key = fixture
    identify(source)
    root = tmp_path / 'customer'; root.mkdir()
    live = root / 'nexo.db'
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(live)) as dst:
        src.backup(dst)
    with database(source) as db:
        db.execute("UPDATE services SET description='Candidate customer snapshot' WHERE id=1")
    archive, _ = recovery.create(source, key, 'atlas')
    original = fingerprint(live)['history_sha256']
    manager = Maintenance(root, 'atlas')
    manager.stage(archive, key)
    return manager, original, archive, key, source


def test_customer_promotion_verification_and_rollback_pause_collection(customer):
    manager, original, _, _, _ = customer
    state = manager.promote()
    assert state['company_id'] == 'atlas' and blocks_writes(manager.live)
    assert fingerprint(manager.live)['history_sha256'] != original
    manager = Maintenance(manager.root, 'atlas')  # Another CLI process uses the bound journal.
    manager.verify()
    assert not blocks_writes(manager.live)
    manager.commit()
    manager.rollback()
    assert manager.check()['generation_audit_verified']
    assert fingerprint(manager.live)['history_sha256'] == original
    with database(manager.live) as db:
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM telemetry_targets WHERE enabled=1').fetchone()[0] == 0
        value = json.loads(db.execute("SELECT value FROM settings WHERE key='enterprise_monitoring_binding'").fetchone()[0])
        assert value['company_id'] == 'atlas' and value['enabled'] is False
    assert list(manager.generation(manager.state()).glob('before-rollback-*.db'))


def test_customer_journal_requires_matching_explicit_identity(customer):
    manager, original, _, _, _ = customer
    with pytest.raises(recovery.RecoveryError):
        Maintenance(manager.root, 'boreal')
    generic = Maintenance(manager.root)
    with pytest.raises(recovery.RecoveryError, match='diário'):
        generic.promote()
    assert fingerprint(manager.live)['history_sha256'] == original
    assert manager.state()['phase'] == 'staged'


def test_other_company_archive_is_rejected_before_switch(customer):
    manager, original, _, key, source = customer
    manager.rollback()
    identify(source, 'boreal')
    wrong, _ = recovery.create(source, key, 'boreal')
    with pytest.raises(recovery.RecoveryError):
        manager.stage(wrong, key)
    assert manager.state()['phase'] == 'cancelled'
    assert fingerprint(manager.live)['history_sha256'] == original


def test_live_company_change_after_stage_is_rejected_before_switch(customer):
    manager, original, _, _, _ = customer
    identify(manager.live, 'boreal')
    with pytest.raises(recovery.RecoveryError):
        manager.promote()
    assert manager.state()['phase'] == 'staged'
    assert fingerprint(manager.live)['history_sha256'] == original


def test_interrupted_customer_switch_recovers_from_bound_checkpoint(customer, monkeypatch):
    manager, original, _, _, _ = customer
    save = manager.save

    def interrupted(state, phase):
        if phase == 'promoted':
            raise OSError('Disposable interruption fixture')
        return save(state, phase)

    monkeypatch.setattr(manager, 'save', interrupted)
    with pytest.raises(OSError):
        manager.promote()
    assert manager.state()['phase'] == 'switching'
    with pytest.raises(RuntimeError):
        require_ready(manager.live)
    manager.rollback()
    require_ready(manager.live)
    assert fingerprint(manager.live)['history_sha256'] == original
    assert manager.check()['tables']['sessions'] == 0
