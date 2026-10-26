import asyncio
from datetime import datetime,timedelta,timezone
import logging
from concurrent.futures import ThreadPoolExecutor
import time

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.accesslog import RedactQuery
from app.db import database
from app.main import create_app
from app.request_limits import BodyLimitMiddleware
from app.security import PASSWORD_SLOTS
from app import slo
from tests.test_workflow import PASSWORD, client, login


def test_password_work_capacity_is_bounded_and_released(client):
    PASSWORD_SLOTS.acquire();PASSWORD_SLOTS.acquire()
    try:
        result=client.post('/api/login',json={'email':'admin@local.test','password':PASSWORD})
        assert result.status_code==429 and result.headers['retry-after']=='2'
        assert 'nexo_session' not in result.cookies
    finally:
        PASSWORD_SLOTS.release();PASSWORD_SLOTS.release()
    login(client)


@pytest.mark.parametrize('password',['curta','EstudoLocal2026!','123456789012345'])
def test_production_bootstrap_rejects_weak_passwords(tmp_path,monkeypatch,password):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('APP_ORIGIN','https://localhost')
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD',password)
    with pytest.raises(RuntimeError):
        with TestClient(create_app(tmp_path/'new.db',demo=False),base_url='https://localhost'):
            pass
    with database(tmp_path/'new.db') as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0]==0


def test_request_read_deadline_does_not_reach_application():
    sent=[];forwarded=[]
    async def receive():
        await asyncio.sleep(1)
        return {'type':'http.request','body':b'x','more_body':True}
    async def send(message):sent.append(message)
    async def downstream(*args):forwarded.append(True)
    asyncio.run(BodyLimitMiddleware(downstream,timeout_seconds=.01)({'type':'http','headers':[]},receive,send))
    assert sent[0]['status']==408 and not forwarded


def test_access_log_retains_path_but_no_query():
    record=logging.LogRecord('uvicorn.access',logging.INFO,'',0,'%s - "%s %s HTTP/%s" %d',
                             ('127.0.0.1','GET','/api/knowledge?q=private-secret&method=hybrid','1.1',200),None)
    assert RedactQuery().filter(record)
    assert '/api/knowledge HTTP/' in record.getMessage()
    assert 'private-secret' not in record.getMessage() and '?q=' not in record.getMessage()
    record.args=('unexpected contract',)
    assert not RedactQuery().filter(record)


def test_history_is_bounded_without_truncating_availability(client):
    login(client)
    stamp=datetime.now(timezone.utc)
    with database(client.app.state.db_path) as db:
        db.execute('DELETE FROM observations WHERE service_id=1')
        db.executemany('INSERT INTO observations(service_id,available,latency_ms,source,observed_at) VALUES(1,?,100,?,?)',
                       [(int(n!=0),'load-test',(stamp-timedelta(seconds=100-n)).isoformat()) for n in range(100)])
    service=client.get('/api/services').json()[0]
    assert service['sample_count']==100 and service['availability']==99
    assert len(service['history'])==48
    assert service['history'][0]['observed_at']<service['history'][-1]['observed_at']
    assert service['latest']==service['history'][-1]


def test_slo_cache_single_flight_and_invalidation(client,monkeypatch):
    calls=[]
    def calculate(path,window):
        calls.append(window)
        time.sleep(.02)
        return {'services':[],'generated_at':'test'}
    monkeypatch.setattr(slo,'report',calculate)
    monkeypatch.setattr(slo.time,'time',lambda:1800000100)
    cache=slo.ReportCache(client.app.state.db_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:cache.get('24h'),range(8)))
    assert calls==['24h'] and all(r['cache_max_age_seconds']==3 for r in results)
    with database(client.app.state.db_path) as db:
        db.execute("UPDATE services SET team='Nova equipa' WHERE id=1")
    cache.get('24h');assert len(calls)==2
    with database(client.app.state.db_path) as db:
        db.execute("INSERT INTO observations(service_id,available,latency_ms,source,observed_at) VALUES(1,1,100,'test','2030-01-01')")
    cache.get('24h');assert len(calls)==3
    cache.ttl=0
    cache.get('24h');assert len(calls)==4
    cache.wait_seconds=.01
    cache.lock.acquire()
    try:
        with pytest.raises(HTTPException) as error:
            cache.get('24h')
        assert error.value.status_code==503 and error.value.headers['Retry-After']=='1'
    finally:
        cache.lock.release()
