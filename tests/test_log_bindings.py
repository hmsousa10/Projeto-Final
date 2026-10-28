import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from app import logs, monitoring, telemetry
from app.main import create_app

ORDERS = 'http://portal-lab:8080/api/orders'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD', 'EstudoLocal2026!')
    monkeypatch.setenv('LOKI_URL', 'http://loki:3100')
    monkeypatch.setenv('MONITORING_ALLOWED_URLS', json.dumps([*monitoring.LAB_URLS.values(), ORDERS]))
    monkeypatch.delenv('SEMANTIC_URL', raising=False)
    monkeypatch.setenv('PROMETHEUS_URL', 'http://prometheus:9090')
    token = tmp_path/'discovery.key'
    token.write_text('test-discovery-token-with-more-than-32-characters')
    monkeypatch.setenv('MONITORING_SD_TOKEN_FILE', str(token))
    monkeypatch.setattr(telemetry, 'collect', lambda *args: 0)
    app = create_app(tmp_path/'logs.db', demo=True)
    with TestClient(app, base_url='http://localhost') as c:
        telemetry.initialize_targets(app.state.db_path)
        login(c)
        yield c


def login(client, email='admin@local.test'):
    assert client.post('/api/login', json={'email': email, 'password': 'EstudoLocal2026!'}).status_code == 200


def connected_service(client):
    response = client.post('/api/services', json={'name': 'Pedidos Aurora', 'team': 'Operações'})
    assert response.status_code == 201
    sid = response.json()['id']
    assert client.put(f'/api/services/{sid}/monitoring', json={'url': ORDERS}).status_code == 200
    return sid


def test_explicit_mapping_and_revoked_or_unknown_targets(monkeypatch):
    monkeypatch.setenv('MONITORING_ALLOWED_URLS', json.dumps([ORDERS, 'http://other:8080/api/orders']))
    scope = logs.binding({'target_key': 'generated-id', 'target_url': ORDERS})
    assert scope['service_key'] == 'portal-lab' and scope['path'] == '/api/orders'
    assert logs.binding({'target_key': 'portal-lab', 'target_url': 'http://other:8080/api/orders'}) is None
    monkeypatch.setenv('MONITORING_ALLOWED_URLS', '[]')
    assert logs.binding({'target_key': 'portal-lab', 'target_url': ORDERS}) is None
    assert logs.binding(None) is None


def fake_upstream(monkeypatch, streams):
    requests = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            return json.dumps({'status': 'success', 'data': {'resultType': 'streams', 'result': streams}}).encode()[:size]
    class Opener:
        def open(self, url, timeout):
            requests.append((url, timeout))
            return Response()
    monkeypatch.setattr(logs, 'build_opener', lambda *args: Opener())
    return requests


def entry(path, stamp, status=200):
    return [str(stamp), json.dumps({'path': path, 'method': 'GET', 'status': status, 'duration_ms': 1.2})]


def test_endpoint_filtered_before_upstream_limit_and_locally(monkeypatch):
    now = time.time_ns()
    monkeypatch.setattr(logs.time, 'time_ns', lambda: now)
    values = [entry('/health', now-n) for n in range(50)]
    values += [entry('/api/orders', now-100, 503), entry('/api/orders', now-901*10**9), entry('/api/orders', now+1)]
    requests = fake_upstream(monkeypatch, [{'stream': {'service_key': 'portal-lab'}, 'values': values}])
    result = logs.read_logs('http://loki:3100', 'portal-lab', '/api/orders')
    assert len(result) == 1 and result[0]['status'] == 503
    query = parse_qs(urlsplit(requests[0][0]).query)
    assert '| json | __error__="" | path="/api/orders"' in query['query'][0]
    assert query['limit'] == ['50'] and requests[0][1] == 5


def test_service_scope_keeps_multiple_paths_and_rejects_wrong_origin(monkeypatch):
    now = time.time_ns()
    fake_upstream(monkeypatch, [{'stream': {'service_key': 'portal-lab'},
        'values': [entry('/health', now-1), entry('/api/orders', now-2)]}])
    assert len(logs.read_logs('http://loki:3100', 'portal-lab')) == 2
    fake_upstream(monkeypatch, [{'stream': {'service_key': 'api-lab'}, 'values': [entry('/api/orders', now)]}])
    with pytest.raises(ValueError, match='Origem'):
        logs.read_logs('http://loki:3100', 'portal-lab', '/api/orders')
    with pytest.raises(ValueError, match='Caminho'):
        logs.read_logs('http://loki:3100', 'portal-lab', '/api/orders" |= "secret')


def test_configured_service_collects_direct_evidence_and_preserves_scope(client, monkeypatch):
    calls = []
    def read(url, key, path=None):
        calls.append((key, path))
        return [{'timestamp_ns': str(time.time_ns()), 'method': 'GET', 'path': '/api/orders', 'status': 503, 'duration_ms': 1.2}]
    monkeypatch.setattr(logs, 'read_logs', read)
    sid = connected_service(client)
    service = next(s for s in client.get('/api/services').json() if s['id'] == sid)
    assert service['monitoring']['target_key'] not in telemetry.TARGETS
    assert service['logs_available'] and service['log_scope']['path'] == '/api/orders'
    iid = client.post('/api/incidents', json={'service_id': sid, 'title': 'Pedidos temporariamente indisponíveis',
        'description': 'Erro HTTP 503 confirmado na ligação dos pedidos.'}).json()['id']
    assert client.post(f'/api/incidents/{iid}/evidence').status_code == 201
    assert calls == [('portal-lab', '/api/orders')]
    snapshot = client.get(f'/api/incidents/{iid}').json()['evidence'][0]['payload']
    assert snapshot['service_id'] == sid and snapshot['scope']['target_url'] == ORDERS
    assert snapshot['scope']['kind'] == 'endpoint' and snapshot['queried_at']
    assert client.put(f'/api/services/{sid}/monitoring', json={'url': ORDERS, 'enabled': False}).status_code == 200
    assert client.get(f'/api/services/{sid}/logs').status_code == 200
    monkeypatch.setenv('MONITORING_ALLOWED_URLS', '[]')
    assert client.get(f'/api/services/{sid}/logs').status_code == 404
    assert not next(s for s in client.get('/api/services').json() if s['id'] == sid)['logs_available']
    assert client.get(f'/api/incidents/{iid}').json()['evidence'][0]['payload'] == snapshot
    assert client.post(f'/api/incidents/{iid}/assign', json={'user_id': 1}).status_code == 200
    for state in ['acknowledged', 'investigating', 'resolved', 'closed']:
        assert client.patch(f'/api/incidents/{iid}', json={'status': state, 'note': 'Recuperação confirmada na base isolada.',
            'root_cause': 'Falha deliberada no teste isolado.', 'prevention': 'Verificar as sondagens antes de fechar.'}).status_code == 200
    assert client.post(f'/api/incidents/{iid}/evidence').status_code == 409
    login(client, 'leitor@local.test')
    assert client.post(f'/api/incidents/{iid}/evidence').status_code == 403
    exported = client.get(f'/api/incidents/{iid}/export?format=json').json()
    assert exported['incident']['evidence'][0]['payload'] == snapshot
