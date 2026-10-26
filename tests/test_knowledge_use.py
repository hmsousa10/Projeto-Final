import json
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.db import database, event
from app import dossier

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD', 'EstudoLocal2026!')
    for name in ('PROMETHEUS_URL','SEMANTIC_URL','LOKI_URL'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('LAB_MODE','0')
    app=create_app(tmp_path/'nexo.db',demo=True)
    with TestClient(app,base_url='http://localhost') as client:
        yield client


def login(client, email='admin@local.test'):
    assert client.post('/api/login',json={'email':email,'password':'EstudoLocal2026!'}).status_code==200


def case(client):
    result=client.post('/api/incidents',json={'service_id':1,'title':'Falha na consulta de pedidos',
        'description':'Erro HTTP 503 observado na consulta de pedidos.'})
    assert result.status_code==201
    return result.json()['id']




def reference(client):
    return next(i['id'] for i in client.get('/api/incidents').json() if i['status']=='closed')


def test_permission_and_constraints(client):
    body={'source_incident_id':1,'reason':'Diagnóstico confirmado pelo operador.'}
    assert client.post('/api/incidents/1/knowledge-use',json=body).status_code==401
    login(client); iid=case(client); sid=reference(client); body['source_incident_id']=sid
    login(client,'leitor@local.test')
    assert client.post(f'/api/incidents/{iid}/knowledge-use',json=body).status_code==403
    login(client)
    assert client.post(f'/api/incidents/{sid}/knowledge-use',json=body).status_code==409
    body['source_incident_id']=iid
    assert client.post(f'/api/incidents/{iid}/knowledge-use',json=body).status_code==422
    other=case(client);body['source_incident_id']=other
    assert client.post(f'/api/incidents/{iid}/knowledge-use',json=body).status_code==409
    body['source_incident_id']=999999
    assert client.post(f'/api/incidents/{iid}/knowledge-use',json=body).status_code==404


@pytest.mark.parametrize('value',[True,'1',0,9223372036854775808])
def test_invalid_reference_ids(client,value):
    login(client)
    assert client.post('/api/incidents/1/knowledge-use',json={'source_incident_id':value,'reason':'Explicação suficientemente longa.'}).status_code==422


def test_snapshot_audit_duplicate_and_export(client):
    login(client,'operacoes@local.test');iid=case(client);sid=reference(client)
    source=client.get(f'/api/incidents/{sid}').json()
    before=client.get(f'/api/incidents/{iid}').json()
    body={'source_incident_id':sid,'reason':'Usei os passos de diagnóstico e confirmei a recuperação.'}
    assert client.post(f'/api/incidents/{iid}/knowledge-use',json=body).status_code==201
    assert client.post(f'/api/incidents/{iid}/knowledge-use',json=body).status_code==409
    after=client.get(f'/api/incidents/{iid}').json()
    assert after['status']==before['status']
    assert len(after['timeline'])==len(before['timeline'])+1
    entry=after['timeline'][-1];record=json.loads(entry['note'])
    assert entry['action']=='Conhecimento aplicado' and entry['actor']
    assert record['reason']==body['reason']
    assert record['source_snapshot']['resolution']==source['resolution']
    with database(client.app.state.db_path) as db:
        db.execute("UPDATE incidents SET resolution='Texto alterado depois da associação' WHERE id=?",(sid,))
        assert db.execute("SELECT count(*) FROM audit WHERE action='incident.knowledge.applied' AND entity=?",(f'incident:{iid}',)).fetchone()[0]==1
    exported=client.get(f'/api/incidents/{iid}/export?format=json').json()['incident']
    assert exported['timeline'][-1]==entry
    assert 'Usei os passos' in client.get(f'/api/incidents/{iid}/export').text
    assert client.get(f'/api/incidents/{iid}').json()['timeline'][-1]==entry


def test_reason_required_and_unknown_fields_rejected(client):
    login(client);iid=case(client);sid=reference(client)
    for body in [{'source_incident_id':sid,'reason':'   '},
                 {'source_incident_id':sid,'reason':'Explicação válida aqui.','actor':'Outra pessoa'}]:
        assert client.post(f'/api/incidents/{iid}/knowledge-use',json=body).status_code==422
