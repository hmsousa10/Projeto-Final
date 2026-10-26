"""Disposable fixture. Requires explicit LOAD_TEST_MODE and a dedicated database."""
from contextlib import closing
from datetime import datetime,timedelta,timezone
import json
import hashlib
import os
from pathlib import Path
import resource
import sqlite3

from app.db import database,initialize,now
from app.knowledge import Knowledge,corpus,chunks
from app.seed import seed
from app import telemetry,slo
from app.version import VERSION


def prepare(path):
    if os.getenv('LOAD_TEST_MODE')!='1' or str(path)!='/app/data/load-test.db':
        raise RuntimeError('Only the disposable load-test database is allowed')
    if Path(path).exists():
        raise RuntimeError('A fresh tmpfs is required; do not reuse a prior run')
    initialize(path);seed(path);telemetry.initialize_targets(path);slo.initialize_policies(path)
    stamp=datetime.now(timezone.utc)-timedelta(seconds=40)
    with database(path) as db:
        targets=db.execute('SELECT service_id FROM telemetry_targets ORDER BY service_id').fetchall()
        for (sid,) in targets:
            db.executemany('INSERT INTO observations(service_id,available,latency_ms,source,observed_at) VALUES(?,?,?,\'prometheus\',?)',
                [(sid,int(n%200!=0),float(80+n%40),(stamp-timedelta(seconds=10*(8639-n))).isoformat()) for n in range(8640)])
        documents=json.loads(Path('evaluation/benchmark.json').read_text())['documents']
        for n in range(100):
            d=documents[n%len(documents)]
            db.execute('''INSERT INTO incidents(service_id,title,description,severity,status,created_at,closed_at,resolved_at,
                root_cause,resolution,prevention,runbook,source) VALUES(1,?,?,'P3','closed',?,?,?,?,?,?,?,'load-test')''',
                (d['title'],d['description'],now(),now(),now(),d.get('root_cause',''),d.get('resolution',''),d.get('prevention',''),d.get('runbook','')))
    engine=Knowledge.configured(path);engine.initialize()
    documents,_=corpus(path)
    needed={c['key'] for d in documents for c in chunks(d)}
    # Warm the index before measurement; all subsequent searches use current content.
    for _ in range(25):
        engine.index_step()
        if needed<=engine.cached(documents).keys():break
    else:raise RuntimeError('Semantic warmup did not finish')


def main():
    path=os.environ['DATABASE_PATH']
    prepare(path)
    from app.main import create_app
    app=create_app(path,demo=True)
    @app.get('/api/load-test-marker',include_in_schema=False)
    def marker():
        with closing(sqlite3.connect(path)) as db:
            counts={table:db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('observations','incidents','services')}
        def read_number(name):
            p=Path('/sys/fs/cgroup')/name
            return p.read_text().strip() if p.exists() else None
        return {'fixture':'nexo-disposable-load-v1','version':VERSION,'counts':counts,
                'source_sha256':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in ('app/main.py','app/slo.py','app/security.py','app/request_limits.py','evaluation/benchmark.json','evaluation/load_server.py')},
                'max_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                'cgroup_memory_peak_bytes':read_number('memory.peak'),
                'cgroup_cpu_stat':read_number('cpu.stat'),
                'limits':{'app_cpus':1,'app_memory_mib':256,'encoder_cpus':2,'encoder_memory_mib':1024,'concurrency':32}}
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=8000,limit_concurrency=32,backlog=64,timeout_keep_alive=5)


if __name__=='__main__':main()
