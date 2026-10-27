from app.db import database
from tests.test_workflow import client, login
import pytest


def add_rows(client, count=205):
    with database(client.app.state.db_path) as db:
        for n in range(count):
            db.execute('INSERT INTO audit(actor,action,entity,detail,created_at) VALUES(?,?,?,?,?)',
                       ('Operador de teste','incident.comment',f'incident:{n+1}',f'AÇÃO confirmada {n}',
                        '2026-10-27T12:00:00+00:00'))


def test_admin_only_and_legacy_contract(client):
    assert client.get('/api/audit/events').status_code==401
    for email in ['operacoes@local.test','leitor@local.test']:
        login(client,email)
        assert client.get('/api/audit/events').status_code==403
    login(client)
    assert isinstance(client.get('/api/audit').json(),list)
    assert client.get('/api/audit/events').status_code==200


def test_keyset_reaches_history_beyond_200_and_freezes_snapshot(client):
    login(client);add_rows(client)
    params={'actor':'Operador de teste','limit':50}
    first=client.get('/api/audit/events',params=params).json()
    ids=[r['id'] for r in first['items']]
    add_rows(client,1)
    page=first
    while page['next_before_id']:
        params.update(before_id=page['next_before_id'],snapshot_id=first['snapshot_id'])
        page=client.get('/api/audit/events',params=params).json()
        ids.extend(r['id'] for r in page['items'])
    assert len(ids)==205 and len(set(ids))==205
    assert ids==sorted(ids,reverse=True)
    latest=client.get('/api/audit/events',params={'actor':'Operador de teste'}).json()
    assert latest['items'][0]['id']>first['snapshot_id']


def test_filters_exact_literal_and_unicode_search(client):
    login(client);add_rows(client,3)
    filters={'actor':'Operador de teste','action':'incident.comment','entity':'incident:2','q':'ação'}
    response=client.get('/api/audit/events',params=filters)
    assert response.status_code==200
    assert len(response.json()['items'])==1
    for params in [{'actor':"' OR 1=1 --"},{'q':'%'},{'q':'_'},{'action':'incident'},{'entity':'incident:99'}]:
        assert client.get('/api/audit/events',params=params).json()['items']==[]


def test_inclusive_utc_dates_and_no_mutation(client):
    login(client);add_rows(client,3)
    with database(client.app.state.db_path) as db:
        db.execute("INSERT INTO audit(actor,action,entity,detail,created_at) VALUES('Operador de teste','test','test','','2026-10-28T00:00:00+00:00')")
        before=db.execute('SELECT count(*) FROM audit').fetchone()[0]
    response=client.get('/api/audit/events',params={'actor':'Operador de teste','date_from':'2026-10-27','date_to':'2026-10-27'}).json()
    assert len(response['items'])==3 and response['date_timezone']=='UTC'
    assert client.get('/api/audit/events',params={'date_from':'2026-10-29','date_to':'2026-10-27'}).status_code==422
    with database(client.app.state.db_path) as db:
        assert db.execute('SELECT count(*) FROM audit').fetchone()[0]==before


@pytest.mark.parametrize('params',[
    {'limit':0},{'limit':101},{'before_id':0},{'snapshot_id':-1},
    {'before_id':9223372036854775808},{'date_from':'ontem'},{'q':'a'*201},{'actor':'a'*101},
])
def test_bounded_invalid_queries(client,params):
    login(client)
    assert client.get('/api/audit/events',params=params).status_code==422
