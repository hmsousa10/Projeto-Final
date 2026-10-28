"""Durable collection binding for the authenticated business API."""
import asyncio
import hashlib
import json
import logging
import math
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import Field

from .db import audit, database, event, now
from .models import Input

KEY = 'enterprise_monitoring_binding'
SOURCE = 'enterprise-api'
INCIDENT_SOURCE = 'enterprise-alert'


def binding(db):
    row = db.execute('SELECT value FROM settings WHERE key=?', (KEY,)).fetchone()
    return json.loads(row[0]) if row else None


def save(db, value):
    db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)', (KEY, json.dumps(value)))


def target(db):
    value = binding(db)
    if not value or not value['configured'] or not value['enabled']:
        return None
    state = db.execute("SELECT value FROM settings WHERE key='enterprise_monitoring_state'").fetchone()
    api_status = json.loads(state[0]).get('api_status', 'waiting') if state else 'waiting'
    return {**value, 'target_key': 'enterprise-' + value['company_id'], 'api_status': api_status,
            'observation_source': SOURCE, 'incident_source': INCIDENT_SOURCE,
            'origin_label': 'API empresarial autenticada'}


def configure(path, client):
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        previous = binding(db)
        if not client.url:
            if previous:
                save(db, {**previous, 'configured': False, 'enabled': False, 'updated_at': now()})
            return
        fingerprint = hashlib.sha256((client.company_id + '|' + client.url).encode()).hexdigest()
        if previous and previous['fingerprint'] != fingerprint:
            raise RuntimeError('Esta base tem histórico de outra API empresarial. Usa uma base separada ou uma migração explícita.')
        connector_id = client.connector.id
        if previous and previous.get('connector_id', 'orders-summary-v1') != connector_id:
            raise RuntimeError('Esta base tem histórico de outro conector empresarial. Usa uma base separada ou uma migração explícita.')
        if previous:
            if not db.execute('SELECT 1 FROM services WHERE id=?', (previous['service_id'],)).fetchone():
                raise RuntimeError('O serviço da integração empresarial não existe nesta base.')
            value = {**previous, 'connector_id': connector_id, 'configured': True, 'updated_at': now(), 'last_sample': ''}
        else:
            name = client.company_id.capitalize() + ' · API de operações'
            if db.execute('SELECT 1 FROM services WHERE name=?', (name,)).fetchone():
                name += ' · ' + fingerprint[:8]
            sid = db.execute('''INSERT INTO services
                (name,team,description,criticality,slo_availability,slo_latency_ms,created_at)
                VALUES(?,?,?,'Alta',99.9,500,?)''',
                (name, 'Operações ' + client.company_id.capitalize(),
                 'Resumo autenticado validado pelo conector ' + connector_id + '.', now())).lastrowid
            value = {'service_id': sid, 'company_id': client.company_id, 'connector_id': connector_id, 'fingerprint': fingerprint,
                     'configured': True, 'enabled': True, 'updated_at': now(), 'last_sample': ''}
            audit(db, 'Instalação', 'enterprise.service.created', f'service:{sid}', 'Ligação autenticada de leitura.')
        save(db, value)


def touch(db, sid):
    value = binding(db)
    if value and value['service_id'] == sid:
        save(db, {**value, 'updated_at': now(), 'last_sample': ''})


def pause_for_restore(db):
    value = binding(db)
    if value:
        save(db, {**value, 'enabled': False, 'updated_at': now(), 'last_sample': ''})


def record(path, result, epoch):
    if result['status'] not in ('connected', 'unavailable', 'unauthorized', 'invalid_payload', 'stale'):
        return 0
    stamp = datetime.fromisoformat(result['checked_at'])
    clock = datetime.now(timezone.utc)
    latency = result.get('latency_ms', 0)
    if stamp.tzinfo is None or not -5 <= (clock - stamp).total_seconds() <= 45 or not isinstance(latency, (int, float)) or not math.isfinite(latency) or not 0 <= latency <= 120000:
        return 0
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        current = target(db)
        if not current or current['updated_at'] != epoch or result['checked_at'] < epoch or result['checked_at'] <= current['last_sample']:
            return 0
        db.execute('''INSERT INTO observations(service_id,available,latency_ms,source,observed_at)
            VALUES(?,?,?,?,?)''', (current['service_id'], int(result['status'] == 'connected'), latency, SOURCE, result['checked_at']))
        value = binding(db)
        save(db, {**value, 'last_sample': result['checked_at']})
        db.execute("INSERT OR REPLACE INTO settings VALUES('enterprise_monitoring_state',?)",
                   (json.dumps({'last_attempt': result['checked_at'], 'api_status': result['status']}),))
        from .alerts import evaluate
        evaluate(db, clock.timestamp())
    return 1


def collect(path, client):
    from .maintenance import blocks_writes
    if blocks_writes(path):
        return 0
    with database(path) as db:
        current = target(db)
    if not current:
        return 0
    return record(path, client.fetch(), current['updated_at'])


async def run(path, client):
    while True:
        try:
            await asyncio.to_thread(collect, path, client)
        except Exception:
            logging.getLogger(__name__).error('Recolha da API empresarial indisponível; será tentada novamente.')
        await asyncio.sleep(10)


def status(path):
    with database(path) as db:
        value = binding(db)
        if not value:
            return {'enabled': False, 'collection_state': 'disabled'}
        from .alerts import rule_for
        state = db.execute("SELECT value FROM settings WHERE key='enterprise_monitoring_state'").fetchone()
        state = json.loads(state['value']) if state else {}
        active = db.execute("SELECT id FROM incidents WHERE service_id=? AND source=? AND status NOT IN ('resolved','closed') ORDER BY id DESC LIMIT 1", (value['service_id'], INCIDENT_SOURCE)).fetchone()
        fresh = bool(value['last_sample']) and (datetime.now(timezone.utc) - datetime.fromisoformat(value['last_sample'])).total_seconds() <= 45
        collection = 'disabled' if not value['configured'] else 'paused' if not value['enabled'] else 'waiting' if not value['last_sample'] else 'running' if fresh else 'stale'
        return {'enabled': value['enabled'] and value['configured'], 'configured': value['configured'],
                'service_id': value['service_id'], 'collection_state': collection,
                'last_sample': value['last_sample'] or None, 'interval_seconds': 10,
                'freshness_seconds': 45, 'active_incident_id': active['id'] if active else None,
                'rule': rule_for(db, value['service_id']), **state}


class Toggle(Input):
    enabled: bool = Field(strict=True)


def routes(app, path, client, admin):
    @app.put('/api/enterprise/monitoring')
    def toggle(data: Toggle, user=Depends(admin)):
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            value = binding(db)
            if not client.url or not value or not value['configured']:
                raise HTTPException(409, 'A integração empresarial não está configurada.')
            if value['enabled'] != data.enabled:
                save(db, {**value, 'enabled': data.enabled, 'updated_at': now(), 'last_sample': ''})
                db.execute('DELETE FROM alert_states WHERE service_id=?', (value['service_id'],))
                audit(db, user['name'], 'enterprise.monitoring.resumed' if data.enabled else 'enterprise.monitoring.paused', f"service:{value['service_id']}")
                for row in db.execute("SELECT id FROM incidents WHERE service_id=? AND source=? AND status NOT IN ('resolved','closed')", (value['service_id'], INCIDENT_SOURCE)):
                    event(db, row['id'], user['name'], 'Recolha da API retomada' if data.enabled else 'Recolha da API pausada', 'A retoma exige novas consultas; a pausa não confirma recuperação.')
        return status(path)
