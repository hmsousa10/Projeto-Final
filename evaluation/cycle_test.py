"""Repeatable real HTTP experiment; fixed disposable ports, no live-stack mode."""
import argparse
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import json
from pathlib import Path
import statistics
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor, ProxyHandler

from app.telemetry import NoRedirect
from evaluation.cycle_server import FIXTURE, DATABASE

ROOT = Path(__file__).resolve().parent.parent
BASE = 'http://127.0.0.1:8011/api/'
ORDERS = 'http://127.0.0.1:8012/api/orders'


def utc():
    return datetime.now(timezone.utc).isoformat()


def require(condition, label):
    if not condition:
        raise AssertionError(label)


def validate_marker(marker, digest):
    require(marker.get('fixture') == FIXTURE and marker.get('storage') == 'tmpfs'
            and marker.get('database') == DATABASE, 'Not the isolated cycle fixture')
    require(marker.get('source_sha256', {}).get('evaluation/cycle_protocol.json') == digest,
            'Container protocol differs from the local frozen protocol; rebuild')


def current_failure(entries, since_ns):
    return any(e['status'] == 503 and int(e['timestamp_ns']) >= since_ns for e in entries)


def recovered(case, since):
    return any(e['action'] == 'Serviço recuperado' and
               datetime.fromisoformat(e['created_at']).timestamp() >= since
               for e in case['timeline'])


def run(report):
    protocol_bytes = (ROOT / 'evaluation/cycle_protocol.json').read_bytes()
    protocol = json.loads(protocol_bytes)
    digest = hashlib.sha256(protocol_bytes).hexdigest()
    client = build_opener(ProxyHandler({}), NoRedirect(),
                          HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def api(path, body=None, method=None):
        request = Request(BASE + path, method=method,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={'Content-Type': 'application/json'})
        with client.open(request, timeout=8) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        require(len(raw) <= 2 * 1024 * 1024, 'Response limit exceeded')
        return json.loads(raw)

    def wait(check, label):
        end = time.monotonic() + protocol['phase_timeout_seconds']
        while time.monotonic() < end:
            result = check()
            if result:
                return result
            time.sleep(protocol['poll_seconds'])
        raise AssertionError('Timeout: ' + label)

    def fault(kind):
        return api('lab/fault', {'target': 'portal-lab', 'kind': kind})

    def orders():
        try:
            with client.open(ORDERS, timeout=5) as response:
                return response.status
        except HTTPError as error:
            return error.code

    marker = api('cycle-test-marker')
    validate_marker(marker, digest)  # Before login, before any fault or mutation.
    report.update(fixture=marker, protocol=protocol, protocol_sha256=digest)
    user = api('login', {'email': 'admin@local.test', 'password': 'EstudoLocal2026!'})
    services = api('services')
    service = next(s for s in services if s['name'] == 'Laboratório · Portal HTTP')
    sid = service['id']
    report['service_id'] = sid
    report['initial_incident_count'] = len(api('incidents'))

    def incidents():
        return [i for i in api('incidents') if i['service_id'] == sid]

    require(not incidents(), 'Fixture already has target incidents; start with fresh tmpfs')
    previous = None
    fault_attempted = False
    try:
        wait(lambda: next(s for s in api('services') if s['id'] == sid)['status'] == 'healthy',
             'initial healthy target')
        require(orders() == 200, 'Initial orders must be HTTP 200')
        for n in range(1, protocol['repetitions'] + 1):
            trial = {'repetition': n, 'events': [], 'status': 'running'}
            report['trials'].append(trial)
            origin = time.monotonic()

            def mark(name):
                point = {'event': name, 'at_utc': utc(),
                         'elapsed_seconds': round(time.monotonic() - origin, 6)}
                trial['events'].append(point)
                return point['elapsed_seconds']

            known = {i['id'] for i in incidents()}
            since_ns = time.time_ns()
            injected_wall = since_ns / 1e9
            fault_attempted = True
            injection = mark('fault_request_start')
            trial['fault_control'] = fault('outage')
            mark('fault_request_end')
            require(orders() == 503, 'Actual orders HTTP 503 required')
            mark('orders_503_observed')
            case = wait(lambda: next((i for i in incidents() if i['id'] not in known), None),
                        'new automatic incident')
            detected = mark('incident_observed')
            iid = case['id']
            trial['incident_id'] = iid
            require(case['source'] == 'prometheus-alert' and case['severity'] == 'P1',
                    'Automatic P1 required')
            require(datetime.fromisoformat(case['created_at']).timestamp() >= injected_wall,
                    'Incident predates the failure')
            api(f'incidents/{iid}/assign', {'user_id': user['id']})
            api(f'incidents/{iid}', {'status': 'acknowledged',
                'note': f'Ensaio automático isolado {marker["run_id"]}, repetição {n}: HTTP 503 confirmado.'}, 'PATCH')
            ack = mark('script_acknowledged')
            api(f'incidents/{iid}', {'status': 'investigating',
                'note': 'Tratamento por script; consulta de sondagens, logs e conhecimento anterior.'}, 'PATCH')
            try:
                api(f'incidents/{iid}', {'status': 'resolved', 'note': 'Tentativa negativa antes da recuperação.'}, 'PATCH')
            except HTTPError as error:
                require(error.code == 409, 'Premature resolution must return 409')
                trial['premature_resolution_http'] = error.code
            else:
                raise AssertionError('Premature resolution was allowed')

            def logs_ready():
                try:
                    return current_failure(api(f'services/{sid}/logs')['entries'], since_ns)
                except HTTPError as error:
                    if error.code == 503:
                        return False
                    raise

            wait(logs_ready, 'current failure in Loki')
            api(f'incidents/{iid}/evidence', {})
            detail = api(f'incidents/{iid}')
            require(any(current_failure(e['payload']['entries'], since_ns) for e in detail['evidence']),
                    'Snapshot must preserve a log from this trial')
            mark('current_logs_preserved')
            query = 'knowledge?' + urlencode({'q': protocol['knowledge_query'],
                'method': protocol['knowledge_method'], 'scope': protocol['knowledge_scope'],
                'service_id': sid, 'exclude_id': iid})
            search_start = time.monotonic()
            search = wait(lambda: (r if (r := api(query))['actual_method'] == 'hybrid' else None),
                          'actual hybrid search without fallback')
            trial['knowledge'] = search
            trial['knowledge_wait_seconds'] = round(time.monotonic() - search_start, 6)
            ids = [r['id'] for r in search['results']]
            require(iid not in ids, 'Current case leaked into suggestions')
            require(previous in ids if previous else not ids,
                    'Previous closed trial must be returned; cold trial must have no prior case')
            mark('knowledge_consulted_before_recovery')
            # Fixed delay independent of search speed to observe duplicate suppression.
            time.sleep(protocol['dedup_hold_seconds'])
            current = incidents()
            require(len([i for i in current if i['id'] not in known]) == 1,
                    'Repeated probes created duplicate incidents')
            require(len([i for i in current if i['status'] not in ('resolved', 'closed')]) == 1,
                    'Exactly one active target incident required')
            mark('deduplication_confirmed')
            recovery_wall = time.time()
            recovery = mark('recovery_request_start')
            fault('recovery')
            mark('recovery_request_end')
            require(orders() == 200, 'Orders must recover with HTTP 200')
            mark('orders_200_observed')
            wait(lambda: recovered(api(f'incidents/{iid}'), recovery_wall), 'fresh recovery probes')
            confirmed = mark('probe_recovery_observed')
            api(f'incidents/{iid}', {'status': 'resolved',
                'note': 'Ensaio automático: falha deliberada removida; HTTP 200 e sondagens recentes confirmados.'}, 'PATCH')
            mark('script_resolved')
            api(f'incidents/{iid}', {'status': 'closed',
                'root_cause': 'HTTP 503 provocado deliberadamente na Aurora fictícia, num ambiente tmpfs isolado.',
                'prevention': 'Ensaios apenas em laboratório autorizado; acompanhar sondagens e validar recuperação antes do fecho.',
                'runbook': 'Confirmar HTTP 503 e logs; consultar casos anteriores; remover falha; confirmar HTTP 200 e sondagens; documentar e fechar.'}, 'PATCH')
            closed = mark('script_closed')
            try:
                api(f'incidents/{iid}/comments', {'note': 'Teste negativo de imutabilidade.'})
            except HTTPError as error:
                require(error.code == 409, 'Closed case must reject comment with 409')
                trial['closed_mutation_http'] = error.code
            else:
                raise AssertionError('Closed case accepted a comment')
            detail = api(f'incidents/{iid}')
            actions = {e['action'] for e in detail['timeline']}
            require({'Responsável atribuído', 'Reconhecido', 'Em investigação',
                     'Serviço recuperado', 'Resolvido', 'Fechado'} <= actions,
                    'Required historical transitions missing')
            trial['case'] = detail
            trial['case_sha256'] = hashlib.sha256(json.dumps(detail, sort_keys=True,
                ensure_ascii=False).encode()).hexdigest()
            # Query without excluding the now-closed case; verify it is reusable.
            catalogue = api('knowledge?' + urlencode({'q': protocol['knowledge_query'],
                'method': 'bm25', 'scope': 'operational', 'service_id': sid}))
            require(iid in [r['id'] for r in catalogue['results']], 'Closed case not retrievable')
            trial['seconds'] = {'detection_observed': round(detected - injection, 6),
                'script_ack_after_detection': round(ack - detected, 6),
                'recovery_confirmation_observed': round(confirmed - recovery, 6),
                'injection_to_script_closure': round(closed - injection, 6)}
            trial['status'] = 'passed'
            previous = iid
            print(f'PASS repetition {n}: INC-{iid:03d}, detection {detected:.2f}s, recovery {confirmed-recovery:.2f}s', flush=True)
        require(not any(i['status'] not in ('resolved', 'closed') for i in incidents()),
                'Active target incident left behind')
        require(api('cycle-test-marker')['run_id'] == marker['run_id'], 'Fixture restarted mid-run')
        report['summary_seconds'] = {metric: {
            'n': len(report['trials']), 'min': min(values), 'median': statistics.median(values),
            'max': max(values)} for metric in report['trials'][0]['seconds']
            for values in [[t['seconds'][metric] for t in report['trials']]]}
        report['final_orders_http'] = orders()
        report['status'] = 'passed'
    finally:
        if fault_attempted:
            try:
                fault('recovery')
                report['cleanup_recovery_http'] = orders()
            except (OSError, ValueError) as error:
                report['cleanup_error'] = type(error).__name__
        try:
            api('logout', {})
        except (OSError, ValueError):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Never silently replace an earlier successful or failed experiment.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump({'status': 'started', 'started_at': utc()}, stream)
    report = {'status': 'failed', 'started_at': utc(), 'trials': []}
    try:
        run(report)
    except (OSError, ValueError, AssertionError, KeyError, StopIteration) as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        print('FAIL: ' + str(error), flush=True)
    finally:
        report['finished_at'] = utc()
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
