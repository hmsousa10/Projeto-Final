"""Deployment-approved HTTP targets. No request can expand the approved catalog."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

LAB_URLS = {'portal-lab': 'http://portal-lab:8080/health', 'api-lab': 'http://api-lab:8080/health'}


def valid_target_url(value):
    if not isinstance(value, str) or len(value) > 2048 or any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
        raise ValueError('Endereço inválido.')
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Usa um endereço HTTP(S) sem credenciais, parâmetros ou fragmentos.')
    parsed.port  # Validate invalid/overflowing ports as well.
    return value


def allowed_urls():
    default = [] if os.getenv('APP_ENV') == 'production' else list(LAB_URLS.values())
    try:
        values = json.loads(os.getenv('MONITORING_ALLOWED_URLS', json.dumps(default)))
        if not isinstance(values, list) or len(values) > 50:
            raise ValueError()
        return frozenset(valid_target_url(value) for value in values)
    except (ValueError, TypeError):
        raise RuntimeError('MONITORING_ALLOWED_URLS exige uma lista JSON de até 50 endereços HTTP(S) explícitos.') from None


def discovery_token():
    token = Path(os.environ['MONITORING_SD_TOKEN_FILE']).read_text(encoding='utf-8').strip()
    if len(token) < 32:
        raise RuntimeError('A descoberta exige uma chave aleatória com pelo menos 32 caracteres.')
    return token


def active_targets(db):
    approved = allowed_urls()
    return {r['target_key']: dict(r) for r in db.execute('SELECT * FROM telemetry_targets WHERE enabled=1')
            if r['target_url'] in approved}


def discovery(db):
    return [{'targets': [row['target_url']], 'labels': {'service_key': key}}
            for key, row in sorted(active_targets(db).items())]
