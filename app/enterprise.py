"""Deployment-configured, read-only business API adapter. No browser-supplied URLs."""
import json
import os
import re
import ssl
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from fastapi import Depends

from .db import now
from .connectors import StalePayload, get_connector
from .monitoring import valid_target_url
from .telemetry import NoRedirect


def read_token(filename):
    token = Path(filename).read_text(encoding='utf-8').strip()
    if not re.fullmatch(r'[A-Za-z0-9_+=/.-]{32,512}', token):
        raise RuntimeError('A integração empresarial exige uma chave de leitura válida num ficheiro separado.')
    return token


class EnterpriseClient:
    def __init__(self, url='', token='', company_id='aurora', connector_id='orders-summary-v1', ca_file=''):
        self.connector = get_connector(connector_id)
        self.url, self.token, self.company_id = url, token, company_id
        if ca_file and urlsplit(url).scheme != 'https':
            raise ValueError('Uma CA empresarial só pode ser usada com HTTPS.')
        self.ssl_context = ssl.create_default_context() if urlsplit(url).scheme == 'https' else None
        if ca_file:
            # Trust is scoped to this client; retain system roots and hostname checks.
            self.ssl_context.load_verify_locations(cafile=ca_file)
        self.lock = threading.Lock()
        self.cached, self.cached_at = None, 0

    @classmethod
    def configured(cls):
        connector_id = os.getenv('ENTERPRISE_CONNECTOR', 'orders-summary-v1')
        get_connector(connector_id)  # Fail closed even when the API is disabled.
        url, filename = os.getenv('ENTERPRISE_API_URL', ''), os.getenv('ENTERPRISE_API_TOKEN_FILE', '')
        ca_file = os.getenv('ENTERPRISE_API_CA_FILE', '')
        if not url and not filename:
            if ca_file:
                raise RuntimeError('A CA empresarial exige uma API e uma chave de leitura configuradas.')
            return cls(connector_id=connector_id)
        if not url or not filename:
            raise RuntimeError('Configura ENTERPRISE_API_URL e ENTERPRISE_API_TOKEN_FILE em conjunto.')
        try:
            valid_target_url(url)
            parsed = urlsplit(url)
            if parsed.scheme != 'https' and (os.getenv('APP_ENV') == 'production' or parsed.hostname not in ('portal-lab', 'localhost', '127.0.0.1')):
                raise ValueError()
            company_id = os.getenv('ENTERPRISE_COMPANY_ID', 'aurora')
            if not re.fullmatch(r'[a-z0-9-]{1,40}', company_id):
                raise ValueError()
            token = read_token(filename)
            client = cls(url, token, company_id, connector_id, ca_file)
        except (OSError, ValueError):
            raise RuntimeError('Configuração da API empresarial inválida; usa HTTPS ou o laboratório local explícito.') from None
        return client

    def fetch(self):
        if not self.url:
            return {'configured': False, 'status': 'not_configured', 'checked_at': now()}
        if not self.lock.acquire(timeout=.1):
            return {'configured': True, 'status': 'busy', 'checked_at': now()}
        try:
            if self.cached is not None and time.monotonic() - self.cached_at < 5:
                return self.cached
            result = {'configured': True, 'adapter': self.connector.id,
                      'connector': {'id': self.connector.id, 'label': self.connector.label,
                                    'summary_kind': self.connector.summary_kind}, 'checked_at': now(),
                      'cache_seconds': 5, 'status': 'unavailable'}
            started = time.monotonic()
            try:
                request = Request(self.url, headers={'Accept': 'application/json', 'Authorization': 'Bearer ' + self.token})
                with build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=self.ssl_context)).open(request, timeout=3) as response:
                    if response.status != 200 or response.headers.get_content_type() != 'application/json':
                        raise ValueError()
                    raw = bytearray()
                    while True:
                        if time.monotonic() - started > 3:
                            raise TimeoutError()
                        chunk = response.read1(min(4096, 16 * 1024 + 1 - len(raw)))
                        if not chunk:
                            break
                        raw.extend(chunk)
                        if len(raw) > 16 * 1024:
                            raise ValueError()
                summary = self.connector.normalize(json.loads(raw.decode('utf-8')), self.company_id)
                result.update(status='connected', summary=summary)
            except StalePayload:
                result['status'] = 'stale'
            except HTTPError as error:
                result['status'] = 'unauthorized' if error.code in (401, 403) else 'unavailable'
            except (ValueError, UnicodeError):
                result['status'] = 'invalid_payload'
            except Exception:
                pass  # Never return credentials, upstream bodies or transport exception text.
            result['latency_ms']=round((time.monotonic()-started)*1000,2)
            self.cached, self.cached_at = result, time.monotonic()
            return result
        finally:
            self.lock.release()


def routes(app, client, current_user, monitoring_status=None):
    @app.get('/api/enterprise/summary')
    def summary(user=Depends(current_user)):
        result=dict(client.fetch())
        if monitoring_status is not None:
            result['monitoring']=monitoring_status()
        return result
