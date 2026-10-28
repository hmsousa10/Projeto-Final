"""Authenticated application facade over an internal Loki deployment."""
import json
import math
import time
from urllib.parse import urlencode
from urllib.request import build_opener, ProxyHandler

from .telemetry import NoRedirect, TARGETS
from . import monitoring


# Explicit deployment catalog: probe identity alone never grants access to a log stream.
# Health probes describe the entire reference service; orders probes describe only that endpoint.
BINDINGS = {
    monitoring.LAB_URLS['portal-lab']: ('portal-lab', None),
    monitoring.LAB_URLS['api-lab']: ('api-lab', None),
    'http://portal-lab:8080/api/orders': ('portal-lab', '/api/orders'),
}
PATHS = ('/', '/health', '/api/orders', '/api/operations/summary', '/company.css', '/company.js')


def binding(target):
    if target is None or target['target_url'] not in monitoring.allowed_urls():
        return None
    selected = BINDINGS.get(target['target_url'])
    if selected is None:
        return None
    key, path = selected
    return {'version': 1, 'target_url': target['target_url'], 'service_key': key,
            'path': path, 'kind': 'endpoint' if path else 'service'}


def read_logs(url, target, path=None):
    if target not in TARGETS:
        raise ValueError('Alvo inválido')
    if path is not None and path not in PATHS:
        raise ValueError('Caminho inválido')
    end = time.time_ns()
    start = end - 15 * 60 * 10**9
    expression = '{app="nexo-lab",service_key="' + target + '"}'
    if path is not None:
        expression += ' | json | __error__="" | path=' + json.dumps(path)
    query = urlencode({'query': expression,
                       'start': str(start), 'end': str(end), 'limit': '50', 'direction': 'backward'})
    with build_opener(ProxyHandler({}), NoRedirect()).open(url + '/loki/api/v1/query_range?' + query, timeout=5) as response:
        raw = response.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError('Resposta excessiva')
    payload = json.loads(raw)
    if payload.get('status') != 'success' or payload.get('data', {}).get('resultType') != 'streams':
        raise ValueError('Resposta inválida')
    entries = []
    for stream in payload['data']['result']:
        if stream.get('stream', {}).get('service_key') != target:
            raise ValueError('Origem dos logs inválida')
        for stamp, line in stream['values']:
            value = json.loads(line)
            if value.get('path') not in PATHS or (path is not None and value['path'] != path):
                continue
            if not math.isfinite(float(value['duration_ms'])) or float(value['duration_ms']) < 0 or not 100 <= int(value['status']) <= 599:
                raise ValueError('Registo inválido')
            if not start <= int(stamp) <= end:
                continue
            entries.append({'timestamp_ns': stamp, 'method': str(value.get('method', ''))[:10],
                            'path': str(value.get('path', ''))[:100], 'status': int(value['status']),
                            'duration_ms': float(value['duration_ms'])})
    return sorted(entries, key=lambda r: int(r['timestamp_ns']), reverse=True)[:50]
