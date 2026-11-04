from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db import database, initialize
from tests.test_workflow import client, login, create_incident


def test_stale_assignment_is_rejected_without_side_effects(client):
    login(client)
    iid = create_incident(client)
    revision = client.get(f'/api/incidents/{iid}').json()['revision']
    payload = {'user_id': 2, 'expected_revision': revision}
    assert client.post(f'/api/incidents/{iid}/assign', json=payload).status_code == 200
    with database(client.app.state.db_path) as db:
        before = [tuple(r) for r in db.execute('SELECT * FROM audit')]
        timeline = [tuple(r) for r in db.execute('SELECT * FROM timeline')]
    conflict = client.post(f'/api/incidents/{iid}/assign', json={**payload, 'user_id': 1})
    assert conflict.status_code == 409
    assert conflict.headers['X-Nexo-Conflict'] == 'incident-revision'
    with database(client.app.state.db_path) as db:
        assert before == [tuple(r) for r in db.execute('SELECT * FROM audit')]
        assert timeline == [tuple(r) for r in db.execute('SELECT * FROM timeline')]
        assert db.execute('SELECT assignee_id FROM incidents WHERE id=?', (iid,)).fetchone()[0] == 2


def test_concurrent_assignments_have_exactly_one_winner(client):
    login(client)
    iid = create_incident(client)
    revision = client.get(f'/api/incidents/{iid}').json()['revision']
    def write(uid):
        return client.post(f'/api/incidents/{iid}/assign', json={
            'user_id': uid, 'expected_revision': revision}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, [1, 2])) == [200, 409]


def test_stale_transition_can_be_retried_after_reading_current_version(client):
    login(client)
    iid = create_incident(client)
    revision = client.get(f'/api/incidents/{iid}').json()['revision']
    assert client.post(f'/api/incidents/{iid}/assign', json={'user_id': 2}).status_code == 200
    payload = {'status': 'acknowledged', 'expected_revision': revision}
    assert client.patch(f'/api/incidents/{iid}', json=payload).status_code == 409
    current = client.get(f'/api/incidents/{iid}').json()
    assert current['status'] == 'open'
    response = client.patch(f'/api/incidents/{iid}', json={**payload, 'expected_revision': current['revision']})
    assert response.status_code == 200
    assert response.json()['revision'] > current['revision']


@pytest.mark.parametrize('revision', [-1, True, '0', 0.5, 9007199254740992])
def test_invalid_revisions_are_rejected(client, revision):
    login(client)
    iid = create_incident(client)
    assert client.post(f'/api/incidents/{iid}/assign', json={
        'user_id': 2, 'expected_revision': revision}).status_code == 422


def test_authentication_and_viewer_permissions_still_apply(client):
    assert client.post('/api/incidents/1/assign', json={'user_id': 2, 'expected_revision': 0}).status_code == 401
    login(client, 'leitor@local.test')
    assert client.post('/api/incidents/1/assign', json={'user_id': 2, 'expected_revision': 0}).status_code == 403


def test_revision_trigger_covers_background_updates_and_is_idempotent(client):
    iid = 1
    path = client.app.state.db_path
    with database(path) as db:
        original = dict(db.execute('SELECT * FROM incidents WHERE id=?', (iid,)).fetchone())
        db.execute('UPDATE incidents SET severity=? WHERE id=?', ('P4', iid))
    initialize(path)
    initialize(path)
    with database(path) as db:
        current = dict(db.execute('SELECT * FROM incidents WHERE id=?', (iid,)).fetchone())
        assert current['revision'] == original['revision'] + 1
        assert current['title'] == original['title']
        # Even recursive triggers cannot loop: the inner UPDATE changes the revision.
        db.execute('PRAGMA recursive_triggers=ON')
        db.execute('UPDATE incidents SET severity=? WHERE id=?', ('P3', iid))
        assert db.execute('SELECT revision FROM incidents WHERE id=?', (iid,)).fetchone()[0] == current['revision'] + 1

def test_existing_database_migrates_without_losing_history(tmp_path):
    path = tmp_path / 'legacy.db'
    initialize(path)
    with database(path) as db:
        db.execute('DROP TRIGGER incident_revision')
        db.execute('ALTER TABLE incidents DROP COLUMN revision')
        db.execute("INSERT INTO services(id,name,team,description,criticality,slo_availability,slo_latency_ms,created_at) VALUES(1,'API','Operações','','Alta',99.9,500,'2026-11-04')")
        db.execute("INSERT INTO incidents(id,service_id,title,description,severity,status,created_at) VALUES(1,1,'Caso anterior','Histórico preservado','P1','open','2026-11-04')")
        db.execute("INSERT INTO timeline(incident_id,actor,action,note,created_at) VALUES(1,'Operador','Incidente criado','Nota anterior','2026-11-04')")
        before = dict(db.execute('SELECT * FROM incidents').fetchone())
        history = [tuple(r) for r in db.execute('SELECT * FROM timeline')]
    initialize(path)
    initialize(path)
    with database(path) as db:
        after = dict(db.execute('SELECT * FROM incidents').fetchone())
        assert after.pop('revision') == 0
        assert after == before
        assert history == [tuple(r) for r in db.execute('SELECT * FROM timeline')]
        db.execute("UPDATE incidents SET assignee_id=NULL WHERE id=1")
        assert db.execute('SELECT revision FROM incidents').fetchone()[0] == 1
