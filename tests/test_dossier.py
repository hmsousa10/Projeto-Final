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
    assert client.get('/api/incidents/1/export?format=unsupported').status_code == 422


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

@pytest.mark.parametrize('email',['admin@local.test','operacoes@local.test','leitor@local.test'])
def test_print_view_is_authenticated_complete_and_read_only(client,email):
    assert client.get('/api/incidents/1/export?format=html').status_code==401
    login(client,email)
    before=client.get('/api/incidents/1').json()
    response=client.get('/api/incidents/1/export?format=html')
    assert response.status_code==200
    assert response.headers['content-type'].startswith('text/html')
    assert response.headers['content-disposition'].startswith('inline;')
    assert response.headers['cache-control']=='no-store'
    assert response.headers['x-frame-options']=='DENY'
    assert "default-src 'none'" in response.headers['content-security-policy']
    assert "style-src 'sha256-" in response.headers['content-security-policy']
    assert 'unsafe-inline' not in response.headers['content-security-policy']
    assert before['title'] in response.text
    assert 'Linha temporal completa' in response.text and 'Guardar como PDF' in response.text
    assert 'password_hash' not in response.text and 'token_hash' not in response.text
    assert client.get('/api/incidents/1').json()==before
    assert client.get('/api/incidents/999999/export?format=html').status_code==404


def test_print_view_escapes_every_source_and_does_not_load_resources(client):
    from html.parser import HTMLParser
    from app import printable_dossier
    login(client)
    report=client.get('/api/incidents/1/export?format=json').json()
    attack='</style><script>alert(1)</script><img src="https://invalid.test/tracker" onerror="alert(1)">'
    for key in ('title','description','source','resolution','root_cause','prevention','runbook'):
        report['incident'][key]=attack
    report['service_at_export']['name']=attack
    report['service_at_export']['team']=attack
    report['assignee_at_export']={'name':attack}
    report['incident']['timeline']=[{'action':attack,'created_at':attack,'actor':attack,'note':attack}]
    report['incident']['evidence']=[{'id':1,'source':attack,'captured_at':attack,'actor':attack,'payload':{'message':attack}}]
    report['incident']['detection_context']={'untrusted':attack}
    report['incident']['escalation']={'untrusted':attack}
    report['scope']=attack
    report['application_version']=attack
    rendered=printable_dossier.render(report)
    class Inspector(HTMLParser):
        tags=[]
        attributes=[]
        def handle_starttag(self,tag,attrs):
            self.tags.append(tag);self.attributes.extend(attrs)
    parser=Inspector();parser.feed(rendered)
    assert not {'script','img','iframe','object','link','form','input'} & set(parser.tags)
    assert not any(key.startswith('on') for key,value in parser.attributes)
    assert '&lt;script&gt;' in rendered
    assert 'white-space:pre-wrap' in rendered and '@page{size:A4' in rendered


def test_print_styles_match_the_csp_hash_and_dates_are_explicit():
    import base64, hashlib
    from app import printable_dossier as view
    digest=base64.b64encode(hashlib.sha256(view.CSS.encode()).digest()).decode()
    assert f"'sha256-{digest}'" in view.CSP
    assert view.stamp('2026-11-04T18:30:00+01:00')=='04/11/2026 · 17:30:00 UTC'
    assert view.stamp(None)=='Não registado'
    assert view.stamp('Data antiga sem fuso')=='Data antiga sem fuso'
