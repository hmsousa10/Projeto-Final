"""Compatibility and customer isolation at the connector boundary."""
import json

import pytest

from app import enterprise, enterprise_monitoring as em
from app.db import database
from tests.test_enterprise import TOKEN, body, upstream
from tests.test_enterprise_monitoring import environment


def test_same_connector_supports_another_company_without_aurora_data(upstream):
    url, state = upstream
    payload = body()
    payload.update(company_id='empresa-exemplo', company_name='Empresa Exemplo')
    state['body'] = json.dumps(payload).encode()
    client = enterprise.EnterpriseClient(url, TOKEN, 'empresa-exemplo')
    result = client.fetch()
    assert result['status'] == 'connected'
    assert result['connector']['id'] == 'orders-summary-v1'
    assert result['connector']['summary_kind'] == 'orders'
    assert result['summary']['company_id'] == 'empresa-exemplo'
    assert enterprise.EnterpriseClient(url, TOKEN, 'aurora').fetch()['status'] == 'invalid_payload'
    assert TOKEN not in json.dumps(result) and url not in json.dumps(result)


@pytest.mark.parametrize('connector_id', ['', 'unknown', 'app.lab_service', '../orders'])
def test_configuration_never_loads_unknown_code(monkeypatch, connector_id):
    monkeypatch.setenv('ENTERPRISE_CONNECTOR', connector_id)
    monkeypatch.delenv('ENTERPRISE_API_URL', raising=False)
    monkeypatch.delenv('ENTERPRISE_API_TOKEN_FILE', raising=False)
    with pytest.raises(RuntimeError, match='Conector empresarial desconhecido'):
        enterprise.EnterpriseClient.configured()


def test_legacy_binding_adopts_connector_without_replacing_service_or_resuming(environment, monkeypatch):
    _, path, sid, _, _ = environment
    with database(path) as db:
        legacy = em.binding(db)
        legacy.pop('connector_id')
        legacy['enabled'] = False
        em.save(db, legacy)
        before = tuple(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                       for table in ('services', 'incidents', 'timeline', 'audit'))
    em.configure(path, enterprise.EnterpriseClient.configured())
    with database(path) as db:
        current = em.binding(db)
        assert current['service_id'] == sid and current['enabled'] is False
        assert current['connector_id'] == 'orders-summary-v1'
        after = tuple(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                      for table in ('services', 'incidents', 'timeline', 'audit'))
        assert before == after


@pytest.mark.parametrize('changed', ['company', 'url', 'connector'])
def test_existing_history_rejects_identity_change_atomically(environment, changed):
    _, path, _, _, _ = environment
    client = enterprise.EnterpriseClient.configured()
    with database(path) as db:
        if changed == 'connector':
            em.save(db, {**em.binding(db), 'connector_id': 'different-historical-contract'})
        original = em.binding(db)
    if changed == 'company':
        client.company_id = 'other-company'
    if changed == 'url':
        client.url += '/different-api'
    with pytest.raises(RuntimeError, match='histórico'):
        em.configure(path, client)
    with database(path) as db:
        assert em.binding(db) == original
