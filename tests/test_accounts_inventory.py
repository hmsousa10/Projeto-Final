from concurrent.futures import ThreadPoolExecutor
import time

from fastapi.testclient import TestClient

from app.db import database, initialize
from app.main import create_app
from app import telemetry
from tests.test_workflow import client, login, create_incident, PASSWORD

INITIAL = 'Uma frase inicial longa 2026!'
NEW = ' Uma frase privada com espaços 2026! '


def create_user(client, email='nova@local.test', role='operator'):
    response=client.post('/api/admin/users',json={'name':'Nova conta','email':email,'role':role,'password':INITIAL})
    assert response.status_code==201,response.text
    return response.json()


def details(user, **updates):
    return {**{k:user[k] for k in ('name','email','role')},'active':True,**updates}


def test_new_account_must_change_password_and_spaces_are_preserved(client):
    login(client)
    account=create_user(client)
    assert account['must_change_password']==1 and 'password' not in account
    result=client.post('/api/login',json={'email':account['email'],'password':INITIAL})
    assert result.status_code==200 and result.json()['must_change_password']==1
    assert client.get('/api/me').status_code==200
    assert client.get('/api/services').status_code==403
    assert client.post('/api/incidents',json={'service_id':1,'title':'Não autorizado','description':'Não pode operar antes da alteração.'}).status_code==403
    assert client.post('/api/account/password',json={'current_password':INITIAL,'new_password':NEW}).status_code==200
    assert client.get('/api/services').status_code==200
    client.post('/api/logout')
    assert client.post('/api/login',json={'email':account['email'],'password':NEW.strip()}).status_code==401
    assert client.post('/api/login',json={'email':account['email'],'password':NEW}).status_code==200


def test_password_change_revokes_other_sessions_and_old_password(client):
    login(client)
    with TestClient(client.app,base_url='http://localhost') as other:
        login(other)
        assert client.post('/api/account/password',json={'current_password':PASSWORD,'new_password':NEW}).status_code==200
        assert client.get('/api/me').status_code==200
        assert other.get('/api/me').status_code==401
        assert other.post('/api/login',json={'email':'admin@local.test','password':PASSWORD}).status_code==401
        assert other.post('/api/login',json={'email':'admin@local.test','password':NEW}).status_code==200
    with database(client.app.state.db_path) as db:
        log=' '.join(r['detail'] for r in db.execute('SELECT detail FROM audit'))
        assert NEW not in log and PASSWORD not in log


def test_password_change_rate_limit_persists_across_sessions(client):
    login(client)
    for _ in range(5):
        assert client.post('/api/account/password',json={'current_password':'errada','new_password':NEW}).status_code==400
    login(client)
    assert client.post('/api/account/password',json={'current_password':PASSWORD,'new_password':NEW}).status_code==429


def test_no_password_echo_in_validation_errors_or_account_lists(client):
    login(client)
    for password in ('curta','123456789012345',PASSWORD):
        response=client.post('/api/admin/users',json={'name':'Conta','email':'x@local.test','role':'viewer','password':password})
        assert response.status_code==422
        assert password not in response.text
    assert client.post('/api/admin/users',json={'name':'Conta','email':'nao-email','password':INITIAL}).status_code==422
    create_user(client)
    assert client.post('/api/admin/users',json={'name':'Duplicada','email':'NOVA@LOCAL.TEST','password':INITIAL}).status_code==409
    body=client.get('/api/admin/users').text
    assert INITIAL not in body and 'password_hash' not in body


def test_role_changes_revoke_sessions_and_non_admin_cannot_manage(client):
    login(client)
    users=client.get('/api/admin/users').json()
    operator=next(u for u in users if u['role']=='operator')
    with TestClient(client.app,base_url='http://localhost') as other:
        login(other,'operacoes@local.test')
        assert other.get('/api/admin/users').status_code==403
        assert other.put('/api/admin/users/1',json=details(users[0],role='viewer')).status_code==403
        assert client.put(f'/api/admin/users/{operator["id"]}',json=details(operator,role='viewer')).status_code==200
        assert other.get('/api/me').status_code==401
        login(other,'operacoes@local.test')
        assert other.post('/api/incidents',json={'service_id':1,'title':'Falha demonstrada','description':'Este perfil não pode criar incidentes.'}).status_code==403


def test_deactivation_rejects_login_and_preserves_historical_attribution(client):
    login(client)
    operator=next(u for u in client.get('/api/admin/users').json() if u['role']=='operator')
    iid=create_incident(client)
    assert client.post(f'/api/incidents/{iid}/assign',json={'user_id':operator['id']}).status_code==200
    assert client.put(f'/api/admin/users/{operator["id"]}',json=details(operator,active=False)).status_code==409
    assert client.put(f'/api/admin/users/{operator["id"]}',json=details(operator,role='viewer')).status_code==409
    for state in ('acknowledged','investigating','resolved'):
        assert client.patch(f'/api/incidents/{iid}',json={'status':state,'note':'Falha resolvida no ensaio académico.'}).status_code==200
    assert client.put(f'/api/admin/users/{operator["id"]}',json=details(operator,active=False)).status_code==200
    assert client.get(f'/api/incidents/{iid}').json()['assignee_id']==operator['id']
    another=create_incident(client)
    assert client.post(f'/api/incidents/{another}/assign',json={'user_id':operator['id']}).status_code==422
    assert client.post('/api/login',json={'email':operator['email'],'password':PASSWORD}).status_code==401


def test_last_admin_is_protected_even_under_concurrent_updates(client):
    login(client)
    root=next(u for u in client.get('/api/admin/users').json() if u['id']==1)
    assert client.put('/api/admin/users/1',json=details(root,active=False)).status_code==409
    assert client.put('/api/admin/users/1',json=details(root,role='viewer')).status_code==409
    second=create_user(client,'second@local.test','admin')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda u:client.put(f'/api/admin/users/{u["id"]}',json=details(u,active=False)).status_code,[root,second]))
    assert results.count(200)==1 and all(code in (200,401,409) for code in results)
    with database(client.app.state.db_path) as db:
        assert db.execute("SELECT count(*) FROM users WHERE active=1 AND role='admin'").fetchone()[0]==1


def new_service(client,name):
    return client.post('/api/services',json={'name':name,'team':'Operações'}).json()


def service_values(row, **updates):
    return {**{key:row[key] for key in ('name','team','description','criticality','slo_availability','slo_latency_ms')},'dependencies':[],**updates}


def test_service_edit_preserves_mapping_observations_and_incident_history(client):
    login(client)
    telemetry.initialize_targets(client.app.state.db_path)
    sid=next(s['id'] for s in client.get('/api/services').json() if s['monitoring'] and s['monitoring']['target_key']=='portal-lab')
    stamp=time.time()
    series=[{'metric':{'service_key':'portal-lab','__name__':name},'values':[[stamp,value]]} for name,value in [('probe_success','1'),('probe_duration_seconds','0.01')]]
    telemetry.import_samples(client.app.state.db_path,series)
    old=next(s for s in client.get('/api/services').json() if s['id']==sid)
    iid=client.post('/api/incidents',json={'service_id':sid,'title':'Investigação de serviço','description':'Acompanhamento da alteração do inventário.'}).json()['id']
    response=client.put(f'/api/services/{sid}',json=service_values(old,name='Portal atualizado',team='Equipa nova',slo_latency_ms=600))
    assert response.status_code==200
    changed=next(s for s in client.get('/api/services').json() if s['id']==sid)
    assert changed['id']==sid and changed['monitoring']['target_key']=='portal-lab'
    assert changed['sample_count']==old['sample_count'] and changed['status']=='unknown'
    assert any(t['action']=='Inventário atualizado' for t in client.get(f'/api/incidents/{iid}').json()['timeline'])


def test_service_edits_reject_self_indirect_cycles_duplicates_and_missing_ids(client):
    login(client)
    a,b,c=[new_service(client,name) for name in ('Serviço A','Serviço B','Serviço C')]
    assert client.put(f'/api/services/{b["id"]}',json=service_values(b,dependencies=[a['id']])).status_code==200
    assert client.put(f'/api/services/{c["id"]}',json=service_values(c,dependencies=[b['id']])).status_code==200
    assert client.put(f'/api/services/{a["id"]}',json=service_values(a,dependencies=[c['id']])).status_code==422
    assert client.put(f'/api/services/{a["id"]}',json=service_values(a,dependencies=[a['id']])).status_code==422
    assert client.put(f'/api/services/{a["id"]}',json=service_values(a,dependencies=[99999])).status_code==404
    assert client.put(f'/api/services/{a["id"]}',json=service_values(a,name=b['name'])).status_code==409
    assert client.put('/api/services/99999',json=service_values(a)).status_code==404
    login(client,'operacoes@local.test')
    assert client.put(f'/api/services/{a["id"]}',json=service_values(a)).status_code==403


def test_concurrent_dependency_edits_cannot_introduce_cycle(client):
    login(client)
    a,b=[new_service(client,name) for name in ('Serviço A','Serviço B')]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda pair:client.put(f'/api/services/{pair[0]["id"]}',json=service_values(pair[0],dependencies=[pair[1]['id']])).status_code,[(a,b),(b,a)]))
    assert sorted(results)==[200,422]


def test_legacy_accounts_migrate_without_forcing_unrequested_password_change(tmp_path):
    path=tmp_path/'legacy.db'
    initialize(path)
    initialize(path)
    with database(path) as db:
        columns={r['name'] for r in db.execute('PRAGMA table_info(users)')}
        assert {'active','must_change_password'} <= columns
