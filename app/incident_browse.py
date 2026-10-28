"""Authenticated, bounded browsing of incident history, without changing cases."""
import re
from datetime import date
from typing import Literal

from fastapi import Depends, HTTPException, Query

from .db import database, now

MAX_ID = 2**63 - 1


def routes(app, path, current_user):
    @app.get('/api/incidents/context')
    def context(user=Depends(current_user)):
        with database(path) as db:
            db.execute('BEGIN')
            # The dashboard needs five summaries, not every case and its post-mortem.
            attention = [dict(row) for row in db.execute('''SELECT i.id,i.service_id,i.title,
                i.severity,i.status,i.source,i.created_at,s.name AS service_name,
                u.name AS assignee_name FROM incidents i JOIN services s ON s.id=i.service_id
                LEFT JOIN users u ON u.id=i.assignee_id
                WHERE i.status NOT IN ('resolved','closed')
                ORDER BY i.severity,i.created_at DESC,i.id DESC LIMIT 5''')]
            # These are the two built-in lab targets; custom targets use the incident browser.
            # The unique active Prometheus incident index permits at most one per service.
            laboratory = [dict(row) for row in db.execute('''SELECT i.id,i.service_id,
                i.severity,i.status,i.source FROM incidents i
                JOIN telemetry_targets t ON t.service_id=i.service_id
                WHERE t.target_key IN ('portal-lab','api-lab')
                AND i.source='prometheus-alert' AND i.status NOT IN ('resolved','closed')
                ORDER BY i.id DESC LIMIT 2''')]
            references = [dict(row) for row in db.execute('''SELECT id,title,status,source
                FROM incidents WHERE status IN ('resolved','closed') ORDER BY id DESC LIMIT 101''')]
            return {'attention': attention, 'laboratory': laboratory,
                    'references': references[:100], 'references_more': len(references) > 100,
                    'limits': {'attention': 5, 'laboratory': 2, 'references': 100},
                    'generated_at': now()}

    @app.get('/api/incidents/browse')
    def browse(
        view: Literal['active', 'history', 'all'] = 'active',
        status: Literal['open', 'acknowledged', 'investigating', 'resolved', 'closed'] | None = None,
        severity: Literal['P1', 'P2', 'P3', 'P4'] | None = None,
        service_id: int | None = Query(default=None, ge=1, le=MAX_ID),
        assignee_id: int | None = Query(default=None, ge=0, le=MAX_ID),
        scope: Literal['all', 'operational', 'examples'] = 'all',
        q: str = Query(default='', max_length=200),
        date_from: date | None = None,
        date_to: date | None = None,
        before_id: int | None = Query(default=None, ge=1, le=MAX_ID),
        snapshot_id: int | None = Query(default=None, ge=0, le=MAX_ID),
        limit: int = Query(default=50, ge=1, le=100),
        user=Depends(current_user),
    ):
        if date_from and date_to and date_from > date_to:
            raise HTTPException(422, 'A data inicial não pode ser posterior à data final.')
        with database(path) as db:
            db.execute('BEGIN')
            upper = db.execute('SELECT COALESCE(MAX(id),0) FROM incidents').fetchone()[0]
            if snapshot_id is not None:
                upper = min(upper, snapshot_id)
            clauses, params = ['i.id <= ?'], [upper]
            if view != 'all':
                clauses.append("i.status " + ("NOT IN" if view == 'active' else "IN") + " ('resolved','closed')")
            for column, value in [('status', status), ('severity', severity), ('service_id', service_id)]:
                if value is not None:
                    clauses.append(f'i.{column} = ?')
                    params.append(value)
            if assignee_id == 0:
                clauses.append('i.assignee_id IS NULL')
            elif assignee_id is not None:
                clauses.append('i.assignee_id = ?')
                params.append(assignee_id)
            if scope != 'all':
                clauses.append("i.source " + ("LIKE" if scope == 'examples' else "NOT LIKE") + " 'demo%'")
            # Incident creation dates are stored in UTC. Both endpoint days are included.
            for value, operator in [(date_from, '>='), (date_to, '<=')]:
                if value:
                    clauses.append(f'substr(i.created_at,1,10) {operator} ?')
                    params.append(value.isoformat())
            query = q.strip()
            if query:
                identifier = re.fullmatch(r'(?:INC-)?0*([1-9][0-9]*)', query, re.IGNORECASE)
                if identifier:
                    # Bind as text: arbitrarily long input must not overflow SQLite integers.
                    clauses.append('CAST(i.id AS TEXT) = ?')
                    params.append(identifier[1])
                else:
                    db.create_function('casefold', 1, lambda value: value.casefold(), deterministic=True)
                    clauses.append("instr(casefold(i.title || char(10) || i.description || char(10) || s.name || char(10) || COALESCE(u.name,'')), ?) > 0")
                    params.append(query.casefold())
            if before_id is not None:
                clauses.append('i.id < ?')
                params.append(before_id)
            rows = [dict(row) for row in db.execute('''SELECT i.*, s.name AS service_name,
                u.name AS assignee_name FROM incidents i JOIN services s ON s.id=i.service_id
                LEFT JOIN users u ON u.id=i.assignee_id WHERE ''' + ' AND '.join(clauses) +
                ' ORDER BY i.id DESC LIMIT ?', [*params, limit + 1])]
            items = rows[:limit]
            return {'items': items, 'snapshot_id': upper,
                    'next_before_id': items[-1]['id'] if len(rows) > limit else None,
                    'limit': limit, 'date_timezone': 'UTC', 'order': 'id_desc'}
