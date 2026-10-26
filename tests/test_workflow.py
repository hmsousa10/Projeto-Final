from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app.db import database
from app.main import create_app
from app.search import retrieve

PASSWORD = 'EstudoLocal2026!'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD', PASSWORD)
    with TestClient(create_app(tmp_path / 'test.db', demo=True), base_url='http://localhost') as client:
        yield client


def login(client, email='admin@local.test'):
    result = client.post('/api/login', json={'email': email, 'password': PASSWORD})
    assert result.status_code == 200, result.text
    return result.json()


def create_incident(client):
    result = client.post('/api/incidents', json={
        'service_id': 1, 'title': 'Portal apresenta erros HTTP 503',
        'description': 'Pedidos falham depois da atualização da configuração.', 'severity': 'P1'})
    assert result.status_code == 201, result.text
    return result.json()['id']


def test_complete_incident_cycle_and_search(client):
    login(client)
    iid = create_incident(client)
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'acknowledged'}).status_code == 422
    assert client.post(f'/api/incidents/{iid}/assign', json={'user_id': 2}).status_code == 200
    for state in ('acknowledged', 'investigating'):
        assert client.patch(f'/api/incidents/{iid}', json={'status': state}).status_code == 200
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'resolved', 'note': 'curta'}).status_code == 422
    assert client.patch(f'/api/incidents/{iid}', json={
        'status': 'resolved', 'note': 'Reverter configuração e validar respostas HTTP.'}).status_code == 200
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'closed'}).status_code == 422
    assert client.patch(f'/api/incidents/{iid}', json={
        'status': 'closed', 'root_cause': 'Configuração incorreta na atualização.',
        'prevention': 'Validar configuração automaticamente antes de cada atualização.',
        'runbook': 'Comparar configuração; reverter; validar o serviço.'}).status_code == 200
    detail = client.get(f'/api/incidents/{iid}').json()
    assert detail['acknowledged_at'] <= detail['resolved_at'] <= detail['closed_at']
    assert len(detail['timeline']) == 6
    assert detail['resolution'].startswith('Reverter')
    assert client.post(f'/api/incidents/{iid}/comments', json={'note': 'Alteração tardia'}).status_code == 409
    matches = client.get('/api/knowledge', params={'q': 'configuração HTTP 503'}).json()['results']
    assert iid in [r['id'] for r in matches]
    summary = client.get('/api/summary').json()
    assert summary['mtta']['count'] == 4
    assert summary['mttr']['count'] == 4
    log = client.get('/api/audit').json()
    assert sum(r['action'] == 'incident.transition' and r['entity'] == f'incident:{iid}' for r in log) == 4


def test_reader_permissions_are_enforced_on_server(client):
    login(client, 'leitor@local.test')
    assert client.get('/api/services').status_code == 200
    assert client.get('/api/incidents').status_code == 200
    assert client.get('/api/audit').status_code == 403
    assert client.post('/api/demo/scenario', json={'service_id': 1, 'kind': 'outage'}).status_code == 403
    assert client.post('/api/incidents', json={
        'service_id': 1, 'title': 'Tentativa de criação', 'description': 'Leitor não pode criar incidentes.',
        'severity': 'P1'}).status_code == 403
    assert client.post('/api/services', json={'name': 'Serviço novo','team': 'Equipa'}).status_code == 403
    assert client.patch('/api/incidents/1', json={'status': 'open'}).status_code == 403


def test_operator_cannot_create_services_or_read_audit(client):
    login(client, 'operacoes@local.test')
    create_incident(client)
    assert client.post('/api/services', json={'name': 'Serviço novo','team': 'Equipa'}).status_code == 403
    assert client.get('/api/audit').status_code == 403


def test_session_authentication_logout_and_origin(client):
    assert client.get('/api/summary').status_code == 401
    assert client.post('/api/login', json={'email':'admin@local.test','password':'errada'}).status_code == 401
    login(client)
    assert client.get('/api/me').json()['role'] == 'admin'
    response = client.post('/api/demo/scenario', json={'service_id':1,'kind':'outage'},
                           headers={'Origin':'https://outro-site.invalid'})
    assert response.status_code == 403
    assert client.post('/api/logout').status_code == 200
    assert client.get('/api/me').status_code == 401


def test_service_validation_and_dependencies(client):
    login(client)
    payload = {'name':'Marcações', 'team':'Serviços digitais', 'slo_availability':99.9,
               'slo_latency_ms':450, 'dependencies':[1,4,4]}
    result = client.post('/api/services', json=payload)
    assert result.status_code == 201
    service = next(s for s in client.get('/api/services').json() if s['id'] == result.json()['id'])
    assert service['dependencies'] == [1,4]
    assert service['status'] == 'unknown'
    assert service['availability'] is None
    assert client.post('/api/services', json=payload).status_code == 409
    assert client.post('/api/services', json={**payload, 'name':'Outro', 'slo_availability':101}).status_code == 422
    assert client.post('/api/services', json={**payload, 'name':'Outro', 'dependencies':[999]}).status_code == 404
    fast = client.post('/api/services', json={**payload, 'name':'Serviço de baixa latência', 'slo_latency_ms':1}).json()
    assert client.post('/api/demo/scenario', json={'service_id':fast['id'],'kind':'recovery'}).status_code == 200
    fast_state = next(s for s in client.get('/api/services').json() if s['id']==fast['id'])
    assert fast_state['status'] == 'healthy'


def test_demo_alert_grouping_and_explicit_recovery(client):
    login(client)
    first = client.post('/api/demo/scenario', json={'service_id':1,'kind':'outage'}).json()
    second = client.post('/api/demo/scenario', json={'service_id':1,'kind':'outage'}).json()
    assert first['incident_id'] == second['incident_id']
    assert client.get('/api/summary').json()['active_incidents'] == 1
    service = client.get('/api/services').json()[0]
    assert service['status'] == 'down'
    assert service['sample_count'] == 26
    assert service['availability'] == round(24/26*100,3)
    client.post('/api/demo/scenario', json={'service_id':1,'kind':'recovery'})
    assert client.get('/api/services').json()[0]['status'] == 'healthy'
    assert client.get(f'/api/incidents/{first["incident_id"]}').json()['status'] == 'open'


def test_concurrent_simulations_create_one_active_incident(client):
    login(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.post('/api/demo/scenario', json={'service_id':2,'kind':'outage'}), range(2)))
    assert all(r.status_code == 200 for r in results)
    assert results[0].json()['incident_id'] == results[1].json()['incident_id']


def test_invalid_state_jump_does_not_write_event(client):
    login(client)
    iid = create_incident(client)
    response = client.patch(f'/api/incidents/{iid}', json={'status':'closed','root_cause':'Causa conhecida','prevention':'Ação preventiva'})
    assert response.status_code == 409
    row = client.get(f'/api/incidents/{iid}').json()
    assert row['status'] == 'open'
    assert len(row['timeline']) == 1
    assert client.post(f'/api/incidents/{iid}/assign', json={'user_id':3}).status_code == 422


def test_retrieval_returns_evidence_and_not_unrelated_matches():
    docs = [{'id':1, 'title':'Timeout pagamentos', 'description':'Base de dados saturada',
             'resolution':'Libertar ligações', 'root_cause':'Pool esgotado'},
            {'id':2, 'title':'Faturas duplicadas', 'description':'Fila de faturação',
             'resolution':'Remover duplicados', 'root_cause':'Reprocessamento'}]
    result = retrieve('TIMEOUT ligações', docs)
    assert result[0]['id'] == 1
    assert 0 < result[0]['score'] <= 1
    assert result[0]['resolution'] == 'Libertar ligações'
    assert retrieve('banana telescopio', docs) == []
    assert retrieve('timeout', []) == []


def test_data_and_session_survive_app_restart(tmp_path, monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD', PASSWORD)
    path = tmp_path / 'persistent.db'
    with TestClient(create_app(path,demo=True), base_url='http://localhost') as first:
        login(first)
        iid = create_incident(first)
        cookie = first.cookies.get('nexo_session')
    with TestClient(create_app(path,demo=True), base_url='http://localhost') as second:
        second.cookies.set('nexo_session',cookie)
        assert second.get(f'/api/incidents/{iid}').status_code == 200
        assert len(second.get('/api/services').json()) == 4


def test_clean_mode_has_no_demo_data_or_simulator(tmp_path,monkeypatch):
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD',PASSWORD)
    with TestClient(create_app(tmp_path / 'clean.db',demo=False), base_url='http://localhost') as client:
        assert client.get('/api/config').json()['demo'] is False
        login(client)
        assert client.get('/api/services').json() == []
        assert client.get('/api/summary').json()['mttr'] == {'seconds':None,'count':0}
        assert client.post('/api/demo/scenario',json={'service_id':1,'kind':'outage'}).status_code == 404


def test_stale_observations_are_not_shown_as_healthy(client):
    login(client)
    with database(client.app.state.db_path) as db:
        db.execute("UPDATE observations SET observed_at='2020-01-01T00:00:00+00:00' WHERE service_id=1")
    service = client.get('/api/services').json()[0]
    assert service['status'] == 'unknown'
    assert service['availability'] is None
