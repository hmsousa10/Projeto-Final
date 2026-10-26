import time

import pytest
from fastapi.testclient import TestClient

from app import telemetry
from app.db import database, initialize
from app.main import create_app


def samples(stamp, success='1'):
    return [{'metric': {'__name__': name, 'service_key': key}, 'values': [[stamp, value]]}
            for key in telemetry.TARGETS for name, value in
            [('probe_success', success), ('probe_duration_seconds', '0.8')]]


def test_real_samples_deduplicate_and_ignore_untrusted_labels(tmp_path):
    path = tmp_path / 'metrics.db'
    initialize(path)
    telemetry.initialize_targets(path)
    stamp = time.time()
    series = samples(stamp)
    series.append({'metric': {'__name__': 'probe_success', 'service_key': 'arbitrary-target'},
                   'values': [[stamp, '1']]})
    assert telemetry.import_samples(path, series, stamp) == 2
    assert telemetry.import_samples(path, series, stamp) == 0
    with database(path) as db:
        rows = db.execute('SELECT * FROM observations').fetchall()
        assert len(rows) == 2
        assert all(r['source'] == 'prometheus' and r['latency_ms'] == 800 for r in rows)
    assert telemetry.status(path, True)['status'] == 'connected'


def test_bad_or_stale_samples_never_become_fresh(tmp_path):
    path = tmp_path / 'metrics.db'
    initialize(path)
    telemetry.initialize_targets(path)
    stamp = time.time()
    assert telemetry.import_samples(path, samples(stamp - 180), stamp) == 0
    assert telemetry.import_samples(path, samples(stamp, 'NaN'), stamp) == 0
    assert telemetry.import_samples(path, samples(stamp + 60), stamp) == 0
    assert telemetry.status(path, True)['status'] == 'incomplete'


def test_upstream_failure_keeps_observations_and_marks_unavailable(tmp_path, monkeypatch):
    path = tmp_path / 'metrics.db'
    initialize(path)
    telemetry.initialize_targets(path)
    telemetry.import_samples(path, samples(time.time()))
    def fail(url):
        raise OSError('sensitive upstream information')
    monkeypatch.setattr(telemetry, 'fetch_metrics', fail)
    assert telemetry.collect(path, 'http://prometheus:9090') == 0
    assert telemetry.status(path, True)['status'] == 'unavailable'
    assert 'sensitive' not in str(telemetry.status(path, True))
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM observations').fetchone()[0] == 2


def test_monitoring_authentication_freshness_and_simulator_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv('PROMETHEUS_URL', 'http://prometheus:9090')
    monkeypatch.setattr(telemetry, 'collect', lambda *args: 0)
    app = create_app(tmp_path / 'app.db', demo=True)
    with TestClient(app, base_url='http://localhost') as client:
        assert client.get('/api/telemetry').status_code == 401
        assert client.post('/api/login', json={'email': 'admin@local.test', 'password': 'EstudoLocal2026!'}).status_code == 200
        telemetry.import_samples(app.state.db_path, samples(time.time() - 60, '0'))
        services = [s for s in client.get('/api/services').json() if s['team'] == 'Laboratório']
        assert len(services) == 2
        assert all(s['status'] == 'unknown' for s in services)
        assert client.post('/api/demo/scenario', json={'service_id': services[0]['id'], 'kind': 'recovery'}).status_code == 409
        telemetry.import_samples(app.state.db_path, samples(time.time(), '0'))
        services = [s for s in client.get('/api/services').json() if s['team'] == 'Laboratório']
        assert all(s['status'] == 'down' for s in services)


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'http://user:secret@host', 'http://host/path', 'http://host?token=secret'])
def test_reject_invalid_upstream_configuration(url):
    with pytest.raises(RuntimeError):
        telemetry.validate_url(url)
