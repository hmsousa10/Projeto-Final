"""Administrator-only, bounded keyset browsing of the audit ledger."""
from datetime import date

from fastapi import Depends, HTTPException, Query

from .db import database


MAX_ID = 2**63 - 1


def routes(app, path, admin):
    @app.get('/api/audit/events')
    def events(
        actor: str = Query(default='', max_length=100),
        action: str = Query(default='', max_length=100),
        entity: str = Query(default='', max_length=200),
        q: str = Query(default='', max_length=200),
        date_from: date | None = None,
        date_to: date | None = None,
        before_id: int | None = Query(default=None, ge=1, le=MAX_ID),
        snapshot_id: int | None = Query(default=None, ge=1, le=MAX_ID),
        limit: int = Query(default=50, ge=1, le=100),
        user=Depends(admin),
    ):
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, 'A data inicial não pode ser posterior à data final.')
        clauses, params = ['id <= ?'], []
        with database(path) as db:
            db.execute('BEGIN')
            upper = db.execute('SELECT COALESCE(MAX(id),0) FROM audit').fetchone()[0]
            upper = min(upper, snapshot_id) if snapshot_id else upper
            params.append(upper)
            for column, value in [('actor', actor), ('action', action), ('entity', entity)]:
                if value:
                    clauses.append(f'{column} = ?')
                    params.append(value)
            # Nexo writes UTC ISO timestamps; date filters include both UTC days.
            if date_from:
                clauses.append('substr(created_at,1,10) >= ?')
                params.append(date_from.isoformat())
            if date_to:
                clauses.append('substr(created_at,1,10) <= ?')
                params.append(date_to.isoformat())
            if q:
                db.create_function('casefold', 1, lambda value: value.casefold(), deterministic=True)
                clauses.append("instr(casefold(actor || char(10) || action || char(10) || entity || char(10) || detail), ?) > 0")
                params.append(q.casefold())
            if before_id:
                clauses.append('id < ?')
                params.append(before_id)
            rows = [dict(r) for r in db.execute(
                'SELECT * FROM audit WHERE ' + ' AND '.join(clauses) + ' ORDER BY id DESC LIMIT ?',
                [*params, limit + 1],
            )]
            more = len(rows) > limit
            items = rows[:limit]
            return {'items': items, 'snapshot_id': upper,
                    'next_before_id': items[-1]['id'] if more else None,
                    'limit': limit, 'date_timezone': 'UTC'}
