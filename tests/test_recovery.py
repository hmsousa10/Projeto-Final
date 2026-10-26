from contextlib import closing
import hashlib
from pathlib import Path
import secrets
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import database, initialize, now
from app.knowledge import Knowledge
from app.main import create_app
from app.recovery import RecoveryError, create, decode, restore, verify
from app.seed import seed


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD','EstudoLocal2026!')
    monkeypatch.delenv('SEMANTIC_URL',raising=False)
    path=tmp_path/'source.db'
    initialize(path)
    seed(path)
    Knowledge(str(path)).initialize()
    with database(path) as db:
        db.execute("INSERT INTO sessions VALUES('old-session',1,'2099-01-01')")
        db.execute("INSERT INTO telemetry_targets(target_key,service_id,target_url,enabled) VALUES('test',1,'http://portal-lab:8080/health',1)")
    return path,secrets.token_bytes(32)


def test_live_wal_snapshot_session_removal_and_full_restore(fixture,tmp_path):
    source,key=fixture
    with closing(sqlite3.connect(source)) as live:
        live.execute("INSERT INTO audit(actor,action,entity,detail,created_at) VALUES('test','committed','case','WAL evidence',?)",(now(),))
        live.commit()
        assert Path(str(source)+'-wal').exists()
        before=source.read_bytes()
        archive,manifest=create(source,key)
        assert archive[:8]==b'NEXOBAK1' and b'WAL evidence' not in archive
        assert source.read_bytes()==before
        assert live.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==1
        assert manifest['tables']['sessions']==0
        assert b'old-session' not in decode(archive,key)[0]
        assert verify(archive,key)['verified']
        assert create(source,key)[0]!=archive  # fresh nonce
        target=tmp_path/'restored'
        result=restore(archive,key,target)
        assert result['sessions_revoked'] and result['monitoring_paused']
        with closing(sqlite3.connect(target/'nexo.db')) as db:
            assert db.execute("SELECT COUNT(*) FROM audit WHERE detail='WAL evidence'").fetchone()[0]==1
            assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0
            assert db.execute('SELECT SUM(enabled) FROM telemetry_targets').fetchone()[0]==0
            assert db.execute('SELECT COUNT(*) FROM incidents').fetchone()[0]==manifest['tables']['incidents']
            assert db.execute('SELECT COUNT(*) FROM timeline').fetchone()[0]==manifest['tables']['timeline']
            assert db.execute("SELECT COUNT(*) FROM audit WHERE action='recovery.restored'").fetchone()[0]==1


@pytest.mark.parametrize('change',['key','header','nonce','tag','truncated'])
def test_tamper_never_creates_destination(fixture,tmp_path,change):
    source,key=fixture
    archive,_=create(source,key)
    if change=='key':key=secrets.token_bytes(32)
    elif change=='header':archive=b'X'+archive[1:]
    elif change=='nonce':archive=archive[:8]+bytes([archive[8]^1])+archive[9:]
    elif change=='tag':archive=archive[:-1]+bytes([archive[-1]^1])
    else:archive=archive[:-10]
    with pytest.raises(RecoveryError):restore(archive,key,tmp_path/'new')
    assert not (tmp_path/'new').exists()


def test_never_overwrite_existing_directory(fixture,tmp_path):
    source,key=fixture
    archive,_=create(source,key)
    target=tmp_path/'existing'
    target.mkdir()
    sentinel=target/'nexo.db'
    sentinel.write_bytes(b'do not replace')
    with pytest.raises(RecoveryError):restore(archive,key,target)
    assert sentinel.read_bytes()==b'do not replace'
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    with pytest.raises(RecoveryError):restore(archive,key,source.parent)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before


def test_bad_schema_and_foreign_keys_are_refused(fixture):
    source,key=fixture
    with database(source) as db:
        db.execute('CREATE VIEW unexpected AS SELECT * FROM users')
    with pytest.raises(RecoveryError):create(source,key)
    with database(source) as db:
        db.execute('DROP VIEW unexpected')
        db.execute('PRAGMA foreign_keys=OFF')
        db.execute("UPDATE incidents SET service_id=9999 WHERE id=1")
    with pytest.raises(RecoveryError):create(source,key)


def test_legacy_index_indentation_is_compatible(fixture):
    source,key=fixture
    with database(source) as db:
        db.execute('DROP INDEX unique_prometheus_sample')
        db.execute("CREATE UNIQUE INDEX unique_prometheus_sample\n                ON observations(service_id,source,observed_at) WHERE source='prometheus'")
    archive,_=create(source,key)
    assert verify(archive,key)['verified']


def test_missing_source_invalid_key_and_archive_limit(fixture,tmp_path,monkeypatch):
    source,key=fixture
    with pytest.raises(RecoveryError):create(tmp_path/'missing.db',key)
    with pytest.raises(RecoveryError):create(source,b'short')
    monkeypatch.setattr('app.recovery.MAX_DB',100)
    with pytest.raises(RecoveryError):create(source,key)
    with pytest.raises(RecoveryError):decode(b'NEXOBAK1'+b'x'*80,key)


def test_restore_starts_application_and_retains_history(fixture,tmp_path):
    source,key=fixture
    archive,manifest=create(source,key)
    restored=tmp_path/'recovered'
    restore(archive,key,restored)
    with TestClient(create_app(restored/'nexo.db',demo=True),base_url='http://localhost') as client:
        assert client.get('/api/incidents').status_code==401
        response=client.post('/api/login',json={'email':'leitor@local.test','password':'EstudoLocal2026!'})
        assert response.status_code==200
        rows=client.get('/api/incidents').json()
        assert len(rows)==manifest['tables']['incidents']
        assert client.get('/api/incidents/1').json()['timeline']
        assert client.get('/api/knowledge?q=timeout&method=tfidf').json()['results']
