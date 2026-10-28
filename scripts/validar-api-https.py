"""Validate the private TLS API and automatic collection in preproduction."""
from datetime import datetime, timezone
import base64
import hashlib
from http.cookies import SimpleCookie
import json
from pathlib import Path
import runpy
import ssl
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
from preproduction import ROOT, ORIGIN, prepare, context


def main():
    edge=runpy.run_path(str(ROOT/'scripts/validar-https.py'),run_name='https_validation')
    edge['main']()
    request,check=edge['request'],edge['check']
    directory=prepare(ROOT);command,env=context(ROOT,directory);docker=command[0]
    tls=ssl.create_default_context(cafile=str(directory/'root.crt'))
    password=(directory/'initial-admin.key').read_text(encoding='utf-8')
    status,headers,_,_,_=request(tls,'POST','/api/login',{'email':'admin@preprod.test','password':password},{'Origin':ORIGIN})
    check(status==200,'sessão de validação')
    cookies=SimpleCookie();cookies.load(headers['set-cookie'])
    authenticated={'Cookie':'nexo_session='+cookies['nexo_session'].value,'Origin':ORIGIN}
    deadline=time.monotonic()+35
    while True:
        status,_,payload,_,_=request(tls,'GET','/api/enterprise/summary',headers=authenticated)
        business=json.loads(payload)
        if status==200 and business['status']=='connected' and business['monitoring']['collection_state']=='running':
            break
        check(time.monotonic()<deadline,'recolha automática com amostra nova')
        time.sleep(2)
    check(business['summary']['company_id']=='aurora' and business['summary']['environment']=='laboratory','identidade fictícia validada')
    status,_,payload,_,_=request(tls,'GET','/api/services',headers=authenticated)
    services=json.loads(payload);sid=business['monitoring']['service_id']
    check(status==200 and any(s['id']==sid and s['telemetry_source']=='enterprise' for s in services),'serviço autenticado no inventário')
    status,_,payload,_,_=request(tls,'GET','/api/incidents',headers=authenticated)
    check(status==200 and all(i['status'] in ('resolved','closed') for i in json.loads(payload)), 'nenhum incidente ativo após recuperação')
    check(request(tls,'POST','/api/logout',headers=authenticated)[0]==200,'sessão de ensaio terminada')
    containers=json.loads(subprocess.check_output([docker,'inspect','nexo-preproduction-nexo-1',
                        'nexo-preproduction-proxy-1','nexo-preproduction-enterprise-api-1'],text=True,timeout=20))
    app,proxy,api=containers
    check(not any(api['NetworkSettings']['Ports'].values()),'API sem porta publicada')
    check(set(proxy['NetworkSettings']['Networks']).isdisjoint(api['NetworkSettings']['Networks']),'proxy de entrada fora da rede empresarial')
    for container in (app,proxy):
        check(not any(m['Destination']=='/run/secrets/enterprise_private' for m in container['Mounts']),'chave TLS privada apenas no servidor da API')
    check(all(not m['RW'] for m in api['Mounts'] if m['Destination'].startswith('/run/secrets/')),'ficheiros TLS e token apenas para leitura')
    other_ca=base64.b64encode((directory/'root.crt').read_bytes()).decode()
    probe="""import base64,json,os,socket,ssl,tempfile
from pathlib import Path
from app.enterprise import EnterpriseClient,read_token
url=os.environ['ENTERPRISE_API_URL'];key=read_token(os.environ['ENTERPRISE_API_TOKEN_FILE']);ca=os.environ['ENTERPRISE_API_CA_FILE']
valid=EnterpriseClient.configured().fetch()['status']
missing=EnterpriseClient(url,key,company_id='aurora').fetch()['status']
with tempfile.TemporaryDirectory() as folder:
 other=Path(folder)/'other.crt';other.write_bytes(base64.b64decode(OTHER_CA))
 foreign=EnterpriseClient(url,key,company_id='aurora',ca_file=str(other)).fetch()['status']
wrong=EnterpriseClient(url,'deliberately-wrong-read-token-123456789',company_id='aurora',ca_file=ca).fetch()['status']
connection=socket.create_connection(('enterprise-api',8080),timeout=3)
try:
 with ssl.create_default_context(cafile=ca).wrap_socket(connection,server_hostname='not-this-api.invalid'):
  hostname_refused=False
except ssl.SSLCertVerificationError:
 hostname_refused=True
finally:
 connection.close()
print(json.dumps({'valid':valid,'missing_ca':missing,'foreign_ca':foreign,'wrong_bearer':wrong,'hostname_refused':hostname_refused}))
""".replace('OTHER_CA',repr(other_ca))
    checks=json.loads(subprocess.check_output([docker,'exec','-i',app['Id'],'python','-'],input=probe,text=True,timeout=25))
    check(checks=={'valid':'connected','missing_ca':'unavailable','foreign_ca':'unavailable','wrong_bearer':'unauthorized','hostname_refused':True},'TLS e Bearer verificados separadamente')
    sample_code="""import json,sqlite3
d=sqlite3.connect('file:/app/data/nexo.db?mode=ro',uri=True)
binding=json.loads(d.execute("SELECT value FROM settings WHERE key='enterprise_monitoring_binding'").fetchone()[0])
print(json.dumps({'samples':d.execute("SELECT COUNT(*) FROM observations WHERE service_id=? AND source='enterprise-api'",(binding['service_id'],)).fetchone()[0]}))
"""
    samples=json.loads(subprocess.check_output([docker,'exec',app['Id'],'python','-c',sample_code],text=True,timeout=10))['samples']
    check(samples>0,'observações técnicas persistidas')
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'version':'0.31.0','company_id':'aurora','business_environment':'laboratory',
            'transport':'HTTPS with certificate chain and hostname validation; scoped additional API CA',
            'negative_checks':checks,'service_id':sid,'enterprise_samples':samples,'collection_state':business['monitoring']['collection_state'],
            'last_sample':business['monitoring']['last_sample'],'orders_total':business['summary']['orders']['total'],
            'api_public_port':False,'api_private_key_only_on_api_server':True,'ingress_proxy_outside_api_network':True,
            'api_ca_sha256':hashlib.sha256((directory/'enterprise-tls/ca.crt').read_bytes()).hexdigest(),
            'scope':'Fictional API, real TLS and authentication. No real company or public publication.'}
    (ROOT/'docs/validacao-api-https-runtime.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS: API privada HTTPS, cadeia e nome, CA por integração, Bearer e recolha automática com persistência.')


if __name__=='__main__':
    main()
