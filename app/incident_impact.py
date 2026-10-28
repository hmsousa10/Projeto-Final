"""Explicit, server-calculated snapshots of potential dependency impact."""
import json

from fastapi import Depends, HTTPException

from .db import audit, database, event, now
from .models import Input

ACTION = 'Impacto potencial preservado'
LIMIT = 50


class ImpactCapture(Input):
    """No client-supplied inventory, state, actor or timestamp is accepted."""


def snapshot(services, service_id):
    catalog = {s['id']: s for s in services}
    if service_id not in catalog:
        raise HTTPException(404, 'Serviço não encontrado no inventário.')
    reverse, incomplete = {}, False
    for service in catalog.values():
        for prerequisite in set(service['dependencies']):
            if prerequisite not in catalog:
                incomplete = True
                continue
            reverse.setdefault(prerequisite, set()).add(service['id'])
    record = {'schema_version': 1, 'evaluated_at': now(), 'basis': 'current_inventory',
              'limit': LIMIT, 'dependents': [], 'truncated': False,
              'incomplete': incomplete, 'text_truncated': False}

    def text(value, limit):
        value = str(value or '')
        if len(value) > limit:
            record['text_truncated'] = True
        return value[:limit]

    def project(service):
        latest = service.get('latest') or {}
        return {'id': service['id'], 'name': text(service['name'], 100),
                'team': text(service['team'], 100), 'criticality': text(service['criticality'], 10),
                'status': service['status'] if service['status'] in ('healthy', 'degraded', 'down', 'unknown') else 'unknown',
                'last_observed_at': text(latest.get('observed_at'), 40),
                'observation_source': text(latest.get('source'), 50)}

    record['root'] = project(catalog[service_id])
    queue, seen = [(service_id, 0)], {service_id}
    for current, depth in queue:
        for sid in sorted(reverse.get(current, ())):
            if sid in seen:
                continue
            seen.add(sid)
            if len(record['dependents']) == LIMIT:
                record['truncated'] = True
                return record
            record['dependents'].append({**project(catalog[sid]), 'depth': depth + 1,
                                         'parent_id': current})
            queue.append((sid, depth + 1))
    return record


def routes(app, path, writer, require, service_list):
    @app.post('/api/incidents/{iid}/impact', status_code=201)
    def capture(iid: int, data: ImpactCapture, user=Depends(writer)):
        with database(path) as db:
            # Serialize status/limit checks with other writers, including incident closure.
            db.execute('BEGIN IMMEDIATE')
            incident = require(db, 'incidents', iid)
            if incident['status'] == 'closed':
                raise HTTPException(409, 'O incidente está fechado.')
            count = db.execute('SELECT count(*) FROM timeline WHERE incident_id=? AND action=?',
                               (iid, ACTION)).fetchone()[0]
            if count >= 20:
                raise HTTPException(409, 'Limite de 20 avaliações de impacto atingido.')
            record = snapshot(service_list(db), incident['service_id'])
            payload = json.dumps(record, ensure_ascii=False, separators=(',', ':'))
            if len(payload.encode('utf-8')) > 64 * 1024:
                raise HTTPException(413, 'A avaliação excede o limite de tamanho permitido.')
            event(db, iid, user['name'], ACTION, payload)
            audit(db, user['name'], 'incident.impact.captured', f'incident:{iid}',
                  f"{len(record['dependents'])} dependentes preservados; lista parcial: {record['truncated']}")
            return {'ok': True, 'evaluated_at': record['evaluated_at'],
                    'dependents': len(record['dependents']), 'truncated': record['truncated']}
