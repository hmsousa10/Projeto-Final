"""Bounded, read-only Prometheus integration. Targets are deployment configuration."""
import asyncio
import json
import math
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from .db import database, now
from .alerts import evaluate
from . import monitoring

TARGETS = {'portal-lab': 'Laboratório · Portal HTTP', 'api-lab': 'Laboratório · API HTTP'}
QUERY = '{__name__=~"probe_success|probe_duration_seconds",job="nexo-probes"}[2m]'
FRESH_SECONDS = 45


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_url(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise RuntimeError('PROMETHEUS_URL exige uma origem HTTP(S), sem credenciais ou caminhos.')
    return url.rstrip('/')


def fetch_metrics(url):
    # No ambient proxy or redirects: the deployment selects the upstream explicitly.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    endpoint = url + '/api/v1/query?' + urlencode({'query': QUERY, 'timeout': '3s'})
    with opener.open(endpoint, timeout=5) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('Resposta excessiva')
    payload = json.loads(raw)
    if payload.get('status') != 'success' or payload.get('data', {}).get('resultType') != 'matrix':
        raise ValueError('Resposta inválida')
    return payload['data']['result']


def initialize_targets(path):
    with database(path) as db:
        for key, name in TARGETS.items():
            if db.execute('SELECT 1 FROM telemetry_targets WHERE target_key=?', (key,)).fetchone():
                db.execute("UPDATE telemetry_targets SET target_url=? WHERE target_key=? AND target_url=''", (monitoring.LAB_URLS[key], key))
                continue
            cursor = db.execute('''INSERT INTO services
                (name,team,description,criticality,slo_availability,slo_latency_ms,created_at)
                VALUES(?, 'Laboratório', 'Sondagens HTTP reais sobre um serviço de teste isolado.', 'Média', 99.9, 500, ?)''', (name, now()))
            db.execute('INSERT INTO telemetry_targets(target_key,service_id,target_url) VALUES(?,?,?)',
                       (key, cursor.lastrowid, monitoring.LAB_URLS[key]))


def import_samples(path, series, clock=None):
    clock = time.time() if clock is None else clock
    values = {}
    with database(path) as db:
        targets = monitoring.active_targets(db)
    for item in series:
        metric = item.get('metric', {})
        key, name = metric.get('service_key'), metric.get('__name__')
        if key not in targets or name not in ('probe_success', 'probe_duration_seconds'):
            continue
        for stamp, raw in item.get('values', []):
            stamp, value = float(stamp), float(raw)
            if not math.isfinite(stamp) or not math.isfinite(value) or stamp > clock + 5 or clock - stamp > 120:
                continue
            if targets[key]['updated_at'] and stamp < datetime.fromisoformat(targets[key]['updated_at']).timestamp():
                continue
            values.setdefault((key, stamp), {})[name] = value
    inserted = 0
    fresh = set()
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        # Re-read inside the write transaction: a concurrent pause wins over in-flight responses.
        targets = monitoring.active_targets(db)
        for (key, stamp), pair in sorted(values.items()):
            if key not in targets or (targets[key]['updated_at'] and stamp < datetime.fromisoformat(targets[key]['updated_at']).timestamp()):
                continue
            success, duration = pair.get('probe_success'), pair.get('probe_duration_seconds')
            if success not in (0, 1) or duration is None or not 0 <= duration <= 120:
                continue
            if clock - stamp <= FRESH_SECONDS:
                fresh.add(key)
            service = db.execute('SELECT service_id FROM telemetry_targets WHERE target_key=?', (key,)).fetchone()
            if service:
                result = db.execute('''INSERT OR IGNORE INTO observations
                    (service_id,available,latency_ms,source,observed_at) VALUES(?,?,?,'prometheus',?)''',
                    (service['service_id'], int(success), duration * 1000, datetime.fromtimestamp(stamp, timezone.utc).isoformat()))
                inserted += result.rowcount
        evaluate(db, clock)
        state = {'status': 'no_targets' if not targets else 'connected' if len(fresh) == len(targets) else 'incomplete',
                 'last_attempt': now(), 'fresh_targets': len(fresh), 'expected_targets': len(targets)}
        db.execute("INSERT OR REPLACE INTO settings VALUES('telemetry_state',?)", (json.dumps(state),))
    return inserted


def collect(path, url):
    try:
        return import_samples(path, fetch_metrics(url))
    except Exception:
        # Upstream errors must never become successful observations or disclose addresses.
        with database(path) as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES('telemetry_state',?)",
                       (json.dumps({'status': 'unavailable', 'last_attempt': now(), 'fresh_targets': 0,
                                    'expected_targets': len(monitoring.active_targets(db))}),))
        return 0


async def run_collector(path, url):
    while True:
        await asyncio.to_thread(collect, path, url)
        await asyncio.sleep(10)


def status(path, enabled):
    with database(path) as db:
        row = db.execute("SELECT value FROM settings WHERE key='telemetry_state'").fetchone()
    result = json.loads(row['value']) if row and enabled else {'status': 'waiting' if enabled else 'disabled'}
    if result.get('last_attempt') and (datetime.now(timezone.utc) - datetime.fromisoformat(result['last_attempt'])).total_seconds() > FRESH_SECONDS:
        result['status'] = 'stale'
        result['fresh_targets'] = 0
    return {**result, 'enabled': enabled, 'source': 'prometheus', 'freshness_seconds': FRESH_SECONDS}
