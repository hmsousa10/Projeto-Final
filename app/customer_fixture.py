"""Private business API fixture for isolated installation tests. No fault controls."""
import os
import re
import ssl
from http.server import ThreadingHTTPServer

from .enterprise import read_token
from .lab_service import Handler


class APIOnly(Handler):
    def do_GET(self):
        if self.path not in ('/health', '/api/operations/summary'):
            self.respond(404, {'message': 'Não encontrado.'})
            return
        super().do_GET()


class FixtureServer(ThreadingHTTPServer):
    tls_context = None

    def finish_request(self, request, client_address):
        if self.tls_context is None:
            return super().finish_request(request, client_address)
        request.settimeout(5)
        # Handshake runs in the request thread with a bounded timeout.
        with self.tls_context.wrap_socket(request, server_side=True) as secured:
            super().finish_request(secured, client_address)

    def handle_error(self, request, client_address):
        pass  # Fixture TLS rejection must not echo request material or exceptions.


def tls_context(certfile, keyfile):
    if not certfile and not keyfile:
        return None
    if not certfile or not keyfile:
        raise RuntimeError('Configura o certificado e a chave TLS do ensaio em conjunto.')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile, keyfile)
    return context


def serve():
    company_id = os.environ['ENTERPRISE_COMPANY_ID']
    if not re.fullmatch(r'[a-z0-9-]{1,40}', company_id):
        raise RuntimeError('Identidade de ensaio inválida.')
    server = FixtureServer(('0.0.0.0', 8080), APIOnly)
    server.tls_context = tls_context(os.getenv('FIXTURE_TLS_CERT_FILE',''), os.getenv('FIXTURE_TLS_KEY_FILE',''))
    server.company_id = company_id
    server.company_name = company_id.capitalize() + ' · Empresa fictícia de ensaio'
    server.enterprise_token = read_token(os.environ['ENTERPRISE_API_TOKEN_FILE'])
    server.serve_forever()


if __name__ == '__main__':
    serve()
