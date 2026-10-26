"""Real HTTP failure -> probes -> automatic incident -> recovery -> knowledge."""
import json
import os
from pathlib import Path
import runpy
import time
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import urlopen

helpers = runpy.run_path(str(Path(__file__).with_name('validar-laboratorio.py')))
api, wait_until = helpers['api'], helpers['wait_until']


def portal_status():
    try:
        with urlopen('http://127.0.0.1:8002/api/orders', timeout=5) as response:
            return response.status
    except HTTPError as error:
        return error.code


def main():
    def ready():
        try:
            return api('health')['status'] == 'ok'
        except (OSError, HTTPError):
            return False
    wait_until(ready, 'application ready')
    user = api('login', {'email': 'admin@local.test', 'password': os.getenv('DEMO_PASSWORD', 'EstudoLocal2026!')})
    service = next(s for s in api('services') if s['name'] == 'Laboratório · Portal HTTP')
    sid = service['id']
    def incidents():
        return [i for i in api('incidents') if i['service_id'] == sid and i['source'] == 'prometheus-alert']
    def active():
        return next((i for i in incidents() if i['status'] not in ('resolved','closed')), None)
    api('lab/fault', {'target': 'portal-lab', 'kind': 'recovery'})
    wait_until(lambda: next(s for s in api('services') if s['id']==sid)['status']=='healthy', 'portal initially healthy')
    # Resume any existing laboratory episode rather than deleting its history.
    fault_start = time.time()
    def recovered(iid, since):
        return any(t['action']=='Serviço recuperado' and datetime.fromisoformat(t['created_at']).timestamp() >= since
                   for t in api(f'incidents/{iid}')['timeline'])
    def log_evidence():
        try:
            return any(e['status']==503 for e in api(f'services/{sid}/logs')['entries'])
        except HTTPError as error:
            if error.code == 503:
                return False
            raise
    try:
        api('lab/fault', {'target': 'portal-lab', 'kind': 'outage'})
        assert portal_status() == 503
        print('PASS: company orders endpoint returns actual HTTP 503', flush=True)
        wait_until(lambda: active() is not None, 'automatic incident created')
        incident = active()
        iid = incident['id']
        assert incident['severity'] == 'P1'
        time.sleep(12)
        assert len([i for i in incidents() if i['status'] not in ('resolved','closed')]) == 1
        print('PASS: repeated probes do not duplicate active incident', flush=True)
        wait_until(log_evidence, 'HTTP 503 visible in Loki')
        api(f'incidents/{iid}/evidence', {})
        assert any(e['status']==503 for snapshot in api(f'incidents/{iid}')['evidence'] for e in snapshot['payload']['entries'])
        print('PASS: HTTP evidence preserved in the case history', flush=True)
        if incident['status'] == 'open':
            api(f'incidents/{iid}/assign', {'user_id': user['id']})
            api(f'incidents/{iid}', {'status':'acknowledged','note':'Ensaio de integração real: falha HTTP confirmada.'}, 'PATCH')
        if api(f'incidents/{iid}')['status'] == 'acknowledged':
            api(f'incidents/{iid}', {'status':'investigating','note':'Investigação dos logs Loki e das sondagens Prometheus.'}, 'PATCH')
        api(f'incidents/{iid}/comments', {'note':'Ensaio real no laboratório: /api/orders devolveu HTTP 503; os logs Loki confirmaram o erro. Não representa uma ocorrência numa empresa real.'})
    finally:
        api('lab/fault', {'target': 'portal-lab', 'kind': 'recovery'})
    assert portal_status() == 200
    wait_until(lambda: recovered(iid, fault_start), 'recovery recorded in incident timeline')
    api(f'incidents/{iid}', {'status':'resolved', 'note':'Controlo de falha removido. Pedidos HTTP 200 e duas sondagens recentes confirmaram a recuperação.'}, 'PATCH')
    api(f'incidents/{iid}', {'status':'closed', 'root_cause':'Falha HTTP 503 provocada deliberadamente no serviço de teste da Aurora durante o ensaio académico.',
                            'prevention':'Executar ensaios controlados fora de produção, validar sondagens e acompanhar os logs após alterações.',
                            'runbook':'1. Confirmar HTTP 503 nos logs. 2. Identificar a alteração. 3. Recuperar o serviço no laboratório. 4. Confirmar HTTP 200 e duas sondagens saudáveis. 5. Registar resolução e prevenção.'}, 'PATCH')
    from urllib.parse import urlencode
    results = api('knowledge?' + urlencode({'q':'Serviço indisponível Laboratório Portal HTTP 503 sondagens'}))['results']
    assert iid in [r['id'] for r in results]
    print('PASS: closed case returned by knowledge search', flush=True)
    # A second actual occurrence proves knowledge is available during a new case.
    try:
        second_start = time.time()
        api('lab/fault', {'target':'portal-lab','kind':'outage'})
        wait_until(lambda: active() is not None and active()['id'] != iid, 'new failure creates a new case after recovery and closure')
        second = active()['id']
        assert iid in [r['id'] for r in api('knowledge?' + urlencode({'q':active()['description']}))['results']]
    finally:
        api('lab/fault', {'target':'portal-lab','kind':'recovery'})
    wait_until(lambda: recovered(second, second_start), 'second failure recovered; incident available for manual treatment')
    evidence = {'status':'passed','executed_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
                'closed_incident_id':iid,'followup_incident_id':second,'service_id':sid,
                'company_http_status':portal_status(),'knowledge_method':'TF-IDF',
                'steps':['actual HTTP 503','automatic P1','deduplication','Loki evidence','assignment','investigation','HTTP recovery','manual resolution','post-mortem closure','knowledge retrieval','new occurrence']}
    (Path(__file__).resolve().parent.parent/'docs'/'validacao-ciclo-real.json').write_text(json.dumps(evidence, ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
