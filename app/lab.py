"""Fault controls exist only in the local laboratory and use a deployment secret."""
import json
import os
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler

from .telemetry import NoRedirect, TARGETS


def control_token():
    token = Path(os.environ['LAB_CONTROL_TOKEN_FILE']).read_text(encoding='utf-8').strip()
    if len(token) < 32:
        raise RuntimeError('O laboratório exige uma chave de controlo aleatória com pelo menos 32 caracteres.')
    return token


def set_fault(target, kind):
    if target not in TARGETS or kind not in ('outage', 'latency', 'recovery'):
        raise ValueError('Cenário inválido')
    req = Request(f'http://{target}:8080/_control',
                  data=json.dumps({'kind': kind}).encode(),
                  headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + control_token()})
    with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=5) as response:
        payload = json.loads(response.read(4096))
    return {'kind': payload['kind'], 'expires_at': payload['expires_at']}
