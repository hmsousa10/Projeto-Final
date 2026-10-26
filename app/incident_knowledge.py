"""Authenticated recording of knowledge applied to an incident.

Owns the transaction that validates the reference and preserves its contents.
The timeline remains the source of truth; no separate mutable relationship.
"""
import json

from fastapi import Depends, HTTPException

from .db import audit, database, event
from .models import KnowledgeUse


def routes(app, path, writer, require):
    @app.post('/api/incidents/{iid}/knowledge-use', status_code=201)
    def record_knowledge_use(iid: int, data: KnowledgeUse, user=Depends(writer)):
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            target = require(db, 'incidents', iid)
            if target['status'] == 'closed':
                raise HTTPException(409, 'O incidente está fechado.')
            if iid == data.source_incident_id:
                raise HTTPException(422, 'Escolhe outro incidente como referência.')
            source = require(db, 'incidents', data.source_incident_id)
            if source['status'] not in ('resolved', 'closed'):
                raise HTTPException(409, 'O caso de referência tem de estar resolvido ou fechado.')
            previous = db.execute("SELECT note FROM timeline WHERE incident_id=? AND action='Conhecimento aplicado'", (iid,)).fetchall()
            if any(json.loads(r['note'])['source_incident_id'] == source['id'] for r in previous):
                raise HTTPException(409, 'Este caso já foi associado. Acrescenta uma nota para complementar a decisão.')
            if len(previous) >= 20:
                raise HTTPException(409, 'Limite de 20 referências atingido.')
            snapshot = {key: source[key] for key in ('title','source','status','resolution','root_cause','prevention','runbook')}
            record = {'schema_version': 1, 'source_incident_id': source['id'],
                      'reason': data.reason, 'source_snapshot': snapshot}
            event(db, iid, user['name'], 'Conhecimento aplicado', json.dumps(record, ensure_ascii=False))
            audit(db, user['name'], 'incident.knowledge.applied', f'incident:{iid}', f"Referência INC-{source['id']}")
            return {'ok': True, 'source_incident_id': source['id']}

