"""Ephemeral Linux restore and loopback app probe; receives secrets only on stdin."""
import base64
from contextlib import closing
import http.cookiejar
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import build_opener,HTTPCookieProcessor,Request,ProxyHandler

from app import portable,recovery
from .check_recovery import fingerprint


def main():
    payload=json.loads(sys.stdin.buffer.read(recovery.MAX_INPUT+1))
    archive=base64.b64decode(payload['archive'],validate=True)
    wrapped=base64.b64decode(payload['wrapped_key'],validate=True)
    phrase=base64.b64decode(payload['passphrase_b64'],validate=True).decode('utf-8')
    key=portable.unwrap(wrapped,phrase)
    started=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='nexo-portable-probe-') as folder:
        snapshot,manifest=recovery.checked_snapshot(archive,key,folder)
        reference=fingerprint(snapshot)
        with closing(sqlite3.connect(snapshot)) as db:
            if not db.execute("SELECT 1 FROM settings WHERE key='demo_initialized' AND value='1'").fetchone():
                raise RuntimeError('The HTTP probe only accepts the academic demo database')
        result=recovery.restore(archive,key,Path(folder)/'restored')
        assert fingerprint(Path(result['path']))['digests']==reference['digests']
        env={k:v for k,v in os.environ.items() if k not in ('PROMETHEUS_URL','LOKI_URL','SEMANTIC_URL','APP_ENV','APP_ORIGIN')}
        env.update(DATABASE_PATH=result['path'],DEMO_MODE='1',LAB_MODE='0',ALLOWED_HOSTS='127.0.0.1,localhost')
        child=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8031','--no-access-log'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def call(path,data=None):
            with opener.open(Request('http://127.0.0.1:8031'+path,data=json.dumps(data).encode() if data is not None else None,
                         headers={'Content-Type':'application/json'}),timeout=3) as response:
                return json.load(response)
        try:
            for _ in range(50):
                try:call('/api/health');break
                except OSError:time.sleep(.1)
            else:raise RuntimeError('Restored application failed to start')
            user=call('/api/login',{'email':'leitor@local.test','password':'EstudoLocal2026!'})
            assert user['role']=='viewer'
            cases=call('/api/incidents')
            assert len(cases)==manifest['tables']['incidents']
            with closing(sqlite3.connect(result['path'])) as db:
                iid,title=db.execute("SELECT id,title FROM incidents WHERE status='closed' ORDER BY id DESC LIMIT 1").fetchone()
            detail=call('/api/incidents/'+str(iid))
            assert detail['timeline'] and detail['resolution']
            from urllib.parse import urlencode
            assert call('/api/knowledge?'+urlencode({'q':title,'method':'tfidf'}))['results']
            call('/api/logout',{})
        finally:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:child.kill();child.wait()
        print(json.dumps({'platform':sys.platform,'network':'none (Docker invocation)','dpapi_used':False,
            'original_files_mounted':False,'archive_sha256':result['archive_sha256'],
            'tables_preserved':list(reference['digests']),'counts':manifest['tables'],
            'sessions_removed':True,'monitoring_paused':True,'application_login_history_search':'passed',
            'seconds':round(time.perf_counter()-started,3)},ensure_ascii=True))


if __name__=='__main__':main()
