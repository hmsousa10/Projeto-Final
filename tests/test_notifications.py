from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import database, event
from app.main import create_app
from app import alerts, telemetry
from app.models import AlertRuleInput


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


def test_login_required_and_no_synthetic_noise(client):
    assert client.get('/api/notifications').status_code==401
    assert client.post('/api/notifications/read',json={'through_id':0}).status_code==401
    login(client)
    assert client.get('/api/notifications').json()['items']==[]
    iid=case(client)
    feed=client.get('/api/notifications').json()
    assert feed['unread_count']==1 and feed['items'][0]['incident_id']==iid
    assert feed['items'][0]['kind']=='created'


def test_reader_preferences_are_personal_and_do_not_acknowledge_incident(client):
    login(client);iid=case(client)
    latest=client.get('/api/notifications').json()['latest_id']
    login(client,'leitor@local.test')
    assert client.post('/api/notifications/read',json={'through_id':latest}).status_code==200
    assert client.get('/api/notifications').json()['unread_count']==0
    assert client.get(f'/api/incidents/{iid}').json()['status']=='open'
    assert client.patch(f'/api/incidents/{iid}',json={'status':'acknowledged'}).status_code==403
    client.post('/api/logout',json={})
    login(client,'leitor@local.test')
    assert client.get('/api/notifications').json()['unread_count']==0
    login(client)
    assert client.get('/api/notifications').json()['unread_count']==1


def test_new_arrival_after_snapshot_not_cleared_and_cursor_never_rewinds(client):
    login(client);case(client)
    first=client.get('/api/notifications').json()['latest_id']
    case(client)
    assert client.post('/api/notifications/read',json={'through_id':first}).status_code==200
    assert client.get('/api/notifications').json()['unread_count']==1
    second=client.get('/api/notifications').json()['latest_id']
    client.post('/api/notifications/read',json={'through_id':second})
    assert client.post('/api/notifications/read',json={'through_id':first}).json()['read_through_id']==second
    assert client.get('/api/notifications').json()['unread_count']==0


def test_bounded_keyset_pagination_and_excerpts(client):
    login(client);iid=case(client)
    with database(client.app.state.db_path) as db:
        for n in range(53):
            event(db,iid,'Teste','Prioridade elevada para P3' if n==0 else 'Responsável atribuído','x'*800)
        event(db,iid,'Teste','Nota de investigação','Private note must not become a notification')
    first=client.get('/api/notifications?limit=50').json()
    second=client.get('/api/notifications',params={'limit':50,'before_id':first['next_before_id']}).json()
    assert len(first['items'])==50 and len(second['items'])==4
    assert len({r['id'] for r in first['items']+second['items']})==54
    assert max(len(row['note']) for row in first['items'])==400
    assert all(row['note_truncated'] for row in first['items'])
    assert any(row['kind']=='priority' for row in second['items'])
    assert second['next_before_id'] is None
    assert client.get('/api/notifications?limit=51').status_code==422
    assert client.get('/api/notifications?before_id=9223372036854775808').status_code==422


@pytest.mark.parametrize('payload', [ {'through_id':True},{'through_id':-1},
    {'through_id':'3'},{'through_id':2**63},{'through_id':0,'user_id':2}])
def test_reject_invalid_or_cross_account_payload(client,payload):
    login(client)
    assert client.post('/api/notifications/read',json=payload).status_code==422


def test_no_future_cursor_or_non_notification_ids(client):
    login(client);iid=case(client)
    with database(client.app.state.db_path) as db:
        event(db,iid,'Teste','Nota de investigação','Not an eligible event')
        last=db.execute('SELECT max(id) FROM timeline').fetchone()[0]
    for value in (last,last+100,2**63-1):
        assert client.post('/api/notifications/read',json={'through_id':value}).status_code==409
    assert client.get('/api/notifications').json()['unread_count']==1


def test_existing_deadline_engine_emits_one_persistent_notification(client):
    login(client)
    path=client.app.state.db_path
    telemetry.initialize_targets(path)
    stamp=(datetime.now(timezone.utc)-timedelta(seconds=40)).isoformat()
    with database(path) as db:
        target=db.execute('SELECT service_id FROM telemetry_targets LIMIT 1').fetchone()[0]
        db.execute("INSERT INTO incidents(service_id,title,description,severity,status,source,created_at) VALUES(?,'Prazo de teste','Ensaio do motor existente','P2','open','prometheus-alert',?)",(target,stamp))
        config=AlertRuleInput(escalation_enabled=True,acknowledge_seconds=15).model_dump_json()
        db.execute('INSERT INTO alert_rules VALUES(?,?,?,?)',(target,config,1,stamp))
    alerts.tick(path);alerts.tick(path)
    rows=client.get('/api/notifications').json()['items']
    deadline=[r for r in rows if r['kind']=='deadline']
    assert len(deadline)==1 and deadline[0]['severity']=='P1'
