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



def test_export_auth_validation_and_missing(client):
    assert client.get('/api/incidents/1/export').status_code == 401
    login(client)
    assert client.get('/api/incidents/999999/export').status_code == 404
    assert client.get('/api/incidents/1/export?format=html').status_code == 422


def test_reader_export_complete_and_read_only(client):
    login(client)
    iid=case(client)
    with database(client.app.state.db_path) as db:
        event(db,iid,'Operador','Nota de investigação','Conteúdo Unicode: ação e prevenção.')
        db.execute("INSERT INTO incident_evidence(incident_id,source,captured_at,actor,payload) VALUES(?,?,?,?,?)",
                   (iid,'loki','2026-10-26T00:00:00+00:00','Operador',json.dumps({'entries':[{'status':503}]})))
    before=client.get(f'/api/incidents/{iid}').json()
    login(client,'leitor@local.test')
    response=client.get(f'/api/incidents/{iid}/export?format=json')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert 'attachment;' in response.headers['content-disposition']
    report=response.json()
    assert report['incident']==before
    assert report['incident']['evidence'][0]['payload']['entries'][0]['status']==503
    assert report['service_at_export']['id']==1
    assert report['assignee_at_export'] is None
    assert not any(k in response.text for k in ['password_hash','token_hash','admin@local.test','login_attempts'])
    assert client.get(f'/api/incidents/{iid}').json()==before
    md=client.get(f'/api/incidents/{iid}/export').text
    assert 'Linha temporal completa' in md and 'Conteúdo Unicode' in md and '503' in md


def test_closed_case_has_postmortem(client):
    login(client,'leitor@local.test')
    cases=client.get('/api/incidents').json()
    iid=next(i['id'] for i in cases if i['status']=='closed')
    original=client.get(f'/api/incidents/{iid}').json()
    report=client.get(f'/api/incidents/{iid}/export?format=json').json()
    assert report['incident']==original
    assert report['incident']['root_cause'] and report['incident']['resolution']


def test_untrusted_markdown_stays_literal():
    payload='```\n<script>alert(1)</script>\n# Spoof\n````'
    rendered=dossier.literal(payload)
    assert rendered.startswith('`````\n') and rendered.endswith('\n`````\n')
    assert payload in rendered


def test_snapshot_does_not_mix_concurrent_updates(tmp_path):
    from app.db import initialize
    from app.seed import seed
    path=tmp_path/'snapshot.db'
    initialize(path)
    # Use the API fixture pattern to initialize the demonstration records.
    app=create_app(path,demo=True)
    with TestClient(app,base_url='http://localhost'):
        with database(path) as reader:
            reader.execute('BEGIN')
            original=dossier.build(reader,1)
            with database(path) as writer:
                writer.execute("UPDATE services SET name='Novo nome' WHERE id=1")
                event(writer,1,'Teste','Alteração concorrente','Depois do início da exportação')
            repeated=dossier.build(reader,1)
            assert repeated['incident']==original['incident']
            assert repeated['service_at_export']==original['service_at_export']
