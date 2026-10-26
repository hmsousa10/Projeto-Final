import json
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from fastapi.testclient import TestClient

from app import lab, lab_service, logs, telemetry
from app.main import create_app


def test_fault_control_is_local_and_role_restricted(tmp_path, monkeypatch):
    token = tmp_path / 'key'
    token.write_text('x'*40)
    monkeypatch.setenv('LAB_MODE', '1')
    monkeypatch.setenv('LAB_CONTROL_TOKEN_FILE', str(token))
    monkeypatch.setenv('LOKI_URL', 'http://loki:3100')
    monkeypatch.setattr(lab, 'set_fault', lambda target, kind: {'kind': kind, 'expires_at': 123})
    monkeypatch.setattr(logs, 'read_logs', lambda *args: (_ for _ in ()).throw(OSError('secret upstream error')))
    app = create_app(tmp_path / 'app.db', demo=True)
    with TestClient(app, base_url='http://localhost') as client:
        assert client.post('/api/lab/fault', json={'target': 'portal-lab', 'kind': 'outage'}).status_code == 401
        client.post('/api/login', json={'email': 'leitor@local.test', 'password': 'EstudoLocal2026!'})
        assert client.post('/api/lab/fault', json={'target': 'portal-lab', 'kind': 'outage'}).status_code == 403
        client.post('/api/login', json={'email': 'operacoes@local.test', 'password': 'EstudoLocal2026!'})
        assert client.post('/api/lab/fault', json={'target': 'portal-lab', 'kind': 'outage'}).status_code == 200
        assert client.post('/api/lab/fault', json={'target': 'http://evil', 'kind': 'outage'}).status_code == 422
        telemetry.initialize_targets(app.state.db_path)
        sid = next(s['id'] for s in client.get('/api/services').json() if s['telemetry_source'] == 'prometheus')
        response = client.get(f'/api/services/{sid}/logs')
        assert response.status_code == 503
        assert 'secret upstream' not in response.text


def test_production_rejects_fault_controls(tmp_path, monkeypatch):
    monkeypatch.setenv('LAB_MODE', '1')
    monkeypatch.setenv('APP_ENV', 'production')
    with pytest.raises(RuntimeError, match='controlos'):
        create_app(tmp_path / 'prod.db', demo=False)


def test_actual_http_fault_and_automatic_expiry(monkeypatch):
    with ThreadingHTTPServer(('127.0.0.1', 0), lab_service.Handler) as server:
        server.control_token = 'test-key-with-at-least-32-characters'
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            req = Request(base+'/_control', data=b'{"kind":"outage"}', headers={'Content-Type':'application/json'})
            with pytest.raises(HTTPError) as error:
                urlopen(req)
            assert error.value.code == 403
            req.add_header('Authorization', 'Bearer '+server.control_token)
            with urlopen(req) as response:
                result = json.load(response)
            assert 110 <= result['expires_at'] - time.time() <= 120
            with pytest.raises(HTTPError) as error:
                urlopen(base+'/api/orders')
            assert error.value.code == 503
            monkeypatch.setitem(lab_service.STATE, 'expires_at', time.time()-1)
            with urlopen(base+'/api/orders') as response:
                assert len(json.load(response)['orders']) == 3
        finally:
            with lab_service.LOCK:
                lab_service.STATE.update(kind='recovery', expires_at=0)
            server.shutdown()


def test_log_query_target_is_allowlisted():
    with pytest.raises(ValueError):
        logs.read_logs('http://loki:3100', 'portal-lab"} |= "secret')


def test_preserved_evidence_survives_upstream_failure_and_closure(tmp_path, monkeypatch):
    monkeypatch.setenv('LOKI_URL', 'http://loki:3100')
    entries = [{'timestamp_ns': str(time.time_ns()), 'method':'GET', 'path':'/api/orders', 'status':503, 'duration_ms':1.2}]
    monkeypatch.setattr(logs, 'read_logs', lambda *args: entries)
    app = create_app(tmp_path / 'evidence.db', demo=True)
    with TestClient(app, base_url='http://localhost') as client:
        client.post('/api/login', json={'email':'admin@local.test', 'password':'EstudoLocal2026!'})
        telemetry.initialize_targets(app.state.db_path)
        sid = next(s['id'] for s in client.get('/api/services').json() if s['telemetry_source']=='prometheus')
        iid = client.post('/api/incidents', json={'service_id':sid,'title':'Falha HTTP 503 no portal','description':'Erro no carregamento dos pedidos de laboratório.'}).json()['id']
        assert client.post(f'/api/incidents/{iid}/evidence').status_code == 201
        def fail(*args):
            raise OSError('Loki offline')
        monkeypatch.setattr(logs, 'read_logs', fail)
        assert client.post(f'/api/incidents/{iid}/evidence').status_code == 503
        assert client.get(f'/api/incidents/{iid}').json()['evidence'][0]['payload']['entries'] == entries
        client.post(f'/api/incidents/{iid}/assign', json={'user_id':1})
        for state in ('acknowledged', 'investigating', 'resolved', 'closed'):
            result = client.patch(f'/api/incidents/{iid}', json={'status':state,'note':'Recuperação HTTP confirmada no ensaio.',
                                  'root_cause':'Falha controlada de laboratório.','prevention':'Validar antes de alterações.'})
            assert result.status_code == 200
        assert client.post(f'/api/incidents/{iid}/evidence').status_code == 409
        assert len(client.get(f'/api/incidents/{iid}').json()['evidence']) == 1
        client.post('/api/login', json={'email':'leitor@local.test','password':'EstudoLocal2026!'})
        assert client.post(f'/api/incidents/{iid}/evidence').status_code == 403
        assert client.get(f'/api/incidents/{iid}').json()['evidence'][0]['payload']['entries'][0]['status']==503
