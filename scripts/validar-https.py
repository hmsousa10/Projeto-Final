"""Real TLS rehearsal on loopback; verifies the local CA without installing it."""
from datetime import datetime, timezone
import hashlib
import http.client
from http.cookies import SimpleCookie
import json
from pathlib import Path
import socket
import ssl
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from preproduction import ROOT, HOST, ORIGIN, prepare, context

MARKER = 'Ensaio HTTPS · catálogo privado'


def check(value, label):
    if not value:
        raise RuntimeError('Falhou a verificação: ' + label)


def request(tls, method, path, payload=None, headers=None):
    # Explicit loopback connection with the real DNS hostname as TLS SNI/SAN.
    # No DNS/hosts changes, no insecure TLS mode and no global CA installation.
    connection = http.client.HTTPConnection(HOST, 8443, timeout=8)
    raw = socket.create_connection(('127.0.0.1',8443),timeout=8)
    try:
        connection.sock = tls.wrap_socket(raw,server_hostname=HOST)
        protocol = connection.sock.version()
        certificate = hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()
        body = json.dumps(payload).encode() if payload is not None else None
        values = {'Content-Type':'application/json', **(headers or {})}
        connection.request(method,path,body=body,headers=values)
        response = connection.getresponse()
        content = response.read(512*1024+1)
        check(len(content)<=512*1024,'resposta limitada')
        return response.status,{k.lower():v for k,v in response.getheaders()},content,protocol,certificate
    finally:
        connection.close()
        raw.close()


def main():
    directory = prepare(ROOT)
    command, env = context(ROOT,directory)
    docker = command[0]
    tls = ssl.create_default_context(cafile=str(directory/'root.crt'))
    tls.minimum_version = ssl.TLSVersion.TLSv1_2
    check(tls.check_hostname and tls.verify_mode == ssl.CERT_REQUIRED,'verificação de nome e cadeia ativa')
    try:
        request(ssl.create_default_context(),'GET','/api/health')
    except ssl.SSLCertVerificationError:
        untrusted_refused = True
    else:
        raise RuntimeError('A autoridade do ensaio já é confiável globalmente; revê a condição do teste.')
    status,headers,body,protocol,certificate = request(tls,'GET','/api/health')
    check(status==200 and json.loads(body)['version']=='0.31.0','HTTPS e saúde')
    check(protocol in ('TLSv1.2','TLSv1.3'),'protocolo TLS atual')
    check('max-age=' in headers.get('strict-transport-security',''),'HSTS')
    check('frame-ancestors' in headers.get('content-security-policy',''),'CSP')
    check('server' not in headers,'cabeçalho de servidor removido')
    plain = http.client.HTTPConnection('127.0.0.1',8084,timeout=5)
    try:
        plain.request('GET','/api/config?probe=1',headers={'Host':HOST})
        redirect = plain.getresponse()
        check(redirect.status==308 and redirect.getheader('Location')==ORIGIN+'/api/config?probe=1','redireção para origem fixa')
    finally:
        plain.close()
    status,_,body,_,_ = request(tls,'GET','/api/config',headers={'X-Forwarded-Proto':'http','X-Forwarded-For':'198.51.100.42'})
    config=json.loads(body)
    check(status==200 and config['environment']=='production' and config['demo'] is False,'modo produção atrás do proxy')
    check(config['enterprise'] is True,'API empresarial HTTPS configurada')
    check(request(tls,'GET','/api/config',headers={'Host':'unrelated.invalid'})[0] in (400,421),'Host não autorizado')
    check(request(tls,'GET','/docs')[0]==404 and request(tls,'GET','/openapi.json')[0]==404,'documentação de desenvolvimento desativada')
    check(request(tls,'GET','/api/me')[0]==401,'sessão exigida')
    password=(directory/'initial-admin.key').read_text(encoding='utf-8')
    status,headers,_,_,_ = request(tls,'POST','/api/login',{'email':'admin@preprod.test','password':password},
                                  {'Origin':ORIGIN,'X-Forwarded-Proto':'http','X-Forwarded-For':'198.51.100.42','Forwarded':'for=198.51.100.42;proto=http'})
    check(status==200,'autenticação HTTPS')
    cookies=SimpleCookie();cookies.load(headers.get('set-cookie',''))
    session=cookies['nexo_session']
    check(session['secure'] and session['httponly'] and session['samesite'].lower()=='strict','proteções da cookie')
    authenticated={'Cookie':'nexo_session='+session.value,'Origin':ORIGIN}
    forbidden={'name':'Este registo deve ser recusado','team':'Ensaio'}
    check(request(tls,'POST','/api/services',forbidden,{**authenticated,'Origin':'https://unrelated.invalid'})[0]==403,'origem cruzada recusada')
    check(request(tls,'POST','/api/services',forbidden,{**authenticated,'Sec-Fetch-Site':'cross-site'})[0]==403,'pedido cross-site recusado')
    status,_,body,_,_=request(tls,'GET','/api/services',headers=authenticated)
    check(status==200,'inventário autenticado')
    services=json.loads(body)
    marker=next((s for s in services if s['name']==MARKER),None)
    if marker is None:
        status,_,body,_,_=request(tls,'POST','/api/services',{'name':MARKER,'team':'Pré-produção',
                                'description':'Registo fictício criado pela validação HTTPS; sem ligação empresarial.'},authenticated)
        check(status==201,'escrita autenticada na origem correta')
        marker=json.loads(body)
    check(not any(s['name']==forbidden['name'] for s in services),'pedidos recusados sem escrita')
    status,_,business,_,_=request(tls,'GET','/api/enterprise/summary',headers=authenticated)
    business=json.loads(business)
    check(status==200 and business['status']=='connected','ligação empresarial HTTPS')
    check(business['summary']['company_id']=='aurora' and business['summary']['environment']=='laboratory','identidade fictícia explícita')
    check(business['summary']['orders']['total']==3,'resumo empresarial validado')
    check(request(tls,'POST','/api/logout',headers=authenticated)[0]==200,'fim da sessão de ensaio')
    check(request(tls,'GET','/api/me',headers=authenticated)[0]==401,'cookie revogada')
    containers=json.loads(subprocess.check_output([docker,'inspect','nexo-preproduction-nexo-1','nexo-preproduction-proxy-1'],text=True,timeout=20))
    app,proxy=containers
    check(not any(app['NetworkSettings']['Ports'].values()),'backend sem porta publicada')
    check(all(binding['HostIp']=='127.0.0.1' for bindings in proxy['NetworkSettings']['Ports'].values() if bindings for binding in bindings),'entrada só em loopback')
    check(all(c['HostConfig']['ReadonlyRootfs'] and c['Config']['User'] not in ('','0','root','0:0') for c in containers),'processos sem root e raiz apenas para leitura')
    check(all('ALL' in c['HostConfig']['CapDrop'] for c in containers),'capacidades removidas')
    check(not any(m['Destination']=='/data' for m in app['Mounts']),'chaves da CA ausentes no backend')
    probe="""import json,urllib.request,urllib.error
r=urllib.request.Request('http://172.30.250.3:8000/api/config',headers={'Host':'preprod.localhost','X-Forwarded-Proto':'https','X-Forwarded-For':'198.51.100.42'})
try:
 s=urllib.request.urlopen(r,timeout=5).status
except urllib.error.HTTPError as e:
 s=e.code
print(json.dumps({'status':s}))
"""
    result=json.loads(subprocess.check_output([docker,'run','--rm','--network','nexo-preproduction_backend','--read-only',
                     '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','64m','--pids-limit','64',
                     '--pull=never',app['Config']['Image'],'python','-c',probe],text=True,timeout=20))
    check(result['status']==400,'outro cliente da rede não pode forjar HTTPS')
    code="""import json,sqlite3,hashlib
d=sqlite3.connect('file:/app/data/nexo.db?mode=ro',uri=True)
print(json.dumps({'forged_ip_attempts':d.execute('SELECT COUNT(*) FROM login_attempts WHERE ip_hash=?',(hashlib.sha256(b'198.51.100.42').hexdigest(),)).fetchone()[0]}))
"""
    recorded=json.loads(subprocess.check_output([docker,'exec',app['Id'],'python','-c',code],text=True,timeout=10))
    check(recorded['forged_ip_attempts']==0,'IP forjado não usado no limitador')
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'version':'0.31.0','origin':ORIGIN,'tls_protocol':protocol,
            'leaf_certificate_sha256':certificate,'public_ca_sha256':hashlib.sha256((directory/'root.crt').read_bytes()).hexdigest(),
            'untrusted_ca_refused':untrusted_refused,'hostname_and_chain_verified':True,'cookie_flags':['Secure','HttpOnly','SameSite=Strict'],
            'checks':['https_health','fixed_https_redirect','production_without_demo','no_development_docs','authenticated_catalog',
                      'cross_origin_and_cross_site_denied','host_mismatch_denied','forwarding_headers_replaced','untrusted_backend_peer_denied',
                      'forged_ip_not_recorded','session_revoked','nonroot_readonly_capdrop','loopback_only','no_backend_public_port'],
            'marker_service_id':marker['id'],'backend_image':app['Image'],'proxy_image':proxy['Image'],
            'scope':'Isolated local production-mode transport rehearsal, with a fictional HTTPS business API and no globally trusted public certificate.'}
    (ROOT/'docs/validacao-https-v031-runtime.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS: TLS com CA e nome verificados, cookies seguras, origem, Host, proxy e isolamento. Certificados do Windows não alterados.')


if __name__=='__main__':
    main()
