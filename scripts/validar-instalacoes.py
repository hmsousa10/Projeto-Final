"""Repeatable local rehearsal. Writes a labelled service only in nexo-test-atlas."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from customer_installation import ROOT, compose_command, prepare

MARKER = 'Ensaio Atlas · persistência e isolamento'


def check(condition, label):
    if not condition:
        raise RuntimeError('Falhou a verificação: ' + label)


def main():
    profile, directory = prepare(ROOT, 'atlas')
    docker = shutil.which('docker') or str(Path.home() / 'AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe')
    names = ['nexo-lab-nexo-1', 'nexo-test-atlas-nexo-1', 'nexo-test-atlas-portal-lab-1']

    def inspect():
        return json.loads(subprocess.check_output([docker, 'inspect', *names], text=True, timeout=20))

    def counts():
        code = "import sqlite3,json; d=sqlite3.connect('file:/app/data/nexo.db?mode=ro',uri=True); print(json.dumps({t:d.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('services','incidents','timeline')}))"
        return json.loads(subprocess.check_output([docker, 'exec', names[0], 'python', '-c', code], text=True, timeout=20))

    containers = inspect()
    check(containers[1]['Config']['Labels']['com.docker.compose.project'] == 'nexo-test-atlas', 'projeto de ensaio')
    check(len({c['Image'] for c in containers}) == 1, 'mesma imagem nas três aplicações')
    before = counts()
    base = 'http://localhost:' + str(profile['port'])
    password = (directory / 'initial-admin.key').read_text(encoding='utf-8')
    with httpx.Client(base_url='http://127.0.0.1:8001', trust_env=False, timeout=10) as aurora, \
         httpx.Client(base_url=base, trust_env=False, timeout=10) as atlas:
        check(aurora.get('/api/config').json()['demo'] is True, 'Aurora é laboratório')
        check(atlas.get('/api/config').json()['demo'] is False, 'Atlas sem dados semeados')
        check(aurora.post('/api/login', json={'email': 'admin@local.test', 'password': 'EstudoLocal2026!'}).status_code == 200, 'acesso Aurora local')
        check(atlas.post('/api/login', json={'email': profile['email'], 'password': password}).status_code == 200, 'acesso Atlas')
        check(atlas.get('/api/admin/users').json()[0]['email'] == profile['email'], 'conta própria')
        check(len(atlas.get('/api/admin/users').json()) == 1, 'sem contas de demonstração')
        token_a, token_b = aurora.cookies.get('nexo_session'), atlas.cookies.get('nexo_session')
        check(atlas.get('/api/services', headers={'Cookie': 'nexo_session=' + token_a}).status_code == 401, 'sessão Aurora recusada na Atlas')
        check(aurora.get('/api/services', headers={'Cookie': 'nexo_session=' + token_b}).status_code == 401, 'sessão Atlas recusada na Aurora')
        summary = atlas.get('/api/enterprise/summary').json()
        check(summary['status'] == 'connected' and summary['summary']['company_id'] == 'atlas', 'contrato da Atlas')
        check(aurora.get('/api/enterprise/summary').json()['summary']['company_id'] == 'aurora', 'contrato Aurora')
        check(atlas.post('/api/lab/fault', json={'target': 'portal-lab', 'kind': 'outage'}).status_code == 404, 'controlos de falha desativados')
        services = atlas.get('/api/services').json()
        marker = next((s for s in services if s['name'] == MARKER), None)
        if marker is None:
            created = atlas.post('/api/services', json={'name': MARKER, 'team': 'Ensaio Atlas',
                                 'description': 'Registo criado pelo ensaio automatizado para verificar persistência; dados fictícios.'})
            check(created.status_code == 201, 'registo de ensaio criado')
            marker = created.json()
        check(not any(s['name'] == MARKER for s in aurora.get('/api/services').json()), 'registo ausente na Aurora')
        old_ids = [c['Id'] for c in containers[1:]]
        compose_command(ROOT, profile, directory, 'recriar')
        containers = inspect()
        check(all(c['Id'] != old for c, old in zip(containers[1:], old_ids)), 'contentores recriados')
        check(any(s['id'] == marker['id'] and s['name'] == MARKER for s in atlas.get('/api/services').json()), 'persistência e sessão após recriação')
        refreshed = atlas.get('/api/enterprise/summary').json()
        check(refreshed['status'] == 'connected', 'recolha após recriação')
    volumes = [{m['Name'] for m in c['Mounts'] if m['Type'] == 'volume'} for c in containers[:2]]
    check(volumes[0].isdisjoint(volumes[1]), 'volumes independentes')
    networks = [set(c['NetworkSettings']['Networks']) for c in containers]
    check(networks[0].isdisjoint(networks[1] | networks[2]), 'redes separadas')
    check(not any(containers[2]['NetworkSettings']['Ports'].values()), 'API de ensaio sem porta publicada')
    private = json.loads(subprocess.check_output([docker, 'network', 'inspect', 'nexo-test-atlas_private'], text=True, timeout=20))[0]
    check(private['Internal'] is True, 'rede da API interna')
    check(all(not m['RW'] for c in containers[1:] for m in c['Mounts'] if m['Destination'].startswith('/run/secrets/')), 'segredos montados apenas para leitura')
    check(counts() == before, 'inventário e incidentes principais preservados')
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'version': '0.27.0',
              'checks': ['same_image', 'distinct_company_and_accounts', 'session_replay_401_both_directions',
                         'private_api_no_published_port', 'independent_volumes_and_networks', 'readonly_secret_mounts',
                         'no_fault_controls', 'force_recreate_persistence', 'main_data_preserved'],
              'main_before': before, 'main_after': counts(), 'atlas_service_marker_id': marker['id'],
              'atlas_company': refreshed['summary']['company_id'], 'atlas_summary_status': refreshed['status'],
              'volumes': [sorted(v) for v in volumes], 'networks': [sorted(n) for n in networks],
              'image': containers[0]['Image'], 'scope': 'Local rehearsal with fictional data; not a production security certification.'}
    (ROOT / 'docs/validacao-instalacoes-runtime.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS: identidades, sessões, volumes, redes, segredos e persistência. Aurora preservada.')


if __name__ == '__main__':
    main()
