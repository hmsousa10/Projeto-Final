import json
import threading
from http.server import ThreadingHTTPServer

import httpx
import pytest
from fastapi.testclient import TestClient

from app.bootstrap import initial_password
from app.customer_fixture import APIOnly
from app.enterprise import EnterpriseClient
from app.main import create_app
from scripts.customer_installation import prepare
from tests.test_enterprise import TOKEN


def test_profiles_have_distinct_secrets_and_are_stable_across_restarts(tmp_path):
    atlas, first = prepare(tmp_path, 'atlas', 8003, True)
    boreal, second = prepare(tmp_path, 'boreal', 8004, True)
    assert atlas['company_id'] != boreal['company_id']
    keys = [(folder / name).read_text() for folder in (first, second)
            for name in ('initial-admin.key', 'enterprise-read.key')]
    assert len(set(keys)) == 4 and all(len(key) >= 32 for key in keys)
    assert prepare(tmp_path, 'atlas') == (atlas, first)
    assert (first / 'initial-admin.key').read_text() == keys[0]
    assert keys[0] not in (first / 'profile.json').read_text()
    with pytest.raises(ValueError, match='outra porta'):
        prepare(tmp_path, 'atlas', 8005, True)
    with pytest.raises(ValueError, match='outro ensaio'):
        prepare(tmp_path, 'outro', 8003, True)


@pytest.mark.parametrize('instance,port', [('../lab', 8003), ('Aurora', 8003), ('a;stop', 8003),
                                         ('atlas', 8001), ('atlas', 9000)])
def test_invalid_profiles_cannot_address_main_installation(tmp_path, instance, port):
    with pytest.raises(ValueError):
        prepare(tmp_path, instance, port, True)
    assert not (tmp_path / 'data').exists()


def test_missing_secret_is_not_regenerated(tmp_path):
    _, directory = prepare(tmp_path, 'atlas', 8003, True)
    key = directory / 'enterprise-read.key'
    key.unlink()  # Disposable fixture only.
    with pytest.raises(ValueError, match='Recupera o original'):
        prepare(tmp_path, 'atlas', create=True)
    assert not key.exists()


def test_bootstrap_file_preserves_spaces_and_does_not_echo_secret(tmp_path, monkeypatch):
    path = tmp_path / 'admin.key'
    password = '  Segredo apenas de ensaio 2026!  '
    path.write_text(password, encoding='utf-8')
    monkeypatch.delenv('INITIAL_ADMIN_PASSWORD', raising=False)
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD_FILE', str(path))
    assert initial_password() == password
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD', password)
    with pytest.raises(RuntimeError) as error:
        initial_password()
    assert password not in str(error.value)
    monkeypatch.delenv('INITIAL_ADMIN_PASSWORD')
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD_FILE', str(tmp_path / 'missing.key'))
    with pytest.raises(RuntimeError, match='Não foi possível ler'):
        initial_password()


def test_clean_install_bootstraps_from_file_and_keeps_password_on_restart(tmp_path, monkeypatch):
    path = tmp_path / 'admin.key'
    password = 'Chave exclusiva para ensaio 2026!'
    path.write_text(password, encoding='utf-8')
    monkeypatch.delenv('INITIAL_ADMIN_PASSWORD', raising=False)
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD_FILE', str(path))
    monkeypatch.setenv('INITIAL_ADMIN_EMAIL', 'admin@atlas.test')
    monkeypatch.delenv('ENTERPRISE_API_URL', raising=False)
    monkeypatch.delenv('ENTERPRISE_API_TOKEN_FILE', raising=False)
    database = tmp_path / 'clean.db'
    for _ in range(2):
        with TestClient(create_app(database, demo=False), base_url='http://localhost') as client:
            assert client.post('/api/login', json={'email': 'admin@atlas.test', 'password': password}).status_code == 200
            assert client.get('/api/incidents').json() == []
            assert client.get('/api/services').json() == []
            assert len(client.get('/api/users').json()) == 1
            assert client.post('/api/login', json={'email': 'admin@local.test', 'password': 'EstudoLocal2026!'}).status_code == 401
        path.write_text('This is not a password reset!', encoding='utf-8')


def test_private_fixture_has_distinct_identity_and_no_portal_or_fault_controls():
    with ThreadingHTTPServer(('127.0.0.1', 0), APIOnly) as server:
        server.company_id, server.company_name, server.enterprise_token = 'atlas', 'Atlas · Ensaio', TOKEN
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with httpx.Client(base_url=base, trust_env=False) as client:
                assert client.get('/').status_code == 404
                assert client.get('/api/orders').status_code == 404
                assert client.post('/_control', json={'kind': 'outage'}).status_code == 404
                assert client.get('/api/operations/summary').status_code == 401
            result = EnterpriseClient(base + '/api/operations/summary', TOKEN, 'atlas').fetch()
            assert result['status'] == 'connected' and result['summary']['company_id'] == 'atlas'
            assert TOKEN not in json.dumps(result)
            assert EnterpriseClient(base + '/api/operations/summary', TOKEN, 'aurora').fetch()['status'] == 'invalid_payload'
        finally:
            server.shutdown()
            thread.join(timeout=3)
