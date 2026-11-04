from concurrent.futures import ThreadPoolExecutor

from app.db import database
from tests.test_workflow import client, login, create_incident


def create_action(client,iid=1,**extra):
    return client.post(f'/api/incidents/{iid}/follow-ups',json={
        'title':'Acrescentar teste de recuperação','owner_id':2,'due_date':'2000-01-01',**extra})


def test_action_cycle_preserves_closed_case_and_exports(client):
    login(client)
    with database(client.app.state.db_path) as db:
        before=dict(db.execute('SELECT * FROM incidents WHERE id=1').fetchone())
    result=create_action(client);assert result.status_code==201,result.text
    action=result.json();assert action['overdue'] and action['status']=='open'
    response=client.post(f'/api/incidents/1/follow-ups/{action["id"]}/finish',json={
        'status':'completed','note':'Teste acrescentado e executado com sucesso.'})
    assert response.status_code==200,response.text
    assert not response.json()['overdue']
    assert response.json()['finished_by']=='Hugo Sousa'
    snapshot=client.get('/api/incidents/1').json()
    assert snapshot['follow_ups'][0]['status']=='completed'
    for format in ['json','markdown','html']:
        export=client.get(f'/api/incidents/1/export?format={format}')
        assert export.status_code==200
        assert 'Acrescentar teste de recuperação' in export.text
    with database(client.app.state.db_path) as db:
        assert dict(db.execute('SELECT * FROM incidents WHERE id=1').fetchone())==before
        assert db.execute("SELECT count(*) FROM audit WHERE action LIKE 'incident.followup.%'").fetchone()[0]==2


def test_authentication_and_reader_are_enforced(client):
    assert create_action(client).status_code==401
    login(client,'leitor@local.test')
    assert create_action(client).status_code==403
    assert client.post('/api/incidents/1/follow-ups/1/finish',json={'status':'cancelled','note':'Sem autorização para alterar.'}).status_code==403
    assert client.get('/api/incidents/1').json()['follow_ups']==[]


def test_only_recovered_cases_and_eligible_owners(client):
    login(client)
    active=create_incident(client)
    assert create_action(client,active).status_code==409
    assert create_action(client,999999).status_code==404
    assert create_action(client,owner_id=3).status_code==422
    assert create_action(client,owner_id=999999).status_code==404
    with database(client.app.state.db_path) as db:
        db.execute('UPDATE users SET active=0 WHERE id=2')
    assert create_action(client).status_code==422
    with database(client.app.state.db_path) as db:
        db.execute('UPDATE users SET active=1,must_change_password=1 WHERE id=2')
    assert create_action(client).status_code==422


def test_validation_rejects_invalid_dates_ids_and_extra_fields(client):
    login(client)
    for values in [{'due_date':'2026-02-30'},{'due_date':'04/11/2026'},{'due_date':123},
                   {'owner_id':True},{'owner_id':'2'},{'title':'x'},{'actor':'Outra pessoa'}]:
        assert create_action(client,**values).status_code==422
    assert client.get('/api/incidents/1').json()['follow_ups']==[]


def test_terminal_decision_is_atomic_and_scoped_to_case(client):
    login(client)
    aid=create_action(client).json()['id']
    assert client.post(f'/api/incidents/2/follow-ups/{aid}/finish',json={'status':'completed','note':'Caso errado para esta ação.'}).status_code==404
    def finish(status):
        return client.post(f'/api/incidents/1/follow-ups/{aid}/finish',json={
            'status':status,'note':'Decisão validada pela equipa de operações.'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(finish,['completed','cancelled']))==[200,409]
    assert finish('completed')==409
    with database(client.app.state.db_path) as db:
        assert db.execute("SELECT count(*) FROM timeline WHERE incident_id=1 AND action='Ação de prevenção terminada'").fetchone()[0]==1


def test_limit_and_persistence_are_based_on_history(client):
    login(client)
    for n in range(20):
        assert create_action(client,title=f'Prevenção número {n}').status_code==201
    assert create_action(client).status_code==409
    assert len(client.get('/api/incidents/1').json()['follow_ups'])==20
    client.post('/api/logout',json={});login(client)
    assert len(client.get('/api/incidents/1').json()['follow_ups'])==20

def test_deadline_today_and_owner_snapshot_survive_account_change(client,monkeypatch):
    from app import follow_ups
    login(client)
    monkeypatch.setattr(follow_ups,'now',lambda:'2026-11-04T12:00:00+00:00')
    action=create_action(client,due_date='2026-11-04').json()
    assert not action['overdue']
    with database(client.app.state.db_path) as db:
        db.execute("UPDATE users SET name='Nome posterior',active=0 WHERE id=2")
    read=client.get('/api/incidents/1').json()['follow_ups'][0]
    assert read['owner_name']=='Equipa de operações'
    for body in [{'status':'completed','note':'curta'},{'status':'open','note':'Não é permitida reabertura.'}]:
        assert client.post(f'/api/incidents/1/follow-ups/{action["id"]}/finish',json=body).status_code==422
    assert client.post('/api/incidents/9223372036854775808/follow-ups',json={
        'title':'Ação com limite','owner_id':2,'due_date':'2026-11-04'}).status_code==422


def test_actions_survive_encrypted_backup_and_isolated_restore(client,tmp_path):
    import secrets
    from app.recovery import create,restore
    from app.follow_ups import projection
    login(client)
    action=create_action(client).json()
    assert client.post(f'/api/incidents/1/follow-ups/{action["id"]}/finish',json={
        'status':'cancelled','note':'Medida substituída por uma ação mais adequada.'}).status_code==200
    before=client.get('/api/incidents/1').json()['follow_ups']
    key=secrets.token_bytes(32)
    archive,manifest=create(client.app.state.db_path,key)
    restore(archive,key,tmp_path/'restored')
    with database(tmp_path/'restored'/'nexo.db') as db:
        assert projection(db,1)==before
