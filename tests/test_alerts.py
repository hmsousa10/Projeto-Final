import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app import telemetry
from app.db import database, initialize
from app.main import create_app


def series(stamps, success='0', duration='0.01'):
    return [{'metric': {'__name__': name, 'service_key': 'portal-lab'},
             'values': [[t, value] for t in stamps]}
            for name, value in [('probe_success', success), ('probe_duration_seconds', duration)]]


def test_alert_confirmation_concurrency_escalation_and_recovery(tmp_path):
    path = tmp_path / 'alerts.db'
    initialize(path)
    telemetry.initialize_targets(path)
    stamp = time.time() - 30
    telemetry.import_samples(path, series([stamp], '1', '0.8'), stamp)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incidents').fetchone()[0] == 0
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: telemetry.import_samples(path, series([stamp, stamp+10], '1', '0.8'), stamp+10), range(3)))
    with database(path) as db:
        incident = dict(db.execute('SELECT * FROM incidents').fetchone())
        assert incident['severity'] == 'P2'
        assert db.execute('SELECT count(*) FROM incidents').fetchone()[0] == 1
    telemetry.import_samples(path, series([stamp+20, stamp+30]), stamp+30)
    with database(path) as db:
        assert db.execute('SELECT severity FROM incidents').fetchone()[0] == 'P1'
        assert db.execute('SELECT count(*) FROM incidents').fetchone()[0] == 1
    telemetry.import_samples(path, series([stamp+40, stamp+50], '1'), stamp+50)
    telemetry.import_samples(path, series([stamp+40, stamp+50], '1'), stamp+50)
    with database(path) as db:
        assert db.execute('SELECT status FROM incidents').fetchone()[0] == 'open'
        assert db.execute("SELECT count(*) FROM timeline WHERE action='Serviço recuperado'").fetchone()[0] == 1


def test_full_monitoring_incident_knowledge_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv('PROMETHEUS_URL', 'http://prometheus:9090')
    monkeypatch.setattr(telemetry, 'collect', lambda *args: 0)
    app = create_app(tmp_path / 'app.db', demo=True)
    with TestClient(app, base_url='http://localhost') as client:
        assert client.post('/api/login', json={'email': 'admin@local.test', 'password': 'EstudoLocal2026!'}).status_code == 200
        stamp = time.time()
        telemetry.import_samples(app.state.db_path, series([stamp-40, stamp-30]), stamp)
        incident = next(i for i in client.get('/api/incidents').json() if i['source'] == 'prometheus-alert')
        iid = incident['id']
        assert client.post(f'/api/incidents/{iid}/assign', json={'user_id': 1}).status_code == 200
        for state in ('acknowledged', 'investigating'):
            assert client.patch(f'/api/incidents/{iid}', json={'status': state}).status_code == 200
        assert client.patch(f'/api/incidents/{iid}', json={'status': 'resolved', 'note': 'Descrição suficiente da resolução.'}).status_code == 409
        telemetry.import_samples(app.state.db_path, series([stamp-10, stamp], '1'), stamp)
        assert client.patch(f'/api/incidents/{iid}', json={'status': 'resolved', 'note': 'Recuperação confirmada por sondagens HTTP.'}).status_code == 200
        assert client.patch(f'/api/incidents/{iid}', json={'status': 'closed', 'root_cause': 'Falha controlada do serviço HTTP.', 'prevention': 'Validar a monitorização antes de alterações.', 'runbook': 'Consultar os logs HTTP 503 e recuperar o serviço.'}).status_code == 200
        timeline = client.get(f'/api/incidents/{iid}').json()['timeline']
        assert {r['action'] for r in timeline} >= {'Alerta confirmado por sondagens', 'Serviço recuperado', 'Fechado'}
        results = client.get('/api/knowledge', params={'q': 'Falha serviço HTTP 503 recuperar sondagens'}).json()['results']
        assert iid in [r['id'] for r in results]


def test_gap_staleness_and_closed_episode_do_not_create_false_incidents(tmp_path):
    path = tmp_path / 'alerts.db'
    initialize(path)
    telemetry.initialize_targets(path)
    stamp = time.time()
    telemetry.import_samples(path, series([stamp-100, stamp]), stamp)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incidents').fetchone()[0] == 0
    telemetry.import_samples(path, series([stamp-10, stamp]), stamp)
    with database(path) as db:
        db.execute("UPDATE incidents SET status='closed'")
    telemetry.import_samples(path, series([stamp+10, stamp+20]), stamp+20)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incidents').fetchone()[0] == 1
    telemetry.import_samples(path, series([stamp+30, stamp+40], '1'), stamp+40)
    telemetry.import_samples(path, series([stamp+50, stamp+60]), stamp+60)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incidents').fetchone()[0] == 2
