"""Post-incident actions projected from bounded, append-only timeline events."""
import json
from datetime import date
from typing import Literal, Annotated

from fastapi import Depends, HTTPException, Path
from pydantic import Field, field_validator

from .db import database, audit, now
from .models import Input

CREATED = 'Ação de prevenção criada'
FINISHED = 'Ação de prevenção terminada'


class ActionInput(Input):
    title: str = Field(min_length=5, max_length=200)
    owner_id: int = Field(strict=True, gt=0, le=2**63-1)
    due_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$', min_length=10, max_length=10)

    @field_validator('due_date')
    @classmethod
    def valid_date(cls, value):
        date.fromisoformat(value)
        return value


class FinishInput(Input):
    status: Literal['completed', 'cancelled']
    note: str = Field(min_length=10, max_length=2000)


def projection(db, iid):
    items = {}
    for row in db.execute('''SELECT id,actor,note,created_at,action FROM timeline
            WHERE incident_id=? AND action IN (?,?) ORDER BY id LIMIT 41''', (iid, CREATED, FINISHED)):
        record = json.loads(row['note'])
        if row['action'] == CREATED:
            items[row['id']] = {**record, 'id': row['id'], 'status': 'open',
                'created_at': row['created_at'], 'created_by': row['actor'],
                'finished_at': None, 'finished_by': None, 'completion_note': ''}
        elif record['action_id'] in items:
            items[record['action_id']].update(status=record['status'], completion_note=record['note'],
                finished_at=row['created_at'], finished_by=row['actor'])
    today = now()[:10]
    return [{**item, 'overdue': item['status']=='open' and item['due_date'] < today}
            for item in items.values()]


def append(db, iid, user, action, payload):
    result = db.execute('INSERT INTO timeline(incident_id,actor,action,note,created_at) VALUES(?,?,?,?,?)',
        (iid, user['name'], action, json.dumps(payload,ensure_ascii=False), now()))
    return result.lastrowid


def routes(app, path, writer, require):
    @app.post('/api/incidents/{iid}/follow-ups', status_code=201)
    def create_action(iid: Annotated[int, Path(ge=1, le=2**63-1)], data: ActionInput, user=Depends(writer)):
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            incident = require(db, 'incidents', iid)
            if incident['status'] not in ('resolved','closed'):
                raise HTTPException(409, 'Resolve o incidente antes de registar as ações de prevenção.')
            if len(projection(db,iid)) >= 20:
                raise HTTPException(409, 'Limite de 20 ações de prevenção atingido neste caso.')
            owner = require(db, 'users', data.owner_id)
            if owner['role']=='viewer' or not owner['active'] or owner['must_change_password']:
                raise HTTPException(422, 'Escolhe uma conta ativa de operações ou administração com o primeiro acesso concluído.')
            aid = append(db,iid,user,CREATED,{'schema_version':1,'title':data.title,
                'owner_id':owner['id'],'owner_name':owner['name'],'due_date':data.due_date})
            audit(db,user['name'],'incident.followup.created',f'incident:{iid}',f'Ação {aid}')
            return next(item for item in projection(db,iid) if item['id']==aid)

    @app.post('/api/incidents/{iid}/follow-ups/{aid}/finish')
    def finish_action(iid: Annotated[int, Path(ge=1, le=2**63-1)], aid: Annotated[int, Path(ge=1, le=2**63-1)], data: FinishInput, user=Depends(writer)):
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            require(db,'incidents',iid)
            action = next((item for item in projection(db,iid) if item['id']==aid),None)
            if action is None:
                raise HTTPException(404, 'Ação não encontrada neste incidente.')
            if action['status']!='open':
                raise HTTPException(409, 'Esta ação já foi concluída ou cancelada. Atualiza o caso para consultar a decisão.')
            append(db,iid,user,FINISHED,{'schema_version':1,'action_id':aid,**data.model_dump()})
            audit(db,user['name'],'incident.followup.finished',f'incident:{iid}',f'Ação {aid}: {data.status}')
            return next(item for item in projection(db,iid) if item['id']==aid)
