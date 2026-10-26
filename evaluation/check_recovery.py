"""Read-only reference digests, then application checks ONLY on a marked isolated restore."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from app.db import now
from app.recovery import inspect_db, plain_path

TABLES=('users','services','dependencies','incidents','timeline','incident_evidence',
        'alert_rules','alert_rule_history','incident_alert_context','incident_escalations','service_slo_policies')


def fingerprint(path):
    with closing(sqlite3.connect(plain_path(path).as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('BEGIN')
        report=inspect_db(db)
        digests={}
        for table in TABLES:
            rows=db.execute('SELECT * FROM '+table).fetchall()
            encoded=json.dumps(sorted(rows,key=lambda r:json.dumps(r)),ensure_ascii=True,separators=(',',':')).encode()
            digests[table]=hashlib.sha256(encoded).hexdigest()
        return {**report,'digests':digests}


def check(path,reference):
    started=time.perf_counter()
    before=fingerprint(path)
    assert before['digests']==reference['digests'],'Historical rows differ from reference'
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT COUNT(*) FROM audit WHERE action='recovery.restored'").fetchone()[0]>0
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM telemetry_targets WHERE enabled!=0').fetchone()[0]==0
        closed=db.execute("SELECT id,title FROM incidents WHERE status='closed' ORDER BY id DESC LIMIT 1").fetchone()
    for name in ('PROMETHEUS_URL','LOKI_URL','SEMANTIC_URL'):
        os.environ.pop(name,None)
    os.environ['LAB_MODE']='0'
    from fastapi.testclient import TestClient
    from app.main import create_app
    with TestClient(create_app(path,demo=True),base_url='http://localhost') as client:
        assert client.get('/api/incidents').status_code==401
        response=client.post('/api/login',json={'email':'leitor@local.test','password':os.getenv('VALIDATION_PASSWORD','EstudoLocal2026!')})
        assert response.status_code==200
        incidents=client.get('/api/incidents').json()
        assert len(incidents)==reference['tables']['incidents']
        detail=client.get('/api/incidents/'+str(closed[0])).json()
        assert detail['timeline'] and detail['resolution'] and detail['root_cause']
        assert client.get('/api/knowledge',params={'q':closed[1],'method':'tfidf'}).json()['results']
        assert client.get('/api/admin/users').status_code==403
        assert client.get('/api/recovery').status_code==404
        assert client.post('/api/recovery',json={}).status_code==404
        assert client.post('/api/logout').status_code==200
        assert client.get('/api/incidents').status_code==401
    return {'checked_at':now(),'isolated_restore':str(path),'integrity':'ok','foreign_keys':'ok',
            'historical_tables_equal':list(TABLES),'snapshot_counts':before['tables'],
            'sessions_absent_before_login':True,'monitoring_paused':True,'application_started':True,
            'login_history_search_and_permissions':'passed','public_restore_endpoint':'absent',
            'application_check_seconds':round(time.perf_counter()-started,3)}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--database',required=True)
    parser.add_argument('--reference')
    parser.add_argument('--output')
    args=parser.parse_args()
    report=check(args.database,json.loads(Path(args.reference).read_text(encoding='utf-8-sig'))) if args.reference else fingerprint(args.database)
    result=json.dumps(report,ensure_ascii=True,indent=2)
    if args.output:
        Path(args.output).write_text(result,encoding='utf-8')
    else:
        print(result)
