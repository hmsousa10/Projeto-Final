from contextlib import closing
import json
from pathlib import Path
import secrets
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import recovery, slo
from app.db import database, initialize
from app.knowledge import Knowledge
from app.main import create_app
from app.maintenance import Maintenance, blocks_writes, fingerprint, require_ready, write_json
from app.seed import seed


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    for name in ('PROMETHEUS_URL', 'SEMANTIC_URL', 'LOKI_URL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('LAB_MODE', '0')
    monkeypatch.setenv('DEMO_PASSWORD', 'EstudoLocal2026!')
    monkeypatch.setenv('MONITORING_ALLOWED_URLS', json.dumps(['http://portal-lab:8080/health']))
    root = tmp_path / 'data'; root.mkdir()
    live = root / 'nexo.db'
    initialize(live); seed(live); Knowledge(str(live)).initialize(); slo.initialize_policies(live)
    with database(live) as db:
        db.execute("INSERT INTO sessions VALUES('old-session',1,'2099-01-01')")
        db.execute("INSERT INTO telemetry_targets(target_key,service_id,target_url,enabled) VALUES('active',1,'http://portal-lab:8080/health',1)")
        db.execute("INSERT INTO telemetry_targets(target_key,service_id,target_url,enabled) VALUES('paused',2,'http://api-lab:8080/health',0)")
    original = fingerprint(live)
    source = tmp_path / 'source.db'
    with closing(sqlite3.connect(live)) as src, closing(sqlite3.connect(source)) as dst:
        src.backup(dst)
        dst.execute("UPDATE incidents SET title='Candidate distinct case' WHERE id=1"); dst.commit()
    key = secrets.token_bytes(32)
    archive, _ = recovery.create(source, key)
    manager = Maintenance(root)
    manager.stage(archive, key)
    return manager, original, archive, key


def test_promotion_pause_write_barrier_verification_and_rollback(prepared):
    manager, original, _, _ = prepared
    assert fingerprint(manager.live)['history_sha256'] == original['history_sha256']
    state = manager.promote()
    assert state['phase'] == 'promoted' and blocks_writes(manager.live)
    result = manager.check()
    with database(manager.live) as db:
        assert db.execute("SELECT count(*) FROM audit WHERE action='maintenance.promoted'").fetchone()[0] == 1
    assert result['tables']['sessions'] == 0 and result['enabled_targets'] == 0
    assert fingerprint(manager.live)['history_sha256'] != original['history_sha256']
    with TestClient(create_app(manager.live, demo=True), base_url='http://localhost') as client:
        assert client.post('/api/login', json={'email':'admin@local.test','password':'EstudoLocal2026!'}).status_code == 200
        body = {'service_id':1, 'title':'Validation request', 'description':'Meaningful validation case'}
        assert client.post('/api/incidents', json=body).status_code == 503
        manager.verify()
        assert client.post('/api/incidents', json=body).status_code == 201
    manager.rollback()
    with database(manager.live) as db:
        assert db.execute("SELECT count(*) FROM audit WHERE action='maintenance.rolled_back'").fetchone()[0] == 1
    assert not blocks_writes(manager.live)
    assert manager.check()['tables']['sessions'] == 0
    assert fingerprint(manager.live)['history_sha256'] == original['history_sha256']
    preserved = list(manager.generation(manager.state()).glob('before-rollback-*.db'))
    assert len(preserved) == 1
    assert fingerprint(preserved[0])['tables']['incidents'] == original['tables']['incidents'] + 1


def test_interruption_after_replace_blocks_startup_and_allows_recovery(prepared, monkeypatch):
    manager, original, _, _ = prepared
    save = manager.save
    def fail_final_save(state, phase):
        if phase == 'promoted':
            raise OSError('simulated power interruption')
        return save(state, phase)
    monkeypatch.setattr(manager, 'save', fail_final_save)
    with pytest.raises(OSError):
        manager.promote()
    assert manager.state()['phase'] == 'switching'
    assert blocks_writes(manager.live)
    with pytest.raises(RuntimeError, match='Manutenção incompleta'):
        require_ready(manager.live)
    manager.rollback()
    require_ready(manager.live)
    assert fingerprint(manager.live)['history_sha256'] == original['history_sha256']


@pytest.mark.parametrize('phase', ['prepared', 'switching', 'rolling_back', 'unknown'])
def test_pending_or_unknown_journal_refuses_startup(prepared, phase):
    manager, _, _, _ = prepared
    state = manager.state(); state['phase'] = phase
    write_json(manager.state_path, state)
    assert blocks_writes(manager.live)
    with pytest.raises(RuntimeError):
        require_ready(manager.live)


def test_tampered_candidate_never_overwrites_original(prepared):
    manager, original, _, _ = prepared
    candidate = manager.generation(manager.state()) / 'candidate/nexo.db'
    with candidate.open('ab') as stream:
        stream.write(b'tampered')
    with pytest.raises(recovery.RecoveryError, match='alterada'):
        manager.promote()
    assert fingerprint(manager.live)['history_sha256'] == original['history_sha256']


def test_tampered_rollback_refused_and_candidate_preserved(prepared):
    manager, _, _, _ = prepared
    manager.promote()
    candidate = fingerprint(manager.live)
    rollback = manager.generation(manager.state()) / 'rollback.db'
    with rollback.open('ab') as stream:
        stream.write(b'tampered')
    with pytest.raises(recovery.RecoveryError, match='alterado'):
        manager.rollback()
    assert fingerprint(manager.live)['history_sha256'] == candidate['history_sha256']


def test_existing_reader_prevents_offline_swap(prepared):
    manager, original, _, _ = prepared
    with closing(sqlite3.connect(manager.live)) as reader:
        reader.execute('PRAGMA journal_mode=WAL')
        reader.execute('BEGIN'); reader.execute('SELECT * FROM incidents').fetchone()
        with pytest.raises(sqlite3.OperationalError):
            manager.promote()
    assert manager.state()['phase'] == 'staged'
    assert fingerprint(manager.live)['history_sha256'] == original['history_sha256']


def test_resume_only_previously_active_approved_targets(prepared, monkeypatch):
    manager, _, _, _ = prepared
    manager.promote()
    with pytest.raises(recovery.RecoveryError, match='Verifica'):
        manager.resume()
    manager.verify()
    monkeypatch.setenv('MONITORING_ALLOWED_URLS', '[]')
    with pytest.raises(recovery.RecoveryError, match='política'):
        manager.resume()
    monkeypatch.setenv('MONITORING_ALLOWED_URLS', '["http://portal-lab:8080/health"]')
    assert manager.resume()['resumed_targets'] == 1
    assert manager.resume()['resumed_targets'] == 0
    with database(manager.live) as db:
        assert dict(db.execute('SELECT service_id,enabled FROM telemetry_targets')) == {1:1, 2:0}


def test_cancel_stage_and_confirmed_next_generation(prepared):
    manager, _, archive, key = prepared
    first = manager.state()['generation']
    assert manager.rollback()['phase'] == 'cancelled'
    manager.stage(archive, key); manager.promote(); manager.verify(); manager.commit()
    manager.stage(archive, key)
    assert manager.state()['generation'] != first
    assert (manager.folder / first / 'candidate/nexo.db').is_file()


def test_path_traversal_in_state_is_rejected(prepared):
    manager, _, _, _ = prepared
    state = manager.state(); state['generation'] = '../other'
    write_json(manager.state_path, state)
    with pytest.raises(recovery.RecoveryError, match='Identificador'):
        manager.rollback()
