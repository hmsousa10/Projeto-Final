"""Fictitious company portal: actual HTTP faults, bounded to two minutes."""
import json
import os
from pathlib import Path
import queue
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler

from .telemetry import NoRedirect, validate_url

WEB = Path(__file__).resolve().parent.parent / 'web' / 'company'
LOGS = queue.Queue(maxsize=500)
LOCK = threading.Lock()
STATE = {'kind': 'recovery', 'expires_at': 0}


def condition():
    with LOCK:
        if STATE['expires_at'] <= time.time():
            return 'recovery'
        return STATE['kind']


def log_worker(url):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    target = os.getenv('LAB_TARGET_KEY', 'portal-lab')
    while True:
        stamp, line = LOGS.get()
        payload = {'streams': [{'stream': {'app': 'nexo-lab', 'service_key': target},
                                'values': [[stamp, line]]}]}
        try:
            req = Request(url + '/loki/api/v1/push', data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'})
            with opener.open(req, timeout=2) as response:
                response.read(1024)
        except Exception:
            pass  # Best-effort laboratory logs must not block the business request.
        finally:
            LOGS.task_done()


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *args):
        pass

    def respond(self, status, body, content_type='application/json'):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        started = time.monotonic()
        path = self.path.split('?', 1)[0]
        routes = {'/': ('index.html', 'text/html'), '/company.css': ('company.css', 'text/css'),
                  '/company.js': ('company.js', 'text/javascript')}
        status = 200
        if path in routes:
            filename, content_type = routes[path]
            self.respond(200, (WEB / filename).read_bytes(), content_type)
        elif path in ('/health', '/api/orders'):
            fault = condition()
            delay = 1.2 if fault == 'latency' else float(os.getenv('LAB_DELAY_SECONDS', '0'))
            time.sleep(delay)
            status = 503 if fault == 'outage' else 200
            if status == 503:
                body = {'status': 'unavailable', 'message': 'O serviço de pedidos está temporariamente indisponível.'}
            elif path == '/health':
                body = {'status': 'ok', 'environment': 'laboratory'}
            else:
                body = {'orders': [{'id': 'PED-1042', 'item': 'Kit de escritório', 'state': 'Em preparação'},
                                   {'id': 'PED-1041', 'item': 'Monitor profissional', 'state': 'Expedido'},
                                   {'id': 'PED-1040', 'item': 'Cadeira ergonómica', 'state': 'Entregue'}]}
            self.respond(status, body)
        else:
            status = 404
            self.respond(status, {'message': 'Página não encontrada.'})
        if path in (*routes, '/health', '/api/orders'):
            line = json.dumps({'method': 'GET', 'path': path, 'status': status,
                               'duration_ms': round((time.monotonic() - started) * 1000, 2)}, ensure_ascii=False)
            try:
                LOGS.put_nowait((str(time.time_ns()), line))
            except queue.Full:
                pass

    def do_POST(self):
        token = getattr(self.server, 'control_token', '')
        if self.path != '/_control' or not token:
            self.respond(404, {'message': 'Não encontrado.'})
            return
        if not secrets.compare_digest(self.headers.get('Authorization', '').encode(), ('Bearer ' + token).encode()):
            self.respond(403, {'message': 'Controlo não autorizado.'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1024 or self.headers.get('Transfer-Encoding'):
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            kind = data['kind']
            if set(data) != {'kind'} or kind not in ('outage', 'latency', 'recovery'):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            self.respond(400, {'message': 'Cenário inválido.'})
            return
        with LOCK:
            STATE.update(kind=kind, expires_at=time.time() + 120 if kind != 'recovery' else 0)
            result = dict(STATE)
        self.respond(200, result)


if __name__ == '__main__':
    server = ThreadingHTTPServer(('0.0.0.0', 8080), Handler)
    if os.getenv('LAB_MODE') == '1':
        from .lab import control_token
        server.control_token = control_token()
    if os.getenv('LOKI_URL'):
        threading.Thread(target=log_worker, args=(validate_url(os.environ['LOKI_URL']),), daemon=True).start()
    server.serve_forever()
