"""Bounded closed-loop HTTP experiment, restricted to a marked loopback fixture."""
import argparse
from datetime import datetime,timezone
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import math
from pathlib import Path
import socket
import time
from urllib.parse import urlencode

ORIGIN=('127.0.0.1',8010)
PATHS=['/api/summary','/api/services','/api/incidents',
       '/api/knowledge?'+urlencode({'q':'O navegador recusa a conexão segura porque a validade terminou','method':'hybrid'}),
       '/api/slo?window=24h']


def request(path,cookie=None,method='GET',body=None):
    conn=http.client.HTTPConnection(*ORIGIN,timeout=12)
    headers={'Connection':'close'}
    if cookie:headers['Cookie']=cookie
    if body is not None:headers['Content-Type']='application/json'
    started=time.perf_counter()
    try:
        conn.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers)
        response=conn.getresponse()
        raw=response.read(2*1024*1024+1)
        if len(raw)>2*1024*1024:raise ValueError('Response exceeded test cap')
        return response.status,dict(response.getheaders()),raw,(time.perf_counter()-started)*1000
    finally:conn.close()


def percentile(values,p):
    ordered=sorted(values)
    return round(ordered[max(0,math.ceil(len(ordered)*p)-1)],2) if ordered else None


def phase(clients,count,cookie,overload=False):
    def run(n):
        path='/api/summary' if overload else PATHS[n%len(PATHS)]
        try:
            status,_,raw,elapsed=request(path,cookie)
            method=None
            if status==200 and path.startswith('/api/knowledge'):
                method=json.loads(raw)['actual_method']
            return {'endpoint':path.partition('?')[0],'status':status,'ms':round(elapsed,2),'knowledge_method':method}
        except (OSError,ValueError,http.client.HTTPException):
            return {'endpoint':path.partition('?')[0],'status':'transport_error','ms':None,'knowledge_method':None}
    started=time.perf_counter()
    with ThreadPoolExecutor(max_workers=clients) as pool:rows=list(pool.map(run,range(count)))
    elapsed=time.perf_counter()-started
    accepted=[r['ms'] for r in rows if r['status']==200]
    summary={'clients':clients,'requests':count,'closed_loop':True,'overload_probe':overload,
        'seconds':round(elapsed,3),'status_counts':dict(Counter(str(r['status']) for r in rows)),
        'accepted_rps':round(len(accepted)/elapsed,2),'accepted_p50_ms':percentile(accepted,.5),
        'accepted_p95_ms':percentile(accepted,.95),'accepted_max_ms':round(max(accepted),2) if accepted else None,
        'knowledge_methods':dict(Counter(r['knowledge_method'] for r in rows if r['knowledge_method']))}
    print(json.dumps(summary),flush=True)
    return {**summary,'requests_detail':rows}


def slow_body():
    start=time.perf_counter()
    with socket.create_connection(ORIGIN,timeout=15) as conn:
        conn.settimeout(15)
        conn.sendall(b'POST /api/login HTTP/1.1\r\nHost: 127.0.0.1:8010\r\nContent-Type: application/json\r\nContent-Length: 100\r\nConnection: close\r\n\r\nx')
        line=conn.recv(4096).split(b'\r\n',1)[0].decode('ascii')
    assert ' 408 ' in line,line
    return {'status_line':line,'seconds':round(time.perf_counter()-start,2)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    started_at=datetime.now(timezone.utc).isoformat()
    status,_,raw,_=request('/api/load-test-marker')
    marker=json.loads(raw)
    if status!=200 or marker.get('fixture')!='nexo-disposable-load-v1':
        raise SystemExit('Refusing an unmarked target')
    status,headers,_,_=request('/api/login',method='POST',body={'email':'leitor@local.test','password':'EstudoLocal2026!'})
    assert status==200
    cookie=headers['set-cookie'].split(';',1)[0]
    for path in PATHS:
        assert request(path,cookie)[0]==200
    phases=[phase(clients,40,cookie) for clients in (1,4,12)]
    phases.append(phase(48,96,cookie,True))
    with ThreadPoolExecutor(max_workers=8) as pool:
        pressure=list(pool.map(lambda n:request('/api/login',method='POST',body={'email':f'capacity-{n}@local.test','password':'invalid'})[0],range(8)))
    slow=slow_body()
    recovery_status,_,_,latency=request('/api/summary',cookie)
    assert recovery_status==200
    status,_,raw,_=request('/api/load-test-marker');after=json.loads(raw)
    report={'started_at':started_at,'completed_at':datetime.now(timezone.utc).isoformat(),'fixture':marker,'after':after,'phases':phases,'auth_pressure_statuses':dict(Counter(map(str,pressure))),
        'slow_body':slow,'post_load_recovery':{'status':recovery_status,'summary_ms':round(latency,2)},
        'limitations':'Single local closed-loop run; synthetic fixtures; prewarmed embeddings; new TCP connection per request; no Internet/TLS/proxy, sustained soak, distributed traffic or capacity certification. 503 is reported as rejection, not success. Timings include client/network scheduling.',
        'passed':all(p['status_counts']=={'200':p['requests']} for p in phases[:3]) and set(phases[3]['status_counts'])<={'200','503'} and phases[3]['status_counts'].get('200',0)>0 and set(pressure)<={401,429}}
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not report['passed']:raise SystemExit('Unexpected failures; inspect report')


if __name__=='__main__':main()
