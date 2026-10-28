import pytest

from app.db import database
from tests.test_workflow import client, login


def add_cases(client, count=1):
    with database(client.app.state.db_path) as db:
        ids = []
        for n in range(count):
            cursor = db.execute('''INSERT INTO incidents
                (service_id,title,description,severity,status,assignee_id,created_at,source)
                VALUES(1,?,'AÇÃO com timeout HTTP 503','P2','investigating',2,?, 'manual')''',
                (f'Caso de validação {n}', '2026-10-28T23:59:59+00:00'))
            ids.append(cursor.lastrowid)
        return ids


def test_all_roles_can_read_without_changing_cases(client):
    assert client.get('/api/incidents/browse').status_code == 401
    ids = add_cases(client)
    with database(client.app.state.db_path) as db:
        before = [tuple(r) for r in db.execute('SELECT * FROM incidents ORDER BY id')]
        timeline = db.execute('SELECT count(*) FROM timeline').fetchone()[0]
    for email in ['admin@local.test', 'operacoes@local.test', 'leitor@local.test']:
        login(client, email)
        result = client.get('/api/incidents/browse', params={'view': 'all'}).json()
        assert result['items'][0]['id'] == ids[0]
        assert not any('password' in key or 'token' in key for item in result['items'] for key in item)
    assert isinstance(client.get('/api/incidents').json(), list)  # Original API contract.
    with database(client.app.state.db_path) as db:
        assert before == [tuple(r) for r in db.execute('SELECT * FROM incidents ORDER BY id')]
        assert timeline == db.execute('SELECT count(*) FROM timeline').fetchone()[0]


def test_keyset_reaches_old_cases_and_excludes_new_insertions(client):
    login(client)
    ids = add_cases(client, 123)
    params = {'view': 'all', 'limit': 17}
    first = client.get('/api/incidents/browse', params=params).json()
    assert first['items'][0]['id'] == ids[-1]
    new_id = add_cases(client)[0]
    found = [r['id'] for r in first['items']]
    page = first
    while page['next_before_id']:
        page = client.get('/api/incidents/browse', params={**params,
            'before_id': page['next_before_id'], 'snapshot_id': first['snapshot_id']}).json()
        assert len(page['items']) <= 17
        found.extend(r['id'] for r in page['items'])
    with database(client.app.state.db_path) as db:
        expected = [r[0] for r in db.execute('SELECT id FROM incidents WHERE id <= ? ORDER BY id DESC', (first['snapshot_id'],))]
    assert found == expected and new_id not in found
    assert client.get('/api/incidents/browse', params={'view': 'all'}).json()['items'][0]['id'] == new_id


def test_combined_filters_and_unassigned(client):
    login(client)
    iid = add_cases(client)[0]
    params = {'view': 'active', 'status': 'investigating', 'severity': 'P2',
              'service_id': 1, 'assignee_id': 2, 'scope': 'operational',
              'date_from': '2026-10-28', 'date_to': '2026-10-28', 'q': 'ação'}
    response = client.get('/api/incidents/browse', params=params).json()
    assert [r['id'] for r in response['items']] == [iid]
    assert response['date_timezone'] == 'UTC'
    for field, value in [('severity', 'P1'), ('service_id', 2), ('assignee_id', 0),
                         ('scope', 'examples'), ('date_from', '2026-10-29'), ('view', 'history')]:
        if field == 'date_from':
            selection = {**params, field: value, 'date_to': value}
        else:
            selection = {**params, field: value}
        assert client.get('/api/incidents/browse', params=selection).json()['items'] == []
    with database(client.app.state.db_path) as db:
        db.execute('UPDATE incidents SET assignee_id=NULL WHERE id=?', (iid,))
    assert client.get('/api/incidents/browse', params={**params, 'assignee_id': 0}).json()['items'][0]['id'] == iid


def test_text_and_exact_incident_number_are_literal(client):
    login(client)
    iid = add_cases(client)[0]
    for q in [f'INC-{iid:05}', str(iid), '  açÃo  ', 'timeout HTTP']:
        items = client.get('/api/incidents/browse', params={'view': 'all', 'q': q}).json()['items']
        assert any(r['id'] == iid for r in items)
    for q in ["' OR 1=1 --", '%', '_', '9' * 200]:
        response = client.get('/api/incidents/browse', params={'view': 'all', 'q': q})
        assert response.status_code == 200 and response.json()['items'] == []
    # Literal search includes service and assignee names, without returning authentication records.
    for key in ['service_name', 'assignee_name']:
        item = client.get('/api/incidents/browse', params={'view': 'all', 'q': str(iid)}).json()['items'][0]
        assert any(r['id'] == iid for r in client.get('/api/incidents/browse', params={'view': 'all', 'q': item[key]}).json()['items'])


def test_zero_snapshot_and_live_status_semantics(client):
    login(client)
    iid = add_cases(client)[0]
    assert client.get('/api/incidents/browse', params={'view': 'all', 'snapshot_id': 0}).json()['items'] == []
    first = client.get('/api/incidents/browse', params={'view': 'active'}).json()
    with database(client.app.state.db_path) as db:
        db.execute("UPDATE incidents SET status='closed' WHERE id=?", (iid,))
    # A cursor freezes the upper identifier, not mutable case content.
    response = client.get('/api/incidents/browse', params={'view': 'active', 'snapshot_id': first['snapshot_id']}).json()
    assert iid not in [r['id'] for r in response['items']]


@pytest.mark.parametrize('params', [
    {'view': 'invalid'}, {'status': 'deleted'}, {'severity': 'P0'}, {'scope': 'unknown'},
    {'limit': 0}, {'limit': 101}, {'before_id': 0}, {'snapshot_id': -1},
    {'service_id': 0}, {'assignee_id': -1}, {'before_id': 2**63},
    {'q': 'a' * 201}, {'date_from': 'ontem'},
    {'date_from': '2026-10-29', 'date_to': '2026-10-28'},
])
def test_invalid_queries(client, params):
    login(client)
    assert client.get('/api/incidents/browse', params=params).status_code == 422
