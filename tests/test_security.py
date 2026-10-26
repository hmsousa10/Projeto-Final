import asyncio

import pytest
from fastapi.testclient import TestClient

from app.db import database
from app.main import create_app
from app.request_limits import BodyLimitMiddleware
from tests.test_workflow import PASSWORD, client, login


def test_rejects_untrusted_host_before_login(client):
    response = client.post('/api/login', json={'email':'admin@local.test','password':PASSWORD},
                           headers={'Host':'attacker.example','Origin':'http://attacker.example'})
    assert response.status_code == 400
    login(client)
    assert client.get('/api/incidents', headers={'Host':'attacker.example'}).status_code == 400


def test_safe_mode_rejects_previously_seeded_database(tmp_path,monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD',PASSWORD)
    path = tmp_path / 'demo.db'
    with TestClient(create_app(path,demo=True),base_url='http://localhost') as seeded:
        login(seeded)
    with pytest.raises(RuntimeError, match='demonstração'):
        with TestClient(create_app(path,demo=False),base_url='http://localhost'):
            pass
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM users').fetchone()[0] == 3


def test_rate_limit_cannot_be_reset_by_another_account(client):
    for _ in range(8):
        assert client.post('/api/login',json={'email':'admin@local.test','password':'incorreta'}).status_code == 401
        login(client,'leitor@local.test')
    assert client.post('/api/login',json={'email':'admin@local.test','password':PASSWORD}).status_code == 429
    assert any(row['action']=='session.failed' for row in _audit_rows(client))


def _audit_rows(client):
    # Ler diretamente a BD de teste evita alterar o rate limit com outro login.
    with database(client.app.state.db_path) as db:
        return [dict(row) for row in db.execute('SELECT * FROM audit')]


def test_rate_limit_survives_restart(tmp_path,monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD',PASSWORD)
    path=tmp_path/'rate-limit.db'
    with TestClient(create_app(path,demo=True),base_url='http://localhost') as first:
        for _ in range(8):
            assert first.post('/api/login',json={'email':'admin@local.test','password':'incorreta'}).status_code==401
    with TestClient(create_app(path,demo=True),base_url='http://localhost') as second:
        assert second.post('/api/login',json={'email':'admin@local.test','password':PASSWORD}).status_code==429


def test_oversized_body_rejected_before_validation(client):
    result=client.post('/api/login',content=b'x'*65537,headers={'Content-Type':'application/json'})
    assert result.status_code==413
    assert client.post('/api/login',json={'email':'admin@local.test','password':'incorreta'}).status_code==401


def test_chunked_body_without_content_length_is_bounded():
    forwarded=[]
    messages=iter([{'type':'http.request','body':b'a'*40000,'more_body':True},
                   {'type':'http.request','body':b'b'*40000,'more_body':False}])
    output=[]

    async def receive():
        return next(messages)

    async def send(message):
        output.append(message)

    async def downstream(scope,receive,send):
        forwarded.append(True)

    asyncio.run(BodyLimitMiddleware(downstream)({'type':'http','headers':[]},receive,send))
    assert not forwarded
    assert output[0]['status']==413


def test_production_refuses_demo(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    with pytest.raises(RuntimeError,match='demonstração'):
        with TestClient(create_app(tmp_path/'production.db',demo=True),base_url='https://localhost'):
            pass


def test_production_requires_https_origin(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('APP_ORIGIN','http://localhost')
    with pytest.raises(RuntimeError,match='HTTPS'):
        with TestClient(create_app(tmp_path/'production.db',demo=False),base_url='https://localhost'):
            pass


def test_production_cookie_headers_and_http_rejection(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('APP_ORIGIN','https://localhost')
    monkeypatch.setenv('COOKIE_SECURE','0')
    production_password='ServidorSeguro2026!local'
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD',production_password)
    with TestClient(create_app(tmp_path/'production.db',demo=False),base_url='https://localhost') as secure:
        response=secure.post('/api/login',json={'email':'admin@local.test','password':production_password})
        assert response.status_code==200
        assert 'Secure' in response.headers['set-cookie']
        assert 'HttpOnly' in response.headers['set-cookie']
        assert 'SameSite=strict' in response.headers['set-cookie']
        assert 'max-age' in response.headers['strict-transport-security']
        assert secure.get('/docs').status_code==404
        assert secure.get('/openapi.json').status_code==404
        assert secure.get('http://localhost/api/me').status_code==400


def test_no_wildcard_host_configuration(tmp_path,monkeypatch):
    monkeypatch.setenv('ALLOWED_HOSTS','*')
    with pytest.raises(RuntimeError,match='wildcards'):
        create_app(tmp_path/'hosts.db',demo=True)


def test_cross_site_write_is_blocked(client):
    login(client)
    assert client.post('/api/demo/scenario',json={'service_id':1,'kind':'outage'},
                       headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
