import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import enterprise_monitoring as em
from app.db import database
from app.main import create_app
from tests.test_enterprise import upstream, TOKEN
from tests.test_workflow import login


@pytest.fixture
def environment(upstream, tmp_path, monkeypatch):
    url, state = upstream
    key = tmp_path / 'read.key'
    key.write_text(TOKEN)
    monkeypatch.setenv('ENTERPRISE_API_URL', url)
    monkeypatch.setenv('ENTERPRISE_API_TOKEN_FILE', str(key))

    async def idle(*args):
        await asyncio.Event().wait()

    monkeypatch.setattr(em, 'run', idle)
    with TestClient(create_app(tmp_path / 'nexo.db', demo=True), base_url='http://localhost') as client:
        login(client)
        path = client.app.state.db_path
        with database(path) as db:
            value = em.binding(db)
            epoch = (datetime.now(timezone.utc) - timedelta(seconds=21)).isoformat()
            em.save(db, {**value, 'updated_at': epoch})
        yield client, path, value['service_id'], epoch, state


def result(n, status='unavailable', latency=10):
    # Recent isolated test samples. Production samples come from EnterpriseClient.
    stamp = datetime.now(timezone.utc) - timedelta(seconds=20-n*5)
    return {'status': status, 'checked_at': stamp.isoformat(), 'latency_ms': latency}


def automatic(client):
    return [i for i in client.get('/api/incidents').json() if i['source'] == em.INCIDENT_SOURCE]


def test_confirm_failure_recovery_and_complete_case(environment):
    client, path, sid, epoch, _ = environment
    assert em.record(path, result(0), epoch) == 1
    assert not automatic(client)
    assert em.record(path, result(1, 'unauthorized'), epoch) == 1
    incident = automatic(client)[0]
    assert incident['service_id'] == sid and incident['severity'] == 'P1'
    assert 'API empresarial autenticada' in incident['description']
    iid = incident['id']
    login(client, 'operacoes@local.test')
    assert client.post(f'/api/incidents/{iid}/assign', json={'user_id': 2}).status_code == 200
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'acknowledged'}).status_code == 200
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'investigating'}).status_code == 200
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'resolved', 'note': 'Consulta voltou a ser válida.'}).status_code == 409
    assert em.record(path, result(2, 'connected'), epoch) == 1
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'resolved', 'note': 'Consulta voltou a ser válida.'}).status_code == 409
    assert em.record(path, result(3, 'connected'), epoch) == 1
    assert client.get(f'/api/incidents/{iid}').json()['status'] == 'investigating'
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'resolved', 'note': 'Duas consultas válidas e recentes confirmaram a recuperação.'}).status_code == 200
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'closed', 'root_cause': 'Falha controlada da API no ensaio isolado.', 'prevention': 'Validar autenticação e contrato da API antes de disponibilizar.'}).status_code == 200
    exported = client.get(f'/api/incidents/{iid}/export?format=json').json()['incident']
    assert exported['source'] == em.INCIDENT_SOURCE and exported['detection_context']
    assert any(e['action'] == 'Serviço recuperado' for e in exported['timeline'])
    assert client.get('/api/notifications').json()['items']


def test_dedup_busy_and_pause_race(environment):
    client, path, sid, epoch, _ = environment
    sample = result(0)
    assert em.record(path, sample, epoch) == 1
    assert em.record(path, sample, epoch) == 0
    assert em.record(path, result(1, 'busy'), epoch) == 0
    login(client, 'leitor@local.test')
    assert client.put('/api/enterprise/monitoring', json={'enabled': False}).status_code == 403
    login(client)
    assert client.put('/api/enterprise/monitoring', json={'enabled': False}).status_code == 200
    assert em.record(path, result(1), epoch) == 0
    assert client.put('/api/enterprise/monitoring', json={'enabled': True}).status_code == 200
    assert em.record(path, result(1), epoch) == 0
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM observations WHERE service_id=?', (sid,)).fetchone()[0] == 1
    assert not automatic(client)


def test_latency_escalates_then_recovers(environment):
    client, path, sid, epoch, _ = environment
    em.record(path, result(0, 'connected', 900), epoch)
    em.record(path, result(1, 'connected', 900), epoch)
    iid = automatic(client)[0]['id']
    assert automatic(client)[0]['severity'] == 'P2'
    em.record(path, result(2, 'invalid_payload'), epoch)
    em.record(path, result(3, 'stale'), epoch)
    assert len(automatic(client)) == 1 and automatic(client)[0]['severity'] == 'P1'
    em.record(path, result(4, 'connected'), epoch)
    em.record(path, result(5, 'connected'), epoch)
    assert any(e['action'] == 'Serviço recuperado' for e in client.get(f'/api/incidents/{iid}').json()['timeline'])


def test_recurrence_uses_existing_incident(environment):
    client, path, _, epoch, _ = environment
    for n, state in enumerate(['unavailable', 'unavailable', 'connected', 'connected', 'unavailable', 'unavailable']):
        assert em.record(path, result(n, state), epoch) == 1
    cases = automatic(client)
    assert len(cases) == 1
    events = client.get(f"/api/incidents/{cases[0]['id']}").json()['timeline']
    assert sum(e['action'] == 'Falha recorrente agrupada' for e in events) == 1


def test_enterprise_incident_uses_acknowledgement_deadline(environment):
    import time
    from app.alerts import tick
    client, path, sid, epoch, _ = environment
    em.record(path, result(0, 'connected', 900), epoch)
    em.record(path, result(1, 'connected', 900), epoch)
    iid = automatic(client)[0]['id']
    rule = next(r for r in client.get('/api/alert-rules').json() if r['service_id'] == sid)['config']
    assert client.put(f'/api/services/{sid}/alert-rule', json={**rule, 'escalation_enabled': True, 'acknowledge_seconds': 15}).status_code == 200
    tick(path, time.time() + 1000)
    tick(path, time.time() + 1100)
    assert automatic(client)[0]['severity'] == 'P1'
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incident_escalations WHERE incident_id=?', (iid,)).fetchone()[0] == 1


def test_synthetic_scenarios_are_rejected_and_source_is_named(environment):
    client, _, sid, _, _ = environment
    assert client.post('/api/demo/scenario', json={'service_id': sid, 'kind': 'outage'}).status_code == 409
    service = next(s for s in client.get('/api/services').json() if s['id'] == sid)
    assert service['telemetry_source'] == 'enterprise' and service['enterprise_monitoring']['enabled']
    assert any(r['service_id'] == sid for r in client.get('/api/alert-rules').json())


def test_restore_keeps_enterprise_collection_paused(environment, tmp_path):
    import secrets
    from app.recovery import create, restore
    from app.enterprise import EnterpriseClient

    client, path, _, _, _ = environment
    key = secrets.token_bytes(32)
    archive, _ = create(path, key)
    restored = tmp_path / 'restored'
    restore(archive, key, restored)
    target = restored / 'nexo.db'
    with database(target) as db:
        assert em.binding(db)['enabled'] is False
    # A restart must not silently resume the restored binding.
    import os
    em.configure(target, EnterpriseClient(os.environ['ENTERPRISE_API_URL'], TOKEN))
    with database(target) as db:
        assert em.binding(db)['enabled'] is False
    assert em.status(target)['collection_state'] == 'paused'


def test_concurrent_cached_sample_is_recorded_once(environment):
    from concurrent.futures import ThreadPoolExecutor
    _, path, _, epoch, _ = environment
    sample = result(1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        inserted = list(pool.map(lambda _: em.record(path, sample, epoch), range(2)))
    assert sorted(inserted) == [0, 1]


def test_real_adapter_failure_is_collected_without_secret_material(environment):
    import os
    from app.enterprise import EnterpriseClient

    client, path, _, epoch, state = environment
    adapter = EnterpriseClient(os.environ['ENTERPRISE_API_URL'], TOKEN)
    state.update(status=503, body=b'private upstream error')
    assert em.collect(path, adapter) == 1
    adapter.cached_at = 0
    assert em.collect(path, adapter) == 1
    with database(path) as db:
        incident = db.execute('SELECT * FROM incidents WHERE source=?', (em.INCIDENT_SOURCE,)).fetchone()
        assert incident and TOKEN not in incident['description'] and 'private upstream' not in incident['description']
        assert 'target_url' not in db.execute('SELECT config FROM incident_alert_context WHERE incident_id=?', (incident['id'],)).fetchone()[0]
        assert 'unavailable' in db.execute('SELECT config FROM incident_alert_context WHERE incident_id=?', (incident['id'],)).fetchone()[0]
        iid = incident['id']
    assert client.post(f'/api/incidents/{iid}/assign', json={'user_id': 2}).status_code == 200
    for transition in ('acknowledged', 'investigating'):
        assert client.patch(f'/api/incidents/{iid}', json={'status': transition}).status_code == 200
    state.update(status=200, body=None)
    adapter.cached_at = 0
    assert em.collect(path, adapter) == 1
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'resolved', 'note': 'A API voltou a responder corretamente.'}).status_code == 409
    adapter.cached_at = 0
    assert em.collect(path, adapter) == 1
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'resolved', 'note': 'Duas respostas HTTP reais e válidas confirmam recuperação.'}).status_code == 200
    assert client.patch(f'/api/incidents/{iid}', json={'status': 'closed', 'root_cause': 'HTTP 503 controlado no servidor isolado do ensaio.', 'prevention': 'Validar contrato e autenticação da ligação de leitura.'}).status_code == 200
    exported = client.get(f'/api/incidents/{iid}/export?format=json').json()['incident']
    assert exported['status'] == 'closed' and any(e['action'] == 'Serviço recuperado' for e in exported['timeline'])
    # Re-enabling alerts during a failure must not leave the closed case as the active reference.
    sid = exported['service_id']
    rule = next(r for r in client.get('/api/alert-rules').json() if r['service_id'] == sid)['config']
    assert client.put(f'/api/services/{sid}/alert-rule', json={**rule, 'enabled': False}).status_code == 200
    state.update(status=503, body=b'controlled failure after closure')
    for _ in range(2):
        adapter.cached_at = 0
        assert em.collect(path, adapter) == 1
    assert len(automatic(client)) == 1
    assert client.put(f'/api/services/{sid}/alert-rule', json={**rule, 'enabled': True}).status_code == 200
    for _ in range(2):
        adapter.cached_at = 0
        assert em.collect(path, adapter) == 1
    cases = automatic(client)
    assert len(cases) == 2 and any(c['id'] != iid and c['status'] == 'open' for c in cases)
