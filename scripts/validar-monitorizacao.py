"""Configure a fresh inventory service, verify HTTP SD, pause/resume and real alerts."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import subprocess
import time

helpers = runpy.run_path(str(Path(__file__).with_name('validar-laboratorio.py')))
api, wait_until, COMPOSE = helpers['api'], helpers['wait_until'], helpers['COMPOSE']
NAME = 'Aurora · Consulta de pedidos'
URL = 'http://portal-lab:8080/api/orders'


def main():
    def ready():
        try:
            return api('health')['status']=='ok'
        except OSError:
            return False
    wait_until(ready, 'application ready')
    user = api('login', {'email':'admin@local.test','password':os.getenv('DEMO_PASSWORD','EstudoLocal2026!')})
    existing = next((s for s in api('services') if s['name']==NAME), None)
    sid = existing['id'] if existing else api('services', {'name':NAME, 'team':'Operações Aurora',
                            'description':'Consulta de pedidos ligada através da configuração de monitorização. Serviço de ensaio académico.',
                            'criticality':'Alta','slo_latency_ms':500})['id']
    api(f'services/{sid}/monitoring', {'url':URL,'enabled':True}, 'PUT')
    key = f'service-{sid}'
    def service():
        return next(s for s in api('services') if s['id']==sid)
    def discovered():
        code = "import json,urllib.request; d=json.load(urllib.request.urlopen('http://prometheus:9090/api/v1/targets?state=active')); print(json.dumps([x['labels'].get('service_key') for x in d['data']['activeTargets']]))"
        result = subprocess.run([*COMPOSE,'exec','-T','nexo','python','-c',code],check=True,capture_output=True,text=True,timeout=15)
        return key in json.loads(result.stdout)
    def active():
        return next((i for i in api('incidents') if i['service_id']==sid and i['source']=='prometheus-alert' and i['status'] not in ('resolved','closed')), None)
    wait_until(discovered, 'configured target discovered by Prometheus without restart')
    wait_until(lambda: service()['status']=='healthy', 'new service has actual HTTP measurements')
    assert not service()['logs_available']
    try:
        api('lab/fault', {'target':'portal-lab','kind':'outage'})
        wait_until(lambda: service()['status']=='down' and active() is not None, 'configured service creates an automatic failure incident')
        iid = active()['id']
        api(f'services/{sid}/monitoring', {'url':URL,'enabled':False}, 'PUT')
        count = service()['sample_count']
        wait_until(lambda: not discovered(), 'paused target removed from Prometheus discovery')
        time.sleep(22)
        assert service()['sample_count']==count
        assert service()['status']=='unknown'
        assert api(f'incidents/{iid}')['status'] not in ('resolved','closed')
        print('PASS: pause stops imported samples and preserves incident/history',flush=True)
    finally:
        api('lab/fault', {'target':'portal-lab','kind':'recovery'})
        api(f'services/{sid}/monitoring', {'url':URL,'enabled':True}, 'PUT')
    wait_until(discovered, 'resumed target discovered without restart')
    wait_until(lambda: service()['status']=='healthy' and any(t['action']=='Serviço recuperado' for t in api(f'incidents/{iid}')['timeline']), 'recovery confirmed after resume')
    case = api(f'incidents/{iid}')
    if case['status']=='open':
        api(f'incidents/{iid}/assign', {'user_id':user['id']})
        api(f'incidents/{iid}', {'status':'acknowledged','note':'Ensaio da ligação configurável reconhecido.'},'PATCH')
    if api(f'incidents/{iid}')['status']=='acknowledged':
        api(f'incidents/{iid}', {'status':'investigating','note':'Verificadas descoberta, falha HTTP e pausa sem perda do histórico.'},'PATCH')
    api(f'incidents/{iid}', {'status':'resolved','note':'Falha de laboratório removida; recolha retomada com sondagens saudáveis.'},'PATCH')
    api(f'incidents/{iid}', {'status':'closed','root_cause':'Falha HTTP deliberada no laboratório, com pausa e retoma da recolha.',
                            'prevention':'Rever os endereços autorizados e confirmar novas sondagens após cada retoma.',
                            'runbook':'Verificar a ligação em Monitorização; consultar a última sondagem; recuperar o serviço; retomar a recolha; aguardar duas sondagens saudáveis.'},'PATCH')
    evidence = {'status':'passed','executed_at':datetime.now(timezone.utc).isoformat(),'service_id':sid,'target_key':key,
                'incident_id':iid,'service_status':service()['status'],'samples':service()['sample_count'],
                'steps':['inventory registration','approved URL association','authenticated HTTP discovery','real measurements',
                         'automatic incident','pause removes target','pause preserves history','resume without restart','confirmed recovery','manual closure']}
    (Path(__file__).resolve().parent.parent/'docs'/'validacao-monitorizacao.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=True),flush=True)


if __name__=='__main__':
    main()
