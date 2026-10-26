"""Acceptance test for the dedicated nexo-lab stack; restores stopped services."""
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
DOCKER = shutil.which('docker') or str(Path(os.environ['LOCALAPPDATA']) / 'Programs/DockerDesktop/resources/bin/docker.exe')
COMPOSE = [DOCKER, 'compose', '-p', 'nexo-lab', '-f', str(ROOT / 'compose.observability.yaml')]
http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def api(path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request('http://127.0.0.1:8001/api/' + path, data=data, method=method,
                                 headers={'Content-Type': 'application/json'})
    with http.open(req, timeout=5) as response:
        return json.load(response)


def compose(*args):
    subprocess.run([*COMPOSE, *args], check=True, capture_output=True, timeout=30)


def wait_until(check, label, timeout=55):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            print('PASS: ' + label, flush=True)
            return
        time.sleep(2)
    raise AssertionError(label)


def labs():
    return {s['name']: s for s in api('services') if s['telemetry_source'] == 'prometheus'}


def main():
    api('login', {'email': 'admin@local.test', 'password': os.getenv('DEMO_PASSWORD', 'EstudoLocal2026!')})
    wait_until(lambda: api('telemetry')['status'] == 'connected', 'Prometheus connected')
    initial = labs()
    assert initial['Laboratório · Portal HTTP']['status'] == 'healthy'
    assert initial['Laboratório · API HTTP']['status'] == 'degraded'
    print('PASS: healthy target and measured latency above SLO', flush=True)
    try:
        compose('stop', 'portal-lab')
        wait_until(lambda: labs()['Laboratório · Portal HTTP']['status'] == 'down', 'real HTTP failure detected')
    finally:
        compose('start', 'portal-lab')
    wait_until(lambda: labs()['Laboratório · Portal HTTP']['status'] == 'healthy', 'HTTP recovery detected')
    try:
        compose('stop', 'prometheus')
        wait_until(lambda: api('telemetry')['status'] == 'unavailable', 'collector failure visible')
        wait_until(lambda: all(s['status'] == 'unknown' for s in labs().values()), 'stale samples cannot report healthy', timeout=65)
    finally:
        compose('start', 'prometheus')
    wait_until(lambda: api('telemetry')['status'] == 'connected' and labs()['Laboratório · Portal HTTP']['status'] == 'healthy', 'collection restored')
    print(json.dumps({'status': 'passed', 'telemetry': api('telemetry'),
                      'targets': [{'name': s['name'], 'status': s['status'],
                                   'latency_ms': s['latest']['latency_ms'],
                                   'sample_count': s['sample_count']} for s in labs().values()]}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
