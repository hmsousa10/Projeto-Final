"""Personal read cursor over existing operational events; no external delivery."""
from fastapi import Depends, HTTPException, Query
from pydantic import Field

from .db import database
from .models import Input

KINDS = {
    'Incidente criado': 'created',
    'Alerta confirmado por sondagens': 'detected',
    'Falha recorrente agrupada': 'recurrence',
    'Prioridade elevada para P1': 'priority',
    'Prioridade elevada para P2': 'priority',
    'Prioridade elevada para P3': 'priority',
    'Prioridade elevada para P4': 'priority',
    'Escalonamento por falta de reconhecimento': 'deadline',
    'Prazo de reconhecimento ultrapassado': 'deadline',
    'Responsável atribuído': 'assignment',
    'Serviço recuperado': 'recovery',
}
JOIN = 'FROM timeline t JOIN incidents i ON i.id=t.incident_id JOIN services s ON s.id=i.service_id'
ELIGIBLE = "i.source NOT LIKE 'demo%' AND t.action IN (" + ','.join('?' for _ in KINDS) + ')'


class ReadThrough(Input):
    through_id: int = Field(ge=0, le=2**63-1, strict=True)


def watermark(db, uid):
    row = db.execute('SELECT value FROM settings WHERE key=?', (f'notification.read.{uid}',)).fetchone()
    return max(0, int(row['value'])) if row else 0


def routes(app, path, current_user):
    @app.get('/api/notifications')
    def feed(limit: int = Query(default=30, ge=1, le=50),
             before_id: int | None = Query(default=None, ge=1, le=2**63-1),
             user=Depends(current_user)):
        with database(path) as db:
            db.execute('BEGIN')
            read = watermark(db, user['id'])
            latest = db.execute('SELECT coalesce(max(t.id),0) ' + JOIN + ' WHERE ' + ELIGIBLE,
                                tuple(KINDS)).fetchone()[0]
            unread = db.execute('SELECT count(*) ' + JOIN + ' WHERE ' + ELIGIBLE + ' AND t.id>?',
                                (*KINDS, read)).fetchone()[0]
            rows = db.execute('''SELECT t.id,t.incident_id,t.action,t.note,t.created_at,
                i.title,i.source,i.status,i.severity,s.name AS service_name ''' + JOIN +
                ' WHERE ' + ELIGIBLE + (' AND t.id<?' if before_id else '') +
                ' ORDER BY t.id DESC LIMIT ?', (*KINDS, *([before_id] if before_id else []), limit+1)).fetchall()
            items = [{**dict(row), 'kind': KINDS[row['action']], 'note': (row['note'] or '')[:400],
                      'note_truncated': len(row['note'] or '') > 400,
                      'unread': row['id'] > read} for row in rows[:limit]]
            return {'items': items, 'unread_count': unread, 'latest_id': latest,
                    'read_through_id': read,
                    'next_before_id': items[-1]['id'] if len(rows) > limit else None,
                    'delivery': 'portal', 'refresh_seconds': 10}

    @app.post('/api/notifications/read')
    def mark_read(data: ReadThrough, user=Depends(current_user)):
        # Readers may change their own reading preference, never incident workflow.
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            if data.through_id and not db.execute('SELECT 1 ' + JOIN + ' WHERE ' + ELIGIBLE + ' AND t.id=?',
                                                  (*KINDS, data.through_id)).fetchone():
                raise HTTPException(409, 'O aviso indicado não existe no histórico operacional.')
            read = max(watermark(db, user['id']), data.through_id)
            db.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',
                       (f'notification.read.{user["id"]}', str(read)))
            return {'read_through_id': read}
