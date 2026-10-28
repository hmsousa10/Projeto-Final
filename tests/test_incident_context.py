import json

import pytest

from app import telemetry
from app.db import database
from tests.test_workflow import client, login


def add_history(client, count=250):
    with database(client.app.state.db_path) as db:
        for n in range(count):
            db.execute('''INSERT INTO incidents
                (service_id,title,description,severity,status,created_at,source,resolution,runbook)
                VALUES(1,?,?,'P3','closed','2026-10-28T12:00:00+00:00','manual',?,?)''',
                (f'Caso histórico {n}', 'Descrição interna. ' * 100, 'Resolução. ' * 100, 'Procedimento. ' * 100))


@pytest.mark.parametrize('email', ['admin@local.test', 'operacoes@local.test', 'leitor@local.test'])
def test_context_permissions_compact_fields_and_no_case_changes(client, email):
    assert client.get('/api/incidents/context').status_code == 401
    login(client, email)
    with database(client.app.state.db_path) as db:
        before = [tuple(r) for r in db.execute('SELECT * FROM incidents ORDER BY id')]
        timeline = db.execute('SELECT COUNT(*) FROM timeline').fetchone()[0]
    result = client.get('/api/incidents/context')
    assert result.status_code == 200
    context = result.json()
    assert context['limits'] == {'attention': 5, 'laboratory': 2, 'references': 100}
    assert context['references_more'] is False
    assert all(set(row) == {'id', 'title', 'status', 'source'} for row in context['references'])
    with database(client.app.state.db_path) as db:
        assert before == [tuple(r) for r in db.execute('SELECT * FROM incidents ORDER BY id')]
        assert timeline == db.execute('SELECT COUNT(*) FROM timeline').fetchone()[0]


def test_large_history_is_bounded_without_changing_legacy_api(client):
    login(client)
    add_history(client)
    result = client.get('/api/incidents/context').json()
    assert len(result['references']) == 100 and result['references_more'] is True
    with database(client.app.state.db_path) as db:
        expected = [r[0] for r in db.execute("SELECT id FROM incidents WHERE status IN ('resolved','closed') ORDER BY id DESC LIMIT 100")]
    assert [row['id'] for row in result['references']] == expected
    legacy = client.get('/api/incidents').json()
    assert len(legacy) == 253
    # Measure serialized payload on this fixture, not a claim about response time.
    assert len(json.dumps(result).encode()) < len(json.dumps(legacy).encode()) / 10
    for rows in [result['attention'], result['laboratory'], result['references']]:
        assert all(not {'description', 'resolution', 'runbook', 'password_hash', 'token_hash'} & row.keys() for row in rows)


def test_priority_queue_and_lab_case_outside_top_five(client):
    login(client)
    path = client.app.state.db_path
    telemetry.initialize_targets(path)
    with database(path) as db:
        for n in range(12):
            db.execute('''INSERT INTO incidents(service_id,title,description,severity,status,created_at)
                VALUES(1,?,'','P2','open',?)''', (f'Caso ativo {n}', f'2026-10-28T12:00:{n:02}+00:00'))
        urgent = db.execute('''INSERT INTO incidents(service_id,title,description,severity,status,created_at)
            VALUES(1,'Caso crítico antigo','','P1','open','2025-01-01T00:00:00+00:00')''').lastrowid
        sid = db.execute("SELECT service_id FROM telemetry_targets WHERE target_key='portal-lab'").fetchone()[0]
        lab_id = db.execute('''INSERT INTO incidents(service_id,title,description,severity,status,created_at,source)
            VALUES(?,'Caso automático do laboratório','','P4','open','2026-10-28T12:00:00+00:00','prometheus-alert')''', (sid,)).lastrowid
    context = client.get('/api/incidents/context').json()
    assert len(context['attention']) == 5 and context['attention'][0]['id'] == urgent
    assert lab_id not in [r['id'] for r in context['attention']]
    assert [r['id'] for r in context['laboratory']] == [lab_id]
    assert context['laboratory'][0]['service_id'] == sid


def test_old_reference_outside_catalog_can_still_be_applied(client):
    login(client)
    add_history(client)
    context = client.get('/api/incidents/context').json()
    assert 1 not in [r['id'] for r in context['references']]
    case = client.post('/api/incidents', json={'service_id': 1, 'title': 'Investigação com caso anterior',
        'description': 'Consultar uma referência fora da lista recente.', 'severity': 'P2'}).json()
    assert client.get('/api/incidents/1').status_code == 200
    result = client.post(f"/api/incidents/{case['id']}/knowledge-use", json={
        'source_incident_id': 1, 'reason': 'Consultei o caso antigo e adaptei os passos de diagnóstico.'})
    assert result.status_code == 201 and result.json()['source_incident_id'] == 1
