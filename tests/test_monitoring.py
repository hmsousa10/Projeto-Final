import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from app import monitoring, telemetry
from app.db import database, initialize
from app.main import create_app

URL = 'http://portal-lab:8080/api/orders'
TOKEN = 'test-discovery-secret-with-at-least-32-characters'


@pytest.fixture
def client(tmp_path, monkeypatch):
    token = tmp_path / 'discovery.key'
    token.write_text(TOKEN)
    monkeypatch.setenv('MONITORING_SD_TOKEN_FILE', str(token))
    monkeypatch.setenv('MONITORING_ALLOWED_URLS', json.dumps([*monitoring.LAB_URLS.values(), URL]))
    monkeypatch.setenv('PROMETHEUS_URL', 'http://prometheus:9090')
    monkeypatch.setattr(telemetry, 'collect', lambda *args: 0)
    with TestClient(create_app(tmp_path / 'app.db', demo=True), base_url='http://localhost') as client:
        client.post('/api/login', json={'email':'admin@local.test','password':'EstudoLocal2026!'})
        yield client


def service(client):
    return client.post('/api/services', json={'name':'Pedidos monitorizados','team':'Operações'}).json()['id']


def probe(stamp, key, success='0'):
    return [{'metric': {'service_key':key,'__name__':name}, 'values': [[stamp, value]]}
            for name, value in [('probe_success',success), ('probe_duration_seconds','0.02')]]


def test_discovery_requires_own_secret_not_a_browser_session(client):
    assert client.get('/internal/targets').status_code == 401
    assert client.get('/internal/targets', headers={'Authorization':'Bearer wrong'}).status_code == 401
    response = client.get('/internal/targets', headers={'Authorization':'Bearer '+TOKEN})
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert len(response.json()) == 2
    assert TOKEN not in client.get('/api/config').text
    assert TOKEN not in client.get('/api/monitoring/options').text


def test_registration_and_pause_resume_use_only_new_samples(client):
    sid = service(client)
    response = client.put(f'/api/services/{sid}/monitoring', json={'url':URL})
    assert response.status_code == 200
    key = response.json()['target_key']
    path = client.app.state.db_path
    stamp = time.time()
    # The sample predates registration and must not create an observation.
    assert telemetry.import_samples(path, probe(stamp-10,key),stamp) == 0
    assert telemetry.import_samples(path, probe(stamp,key),stamp) == 1
    assert len(client.get('/internal/targets', headers={'Authorization':'Bearer '+TOKEN}).json()) == 3
    assert client.put(f'/api/services/{sid}/monitoring', json={'url':URL,'enabled':False}).status_code == 200
    assert telemetry.import_samples(path, probe(stamp+1,key),stamp+1) == 0
    row = next(s for s in client.get('/api/services').json() if s['id']==sid)
    assert row['status'] == 'unknown' and not row['monitoring']['enabled']
    assert len(client.get('/internal/targets', headers={'Authorization':'Bearer '+TOKEN}).json()) == 2
    assert client.put(f'/api/services/{sid}/monitoring', json={'url':URL,'enabled':True}).status_code == 200
    assert telemetry.import_samples(path, probe(stamp,key),time.time()) == 0
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM observations WHERE service_id=?',(sid,)).fetchone()[0] == 1
        assert not db.execute('SELECT 1 FROM incidents WHERE service_id=?',(sid,)).fetchone()


def test_target_identity_and_synthetic_history_are_preserved(client):
    sid = service(client)
    assert client.put(f'/api/services/{sid}/monitoring', json={'url':URL}).status_code == 200
    assert client.put(f'/api/services/{sid}/monitoring', json={'url':monitoring.LAB_URLS['portal-lab']}).status_code == 409
    assert client.put('/api/services/1/monitoring', json={'url':URL}).status_code == 409
    lab_sid = next(s['id'] for s in client.get('/api/services').json() if s['monitoring'])
    assert client.put(f'/api/services/{lab_sid}/monitoring', json={'url':monitoring.LAB_URLS['portal-lab'],'enabled':False}).status_code == 409
    assert client.get(f'/api/services/{sid}/logs').status_code == 404


@pytest.mark.parametrize('url', ['http://169.254.169.254/latest/meta-data/', 'http://localhost:8000/api/users',
                                   URL+'?token=secret', 'file:///etc/passwd', 'http://user:secret@host/',
                                   'http://portal-lab:8080/health/../_control'])
def test_unapproved_or_unsafe_addresses_are_not_accepted(client, url):
    sid = service(client)
    assert client.put(f'/api/services/{sid}/monitoring', json={'url':url}).status_code in (403,422)
    assert client.get('/internal/targets', headers={'Authorization':'Bearer '+TOKEN}).json() == [
        {'targets':[monitoring.LAB_URLS[k]],'labels':{'service_key':k}} for k in sorted(monitoring.LAB_URLS)]


def test_revoked_address_stops_import_and_cannot_be_resumed(client, monkeypatch):
    sid = service(client)
    key = client.put(f'/api/services/{sid}/monitoring', json={'url':URL}).json()['target_key']
    monkeypatch.setenv('MONITORING_ALLOWED_URLS', json.dumps(list(monitoring.LAB_URLS.values())))
    assert telemetry.import_samples(client.app.state.db_path, probe(time.time(),key)) == 0
    assert not next(s for s in client.get('/api/services').json() if s['id']==sid)['monitoring']['approved']
    assert client.put(f'/api/services/{sid}/monitoring', json={'url':URL,'enabled':False}).status_code == 200
    assert client.put(f'/api/services/{sid}/monitoring', json={'url':URL,'enabled':True}).status_code == 403


@pytest.mark.parametrize('email', ['operacoes@local.test','leitor@local.test'])
def test_only_admin_can_connect_and_pause(client, email):
    sid = service(client)
    client.post('/api/login', json={'email':email,'password':'EstudoLocal2026!'})
    assert client.put(f'/api/services/{sid}/monitoring', json={'url':URL}).status_code == 403
    assert client.get('/api/monitoring/options').status_code == 403
    assert client.get('/api/services').status_code == 200


def test_legacy_mapping_migration_is_idempotent(tmp_path):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE services(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,team TEXT NOT NULL,
            description TEXT NOT NULL,criticality TEXT NOT NULL,slo_availability REAL NOT NULL,slo_latency_ms INTEGER NOT NULL,created_at TEXT NOT NULL);
            INSERT INTO services VALUES(42,'Laboratório · Portal HTTP','Laboratório','','Média',99.9,500,'2026-10-24');
            CREATE TABLE telemetry_targets(target_key TEXT PRIMARY KEY,service_id INTEGER UNIQUE NOT NULL REFERENCES services(id));
            INSERT INTO telemetry_targets VALUES('portal-lab',42);''')
    initialize(path)
    initialize(path)
    telemetry.initialize_targets(path)
    with database(path) as db:
        row = db.execute("SELECT * FROM telemetry_targets WHERE target_key='portal-lab'").fetchone()
        assert row['service_id'] == 42 and row['target_url'] == monitoring.LAB_URLS['portal-lab']
        assert row['enabled'] == 1


def test_production_policy_has_no_implicit_lab_targets(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.delenv('MONITORING_ALLOWED_URLS', raising=False)
    assert monitoring.allowed_urls() == frozenset()


@pytest.mark.parametrize('policy', ['"http://example.test"','["http://user:secret@host"]','[1]','{"url":"http://host"}'])
def test_invalid_deployment_policy_fails_closed(monkeypatch, policy):
    monkeypatch.setenv('MONITORING_ALLOWED_URLS',policy)
    with pytest.raises(RuntimeError):
        monitoring.allowed_urls()
