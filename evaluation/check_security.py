"""Negative HTTP checks, only against the disposable load-test fixture."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

from .load_test import request


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    status,_,raw,_=request('/api/load-test-marker')
    assert status==200 and json.loads(raw)['fixture']=='nexo-disposable-load-v1'
    checks=[]
    def record(name,condition):
        assert condition,name
        checks.append({'check':name,'passed':True})
    for path in ('/api/incidents','/api/services','/api/knowledge','/api/slo','/api/admin/users','/api/audit'):
        status,headers,_,_=request(path)
        record('anonymous '+path,status==401 and headers.get('cache-control')=='no-store')
    for path in ('/data/nexo.db','/.env','/.git/config','/static/%2e%2e/data/nexo.db','/static/%2e%2e/.env','/api/recovery'):
        record('no file/restore exposure '+path,request(path)[0] in (400,404))
    status,headers,raw,_=request('/api/login',method='POST',body={'email':"admin@local.test' OR 1=1--",'password':'test-only'})
    record('SQL injection does not authenticate',status==401 and 'set-cookie' not in headers)
    status,headers,raw,_=request('/api/login',method='POST',body={'email':'leitor@local.test','password':'EstudoLocal2026!'})
    record('login cookie flags',status==200 and 'HttpOnly' in headers['set-cookie'] and 'SameSite=strict' in headers['set-cookie'])
    cookie=headers['set-cookie'].split(';',1)[0]
    record('password hashes not returned',b'password_hash' not in raw)
    for path in ('/api/admin/users','/api/audit'):
        record('viewer forbidden '+path,request(path,cookie)[0]==403)
    record('viewer cannot create services',request('/api/services',cookie,'POST',{'name':'Forbidden','team':'Test'})[0]==403)
    status,headers,raw,_=request('/api/knowledge?q=private-query-probe',cookie)
    record('security response headers',status==200 and headers.get('x-content-type-options')=='nosniff' and headers.get('x-frame-options')=='DENY' and "default-src 'self'" in headers.get('content-security-policy',''))
    status,_,raw,_=request('/api/login',method='POST',body={'email':'user@local.test','password':'private-invalid-value','unexpected':'private-invalid-value'})
    record('validation does not echo submitted secrets',status==422 and b'private-invalid-value' not in raw)
    record('public restore upload absent',request('/api/recovery',cookie,'POST',{})[0]==404)
    record('session logout',request('/api/logout',cookie,'POST')[0]==200 and request('/api/me',cookie)[0]==401)
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'target':'disposable loopback fixture','checks':checks,
            'limitations':'Manual code review plus selected automated regressions. Not a penetration test, exhaustive ASVS certification, multi-tenant isolation claim or image/OS vulnerability scan.'}
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(checks)} isolated HTTP security checks passed.')


if __name__=='__main__':main()
