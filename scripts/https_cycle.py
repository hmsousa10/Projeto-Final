"""Two controlled outages of the private preproduction fixture; never targets customer deployments."""
from datetime import datetime, timezone
from http.cookies import SimpleCookie
import json
from pathlib import Path
import runpy
import ssl
import subprocess
import sys
import time
from urllib.parse import urlencode
import uuid

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from scripts.preproduction import prepare,context,ORIGIN


def approved_api(container):
    labels=container.get('Config',{}).get('Labels',{})
    if labels.get('com.docker.compose.project')!='nexo-preproduction' or labels.get('com.docker.compose.service')!='enterprise-api':
        raise ValueError('A interrupção só é permitida na API fictícia da pré-produção.')
    if any(container.get('NetworkSettings',{}).get('Ports',{}).values()):
        raise ValueError('A API de ensaio deve ser privada.')
    values=container['Config'].get('Env',[])
    if container['Config'].get('Cmd') != ['python','-m','app.customer_fixture']:
        raise ValueError('O contentor não executa a API fictícia prevista.')
    if 'ENTERPRISE_COMPANY_ID=aurora' not in values or 'FIXTURE_TLS_KEY_FILE=/run/secrets/enterprise_private' not in values:
        raise ValueError('A API não tem a identidade e o TLS esperados.')
    if not container.get('State',{}).get('Running'):
        raise ValueError('A API deve estar ativa antes do ensaio.')
    return container['Id']


def wait_for(check,label,timeout=55):
    deadline=time.monotonic()+timeout
    while True:
        value=check()
        if value:
            return value
        if time.monotonic()>=deadline:
            raise RuntimeError('Tempo excedido: '+label)
        time.sleep(2)


def source_history(docker):
    code="import json; from app.maintenance import fingerprint; print(json.dumps(fingerprint('/app/data/nexo.db')))"
    return {name:json.loads(subprocess.check_output([docker,'exec',name,'python','-c',code],text=True,timeout=15))
            for name in ('nexo-lab-nexo-1','nexo-test-atlas-nexo-1')}


def main():
    folder=prepare(ROOT);command,_=context(ROOT,folder);docker=command[0]
    container=json.loads(subprocess.check_output([docker,'inspect','nexo-preproduction-enterprise-api-1'],text=True,timeout=15))[0]
    target=approved_api(container)
    edge=runpy.run_path(str(ROOT/'scripts/validar-https.py'),run_name='tls_transport')
    transport=edge['request'];tls=ssl.create_default_context(cafile=str(folder/'root.crt'))
    headers={'Origin':ORIGIN}

    def api(method,path,body=None,expected=200):
        status,_,raw,_,_=transport(tls,method,'/api'+path,body,headers)
        if status!=expected:
            raise RuntimeError('Resposta inesperada em '+path+': '+str(status))
        return json.loads(raw) if raw else None

    before=source_history(docker)
    run_id=uuid.uuid4().hex[:12]
    report={'run_id':run_id,'started_at':datetime.now(timezone.utc).isoformat(),'scope':'controlled preproduction fixture only',
            'timing_scope':'automated test timings, not human MTTA/MTTR','cycles':[],'passed':False}
    stopped=False;logged=False
    try:
        status,response,_,_,_=transport(tls,'POST','/api/login',{'email':'admin@preprod.test',
                     'password':(folder/'initial-admin.key').read_text(encoding='utf-8')},headers)
        if status!=200:
            raise RuntimeError('Não foi possível autenticar no ensaio.')
        cookie=SimpleCookie();cookie.load(response['set-cookie']);headers['Cookie']='nexo_session='+cookie['nexo_session'].value
        logged=True
        uid=api('GET','/me')['id']
        summary=api('GET','/enterprise/summary');sid=summary['monitoring']['service_id']
        if summary['status']!='connected' or summary['summary']['environment']!='laboratory' or summary['monitoring']['collection_state']!='running':
            raise RuntimeError('O ensaio exige a API fictícia saudável e recolha ativa.')
        rule=next(r['config'] for r in api('GET','/alert-rules') if r['service_id']==sid)
        if not (rule['enabled'] and rule['outage_enabled'] and rule['failure_samples']==2 and rule['recovery_samples']==2):
            raise RuntimeError('O ensaio exige as regras de confirmação 2/2 ativas; não serão alteradas.')
        cases=lambda:[i for i in api('GET','/incidents') if i['service_id']==sid and i['source']=='enterprise-alert']
        if any(i['status'] not in ('resolved','closed') for i in cases()):
            raise RuntimeError('Existe um incidente ativo desta API. Trata-o antes de iniciar outro ensaio.')
        previous=None
        for number in (1,2):
            known={i['id'] for i in cases()};started=time.monotonic()
            # Set the guard before calling Docker: a timeout after a successful stop still restores the service.
            stopped=True
            subprocess.run([docker,'stop','-t','5',target],check=True,capture_output=True,timeout=15)
            incident=wait_for(lambda:next((i for i in cases() if i['id'] not in known),None),'deteção da falha')
            iid=incident['id'];detected=time.monotonic()-started
            item={'number':number,'incident_id':iid,'detected_seconds':round(detected,3)}
            report['cycles'].append(item)
            api('POST',f'/incidents/{iid}/assign',{'user_id':uid})
            api('PATCH',f'/incidents/{iid}',{'status':'acknowledged'})
            api('PATCH',f'/incidents/{iid}',{'status':'investigating'})
            api('POST',f'/incidents/{iid}/comments',{'note':f'Ensaio HTTPS {run_id}: interrupção real e controlada do contentor privado da API; tratamento automatizado.'},201)
            api('PATCH',f'/incidents/{iid}',{'status':'resolved','note':'Tentativa de resolução antes da recuperação confirmada.'},409)
            item['premature_resolution_denied']=True
            if previous is not None:
                query=urlencode({'q':run_id+' API HTTPS Aurora recuperação','method':'bm25','scope':'operational','service_id':sid,'exclude_id':iid})
                found=api('GET','/knowledge?'+query)
                if not any(r['id']==previous for r in found['results']):
                    raise RuntimeError('O caso anterior não foi recuperado pela pesquisa.')
                api('POST',f'/incidents/{iid}/knowledge-use',{'source_incident_id':previous,
                    'reason':f'Ensaio {run_id}: aplicar o procedimento de recuperação HTTPS validado no primeiro ciclo.'},201)
                item['knowledge_source']=previous;item['retrieval_method']=found['method']
            restarted=time.monotonic()
            subprocess.run([docker,'start',target],check=True,capture_output=True,timeout=15);stopped=False
            current=wait_for(lambda:next((c for c in [api('GET',f'/incidents/{iid}')] if any(e['action']=='Serviço recuperado' for e in c['timeline'])),None),'recuperação confirmada')
            item['recovery_seconds']=round(time.monotonic()-restarted,3)
            api('PATCH',f'/incidents/{iid}',{'status':'resolved','note':'Duas respostas válidas recentes confirmaram a recuperação da API HTTPS após reinício controlado.'})
            api('PATCH',f'/incidents/{iid}',{'status':'closed','root_cause':f'Ensaio {run_id}: paragem controlada da API privada HTTPS; não corresponde a avaria de uma empresa real.',
                'prevention':'Usar janela de manutenção, rever saúde e certificado da API e confirmar a recuperação antes de fechar.',
                'runbook':'Consultar ligação HTTPS e certificado; reiniciar apenas a API de ensaio; aguardar duas amostras válidas; resolver e documentar o fecho.'})
            dossier=api('GET',f'/incidents/{iid}/export?format=json')
            if dossier['incident']['status']!='closed' or not dossier['incident']['detection_context']:
                raise RuntimeError('Dossier sem fecho ou contexto de deteção.')
            if previous is not None and not any(e['action']=='Conhecimento aplicado' for e in dossier['incident']['timeline']):
                raise RuntimeError('A referência de conhecimento não foi preservada.')
            output=ROOT/'data'/'https-cycles'/run_id;output.mkdir(parents=True,exist_ok=True)
            (output/f'incident-{iid}.json').write_text(json.dumps(dossier,ensure_ascii=False,indent=2),encoding='utf-8')
            item['closed_and_exported']=True;previous=iid
            print('PASS: ciclo '+str(number)+' / INC-'+str(iid),flush=True)
        after=source_history(docker)
        if any(before[n]['history_sha256']!=after[n]['history_sha256'] for n in before):
            raise RuntimeError('O histórico de outro portal mudou durante o ensaio; requer revisão.')
        report['other_portals_historical_hashes_match']=True
        report['passed']=True
    except Exception as error:
        report['error_type']=type(error).__name__
        raise
    finally:
        if stopped:
            report['emergency_start_requested']=True
            try:
                result=subprocess.run([docker,'start',target],capture_output=True,timeout=15)
                report['emergency_start_succeeded']=result.returncode==0
            except (OSError,subprocess.SubprocessError):
                report['emergency_start_succeeded']=False
            # Always preserve the failure report, including a failed emergency restart.
        if logged:
            try:
                api('POST','/logout')
            except Exception:
                report['logout_confirmed']=False
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        output=ROOT/'data'/'https-cycles'/run_id;output.mkdir(parents=True,exist_ok=True)
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if report['passed']:
            (ROOT/'docs/validacao-ciclo-https-runtime.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    main()
