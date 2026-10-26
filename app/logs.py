"""Authenticated application facade over an internal Loki deployment."""
import json
import math
import time
from urllib.parse import urlencode
from urllib.request import build_opener, ProxyHandler

from .telemetry import NoRedirect, TARGETS


def read_logs(url, target):
    if target not in TARGETS:
        raise ValueError('Alvo inválido')
    end = time.time_ns()
    query = urlencode({'query': '{app="nexo-lab",service_key="' + target + '"}',
                       'start': str(end - 15 * 60 * 10**9), 'end': str(end), 'limit': '50', 'direction': 'backward'})
    with build_opener(ProxyHandler({}), NoRedirect()).open(url + '/loki/api/v1/query_range?' + query, timeout=5) as response:
        raw = response.read(512 * 1024 + 1)
    if len(raw) > 512 * 1024:
        raise ValueError('Resposta excessiva')
    payload = json.loads(raw)
    if payload.get('status') != 'success' or payload.get('data', {}).get('resultType') != 'streams':
        raise ValueError('Resposta inválida')
    entries = []
    for stream in payload['data']['result']:
        for stamp, line in stream['values']:
            value = json.loads(line)
            if value.get('path') not in ('/', '/health', '/api/orders', '/company.css', '/company.js'):
                continue
            if not math.isfinite(float(value['duration_ms'])) or not 100 <= int(value['status']) <= 599:
                raise ValueError('Registo inválido')
            int(stamp)
            entries.append({'timestamp_ns': stamp, 'method': str(value.get('method', ''))[:10],
                            'path': str(value.get('path', ''))[:100], 'status': int(value['status']),
                            'duration_ms': float(value['duration_ms'])})
    return sorted(entries, key=lambda r: int(r['timestamp_ns']), reverse=True)[:50]
