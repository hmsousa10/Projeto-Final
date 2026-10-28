import json
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from fastapi.testclient import TestClient

from app import enterprise, lab_service
from app.main import create_app
from tests.test_workflow import login

TOKEN = 'read-token-only-for-isolated-tests-123456'


def body():
    return {'schema_version': 1, 'company_id': 'aurora', 'company_name': 'Aurora',
            'environment': 'laboratory', 'generated_at': datetime.now(timezone.utc).isoformat(),
            'orders': {'total': 3, 'preparing': 1, 'shipped': 1, 'delivered': 1}}


@pytest.fixture
def upstream():
    state = {'calls': [], 'status': 200, 'body': None, 'mime': 'application/json'}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            state['calls'].append((self.path, self.headers.get('Authorization')))
            self.send_response(state['status'])
            self.send_header('Content-Type', state['mime'])
            if state['status'] == 302:
                self.send_header('Location', '/must-not-receive-token')
            raw = state['body'] if state['body'] is not None else json.dumps(body()).encode()
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}/summary', state
        finally:
            server.shutdown()
            thread.join(timeout=3)


def test_actual_json_read_authentication_cache_and_no_secret_in_result(upstream):
    url, state = upstream
    client = enterprise.EnterpriseClient(url, TOKEN)
    first, second = client.fetch(), client.fetch()
    assert first == second and len(state['calls']) == 1
    assert state['calls'][0][1] == 'Bearer ' + TOKEN
    assert first['status'] == 'connected' and first['summary']['orders']['total'] == 3
    assert TOKEN not in json.dumps(first) and url not in json.dumps(first)
    assert first['latency_ms'] >= 0


def test_busy_adapter_does_not_start_another_request(upstream):
    url, state = upstream
    client = enterprise.EnterpriseClient(url, TOKEN)
    client.lock.acquire()
    try:
        assert client.fetch()['status'] == 'busy' and not state['calls']
    finally:
        client.lock.release()


@pytest.mark.parametrize('change,expected', [
    ('counts', 'invalid_payload'), ('boolean', 'invalid_payload'), ('schema', 'invalid_payload'),
    ('company', 'invalid_payload'), ('extra', 'invalid_payload'), ('naive', 'invalid_payload'),
    ('numeric_time', 'invalid_payload'), ('old', 'stale'), ('future', 'stale'),
    ('html', 'invalid_payload'), ('large', 'invalid_payload'), ('mime', 'invalid_payload'),
])
def test_invalid_or_stale_data_never_appears_as_zero_or_success(upstream, change, expected):
    url, state = upstream
    payload = body()
    if change == 'counts': payload['orders']['total'] = 4
    if change == 'boolean': payload['orders']['total'] = True
    if change == 'schema': payload['schema_version'] = True
    if change == 'company': payload['company_id'] = 'other-company'
    if change == 'extra': payload['customers'] = ['unexpected private data']
    if change == 'naive': payload['generated_at'] = '2026-10-28T12:00:00'
    if change == 'numeric_time': payload['generated_at'] = time.time()
    if change in ('old', 'future'):
        payload['generated_at'] = (datetime.now(timezone.utc) + timedelta(seconds=-130 if change == 'old' else 130)).isoformat()
    state['body'] = b'<html>invalid</html>' if change == 'html' else b'x' * 17000 if change == 'large' else json.dumps(payload).encode()
    if change == 'mime': state['mime'] = 'text/plain'
    result = enterprise.EnterpriseClient(url, TOKEN).fetch()
    assert result['status'] == expected and 'summary' not in result
    assert 'unexpected private data' not in json.dumps(result)


@pytest.mark.parametrize('status,expected', [(401, 'unauthorized'), (403, 'unauthorized'), (503, 'unavailable'), (302, 'unavailable')])
def test_http_errors_and_redirects_are_sanitized(upstream, status, expected):
    url, state = upstream
    state.update(status=status, body=('secret upstream ' + TOKEN).encode())
    result = enterprise.EnterpriseClient(url, TOKEN).fetch()
    assert result['status'] == expected and TOKEN not in json.dumps(result)
    assert len(state['calls']) == 1


def test_configuration_disabled_and_http_policy(tmp_path, monkeypatch):
    monkeypatch.delenv('ENTERPRISE_API_URL', raising=False)
    monkeypatch.delenv('ENTERPRISE_API_TOKEN_FILE', raising=False)
    assert enterprise.EnterpriseClient.configured().fetch()['status'] == 'not_configured'
    key = tmp_path / 'read.key'
    key.write_text(TOKEN)
    monkeypatch.setenv('ENTERPRISE_API_TOKEN_FILE', str(key))
    for url in ['http://company.example/summary', 'https://user:password@company.example/summary', 'https://company.example/summary?token=x']:
        monkeypatch.setenv('ENTERPRISE_API_URL', url)
        with pytest.raises(RuntimeError): enterprise.EnterpriseClient.configured()
    monkeypatch.setenv('ENTERPRISE_API_URL', 'http://portal-lab:8080/api/operations/summary')
    assert enterprise.EnterpriseClient.configured().token == TOKEN
    monkeypatch.setenv('APP_ENV', 'production')
    with pytest.raises(RuntimeError): enterprise.EnterpriseClient.configured()
    monkeypatch.setenv('ENTERPRISE_API_URL', 'https://company.example/summary')
    assert enterprise.EnterpriseClient.configured().url.startswith('https://')
    key.write_text('bad\nheader')
    with pytest.raises(RuntimeError): enterprise.EnterpriseClient.configured()


def test_portal_api_requires_session_for_all_roles(upstream, tmp_path, monkeypatch):
    url, state = upstream
    key = tmp_path / 'read.key'
    key.write_text(TOKEN)
    monkeypatch.setenv('ENTERPRISE_API_URL', url)
    monkeypatch.setenv('ENTERPRISE_API_TOKEN_FILE', str(key))
    with TestClient(create_app(tmp_path / 'nexo.db', demo=True), base_url='http://localhost') as client:
        assert client.get('/api/enterprise/summary').status_code == 401
        assert client.get('/api/config').json()['enterprise'] is True
        for email in ['admin@local.test', 'operacoes@local.test', 'leitor@local.test']:
            login(client, email)
            result = client.get('/api/enterprise/summary')
            assert result.status_code == 200 and result.json()['status'] == 'connected'
            assert TOKEN not in result.text and url not in result.text
        assert len(state['calls']) == 1


def test_real_aurora_read_token_is_separate_from_fault_control(monkeypatch):
    with ThreadingHTTPServer(('127.0.0.1', 0), lab_service.Handler) as server:
        server.enterprise_token, server.control_token = TOKEN, 'control-only-test-key-with-32-characters'
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with pytest.raises(HTTPError) as error:
                urlopen(base + '/api/operations/summary')
            assert error.value.code == 401
            with pytest.raises(HTTPError) as error:
                urlopen(Request(base + '/_control', data=b'{"kind":"outage"}', headers={'Authorization': 'Bearer ' + TOKEN}))
            assert error.value.code == 403
            adapter = enterprise.EnterpriseClient(base + '/api/operations/summary', TOKEN)
            assert adapter.fetch()['summary']['orders']['total'] == len(lab_service.ORDERS)
            monkeypatch.setitem(lab_service.STATE, 'kind', 'outage')
            monkeypatch.setitem(lab_service.STATE, 'expires_at', time.time() + 60)
            adapter.cached_at = 0
            assert adapter.fetch()['status'] == 'unavailable'
            monkeypatch.setitem(lab_service.STATE, 'expires_at', time.time() - 1)
            adapter.cached_at = 0
            assert adapter.fetch()['status'] == 'connected'
        finally:
            with lab_service.LOCK:
                lab_service.STATE.update(kind='recovery', expires_at=0)
            server.shutdown()
            thread.join(timeout=3)
