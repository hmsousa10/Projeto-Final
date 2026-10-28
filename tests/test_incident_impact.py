import json
from concurrent.futures import ThreadPoolExecutor

from app.db import database, now
from app.incident_impact import ACTION, snapshot
from tests.test_workflow import client, login


def case(client):
    result = client.post('/api/incidents', json={'service_id': 4,
        'title': 'Investigação com dependências', 'description': 'Avaliar relações e estado observado do inventário.'})
    assert result.status_code == 201
    return result.json()['id']


def test_permissions_closed_cases_and_no_client_supplied_snapshot(client):
    assert client.post('/api/incidents/1/impact', json={}).status_code == 401
    login(client)
    iid = case(client)
    login(client, 'leitor@local.test')
    assert client.post(f'/api/incidents/{iid}/impact', json={}).status_code == 403
    login(client)
    assert client.post('/api/incidents/1/impact', json={}).status_code == 409
    assert client.post('/api/incidents/9999/impact', json={}).status_code == 404
    for body in [{'actor': 'Outra pessoa'}, {'root': {'status': 'healthy'}}, {'evaluated_at': 'ontem'}]:
        assert client.post(f'/api/incidents/{iid}/impact', json=body).status_code == 422
    assert not any(t['action'] == ACTION for t in client.get(f'/api/incidents/{iid}').json()['timeline'])


def test_server_snapshot_survives_inventory_changes_and_exports(client):
    login(client, 'operacoes@local.test')
    iid = case(client)
    with database(client.app.state.db_path) as db:
        db.execute('DELETE FROM dependencies WHERE service_id=1 AND depends_on_id=4')
        db.execute("INSERT INTO observations(service_id,available,latency_ms,source,observed_at) VALUES(1,0,10,'demo',?)", (now(),))
    before = client.get(f'/api/incidents/{iid}').json()
    response = client.post(f'/api/incidents/{iid}/impact', json={})
    assert response.status_code == 201 and response.json()['dependents'] == 3
    after = client.get(f'/api/incidents/{iid}').json()
    assert after['status'] == before['status'] and len(after['timeline']) == len(before['timeline']) + 1
    entry = after['timeline'][-1]
    assert entry['action'] == ACTION and entry['actor'] == 'Equipa de operações'
    record = json.loads(entry['note'])
    assert record['basis'] == 'current_inventory' and record['root']['id'] == 4
    portal = next(n for n in record['dependents'] if n['id'] == 1)
    assert portal['status'] == 'down' and portal['depth'] == 2 and portal['parent_id'] == 2
    assert portal['observation_source'] == 'demo' and portal['last_observed_at']
    assert not {'description', 'runbook', 'password_hash', 'target_url'} & portal.keys()
    with database(client.app.state.db_path) as db:
        db.execute("UPDATE services SET name='Portal com nome posterior' WHERE id=1")
        db.execute('DELETE FROM dependencies')
        assert db.execute("SELECT count(*) FROM audit WHERE action='incident.impact.captured' AND entity=?", (f'incident:{iid}',)).fetchone()[0] == 1
    assert client.get(f'/api/incidents/{iid}').json()['timeline'][-1] == entry
    exported = client.get(f'/api/incidents/{iid}/export?format=json').json()
    assert exported['incident']['timeline'][-1] == entry
    assert ACTION in client.get(f'/api/incidents/{iid}/export').text
    login(client, 'leitor@local.test')
    assert client.get(f'/api/incidents/{iid}').json()['timeline'][-1] == entry


def test_capture_limit_is_atomic(client):
    login(client)
    iid = case(client)
    with database(client.app.state.db_path) as db:
        for n in range(19):
            db.execute('INSERT INTO timeline(incident_id,actor,action,note,created_at) VALUES(?,?,?,?,?)',
                       (iid, 'Teste isolado', ACTION, '{}', now()))
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: client.post(f'/api/incidents/{iid}/impact', json={}).status_code, range(2)))
    assert sorted(statuses) == [201, 409]
    with database(client.app.state.db_path) as db:
        assert db.execute('SELECT count(*) FROM timeline WHERE incident_id=? AND action=?', (iid, ACTION)).fetchone()[0] == 20


def service(sid, dependencies):
    return {'id': sid, 'name': f'Serviço {sid}', 'team': 'Equipa', 'criticality': 'Alta',
            'status': 'unknown', 'dependencies': dependencies, 'latest': None}


def test_snapshot_cycles_truncation_and_projection():
    cyclic = [service(1, [3]), service(2, [1]), service(3, [2])]
    result = snapshot(cyclic, 1)
    assert [n['id'] for n in result['dependents']] == [2, 3]
    chain = [service(n, [n-1] if n > 1 else []) for n in range(1, 53)]
    result = snapshot(chain, 1)
    assert len(result['dependents']) == 50 and result['truncated'] is True
    assert result['dependents'][-1]['depth'] == 50
    assert len(json.dumps(result).encode()) < 64 * 1024
    assert snapshot(chain[:-1], 1)['truncated'] is False
    chain[0]['name'] = '<texto>' * 100
    assert snapshot(chain, 1)['text_truncated'] is True


def test_snapshot_missing_relationship_is_explicit():
    result = snapshot([service(1, []), service(2, [99])], 1)
    assert result['incomplete'] is True and not result['dependents']


def test_captured_impact_survives_encrypted_backup_and_restore(client, tmp_path):
    import secrets
    from app.recovery import create, restore

    login(client)
    iid = case(client)
    assert client.post(f'/api/incidents/{iid}/impact', json={}).status_code == 201
    entry = client.get(f'/api/incidents/{iid}').json()['timeline'][-1]
    key = secrets.token_bytes(32)
    archive, _ = create(client.app.state.db_path, key)
    target = tmp_path / 'impact-restored'
    restore(archive, key, target)
    with database(target / 'nexo.db') as db:
        restored = dict(db.execute('SELECT * FROM timeline WHERE id=?', (entry['id'],)).fetchone())
    assert restored == entry
