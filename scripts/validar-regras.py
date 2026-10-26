"""Real latency detection and acknowledgement escalation, including a collector outage."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy
import time

helpers=runpy.run_path(str(Path(__file__).with_name('validar-laboratorio.py')))
api,wait_until,compose=helpers['api'],helpers['wait_until'],helpers['compose']


def main():
    user=api('login',{'email':'admin@local.test','password':os.getenv('DEMO_PASSWORD','EstudoLocal2026!')})
    service=next(s for s in api('services') if s.get('monitoring') and s['monitoring']['target_key']=='service-7')
    sid=service['id']
    def active():
        return next((i for i in api('incidents') if i['service_id']==sid and i['source']=='prometheus-alert' and i['status'] not in ('resolved','closed')),None)
    if active():
        raise RuntimeError('Este serviço já tem um caso ativo. O ensaio não altera casos anteriores por tratar.')
    previous=next(r for r in api('alert-rules') if r['service_id']==sid)
    config={**previous['config'],'enabled':True,'latency_enabled':True,'latency_ms':500,'failure_samples':3,
            'recovery_samples':2,'latency_severity':'P3','escalation_enabled':True,'acknowledge_seconds':15}
    saved=api(f'services/{sid}/alert-rule',config,'PUT')
    iid=None
    try:
        try:
            api('lab/fault',{'target':'portal-lab','kind':'latency'})
            wait_until(lambda:active() is not None,'three actual HTTP probes create the configured incident',timeout=65)
            incident=active()
            iid=incident['id']
            assert incident['severity']=='P3'
            assert api(f'incidents/{iid}')['detection_context']['config']['failure_samples']==3
            print('PASS: initial priority P3 and detection policy preserved',flush=True)
            compose('stop','prometheus')
            wait_until(lambda:api('telemetry')['status']=='unavailable','Prometheus collection outage visible')
            wait_until(lambda:api(f'incidents/{iid}')['severity']=='P1','unacknowledged incident escalates to P1 during collector outage')
            case=api(f'incidents/{iid}')
            assert case['escalation']['from_severity']=='P3'
            assert case['escalation']['deadline_seconds']==15
            assert api('alert-engine')['status']=='running'
            time.sleep(6)
            case=api(f'incidents/{iid}')
            assert sum(t['action']=='Escalonamento por falta de reconhecimento' for t in case['timeline'])==1
            print('PASS: one escalation only; independent deadline engine remains active',flush=True)
        finally:
            compose('start','prometheus')
            api('lab/fault',{'target':'portal-lab','kind':'recovery'})
            # Keep the test rule until recovery is confirmed; restore the previous policy below.
        wait_until(lambda:any(t['action']=='Serviço recuperado' for t in api(f'incidents/{iid}')['timeline']),'recovery confirmed after Prometheus restart')
        api(f'incidents/{iid}/assign',{'user_id':user['id']})
        api(f'incidents/{iid}',{'status':'acknowledged','note':'Ensaio de prazo reconhecido após confirmar o escalonamento único.'},'PATCH')
        api(f'incidents/{iid}',{'status':'investigating','note':'Confirmadas três sondagens de latência, prioridade P3 e escalonamento para P1 com Prometheus parado.'},'PATCH')
        api(f'incidents/{iid}',{'status':'resolved','note':'Latência controlada removida; Prometheus reposto e recuperação confirmada por duas sondagens.'},'PATCH')
        api(f'incidents/{iid}',{'status':'closed','root_cause':'Ensaio académico deliberado de latência HTTP e falta de reconhecimento durante 15 segundos.',
                                'prevention':'Definir prazos adequados ao serviço, acompanhar incidentes abertos e validar o motor de escalonamento.',
                                'runbook':'Confirmar métricas e regra aplicada; reconhecer o caso; verificar o motor de prazos; recuperar o serviço; confirmar sondagens; registar o post-mortem.'},'PATCH')
        evidence={'status':'passed','executed_at':datetime.now(timezone.utc).isoformat(),'service_id':sid,'incident_id':iid,
                  'rule_version':saved['version'],'initial_severity':'P3','escalated_severity':'P1','deadline_seconds':15,
                  'steps':['three-probe latency detection','P3 incident','policy snapshot','Prometheus outage',
                           'independent time escalation','one-time escalation','recovery','manual closure','policy restored']}
    finally:
        api(f'services/{sid}/alert-rule',previous['config'],'PUT')
    (Path(__file__).resolve().parent.parent/'docs'/'validacao-regras.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence),flush=True)


if __name__=='__main__':
    main()
