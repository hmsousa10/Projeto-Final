"""Local HTTPS rehearsal. Does not install certificates or publish public ports."""
import argparse
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
HOST = 'preprod.localhost'
ORIGIN = 'https://' + HOST + ':8443'


def prepare(root, create=False):
    directory = root / 'data' / 'preproduction'
    # Reuse the path checks used by encrypted recovery, including Windows junctions.
    from app.recovery import plain_path
    directory = plain_path(directory)
    key = plain_path(directory / 'initial-admin.key')
    if not directory.exists():
        if not create:
            raise ValueError('Prepara primeiro o ambiente HTTPS.')
        directory.mkdir(mode=0o700, parents=True)
        with key.open('x', encoding='utf-8') as stream:
            if os.name != 'nt':
                os.chmod(key, 0o600)
            stream.write(secrets.token_urlsafe(36))
    elif not key.is_file():
        raise ValueError('A chave inicial está em falta; não será substituída automaticamente.')
    from scripts.fixture_tls import prepare_bundle
    prepare_bundle(directory / 'enterprise-tls', create=create)
    return directory


def context(root, directory):
    docker = shutil.which('docker')
    fallback = Path(os.getenv('LOCALAPPDATA', '')) / 'Programs/DockerDesktop/resources/bin/docker.exe'
    if not docker and fallback.is_file():
        docker = str(fallback)
    if not docker:
        raise ValueError('Docker não encontrado. Verifica o Docker Desktop.')
    env = os.environ.copy()
    env.update(NEXO_HTTPS_HOST=HOST, NEXO_HTTPS_ORIGIN=ORIGIN, NEXO_HTTPS_SECRET_DIR=directory.as_posix())
    env['NEXO_HTTPS_API_TLS_DIR'] = (directory / 'enterprise-tls').as_posix()
    command = [docker, 'compose', '--project-directory', str(root), '-p', 'nexo-preproduction',
               '-f', str(root / 'compose.preproduction.yaml')]
    return command, env


def export_root(command, env, directory):
    from app.recovery import plain_path
    from cryptography import x509
    destination = plain_path(directory / 'root.crt')
    deadline = time.monotonic() + 20
    while True:
        result = subprocess.run(command + ['exec', '-T', 'proxy', 'cat', '/data/caddy/pki/authorities/local/root.crt'],
                                env=env, capture_output=True, timeout=5)
        if result.returncode == 0:
            break
        if time.monotonic() >= deadline:
            raise ValueError('A autoridade local ainda não está disponível; repete exportar-ca após consultar o estado.')
        time.sleep(1)
    if len(result.stdout) > 8192:
        raise ValueError('Certificado local acima do limite.')
    certificate = x509.load_pem_x509_certificate(result.stdout)
    if not certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError('O ficheiro não é um certificado de autoridade local.')
    if destination.exists():
        if destination.read_bytes() != result.stdout:
            raise ValueError('A autoridade local mudou. Não será substituída silenciosamente na configuração de confiança dos testes.')
    else:
        with destination.open('xb') as stream:
            stream.write(result.stdout)
    return hashlib.sha256(result.stdout).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preparar', 'iniciar', 'estado', 'parar', 'exportar-ca'])
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    try:
        if args.build and args.action != 'iniciar':
            raise ValueError('--build exige iniciar.')
        directory = prepare(ROOT, args.action in ('preparar', 'iniciar'))
        command, env = context(ROOT, directory)
        if args.build:
            subprocess.run(command + ['build'], env=env, check=True, timeout=240)
        if args.action in ('iniciar', 'estado', 'parar'):
            arguments = {'iniciar': ['up', '-d', '--no-build', '--wait', '--wait-timeout', '60'],
                         'estado': ['ps'], 'parar': ['stop']}[args.action]
            subprocess.run(command + arguments, env=env, check=True, timeout=90)
        if args.action in ('iniciar', 'exportar-ca'):
            print('SHA-256 da CA pública local:', export_root(command, env, directory))
        print('Ambiente HTTPS local:', ORIGIN)
        print('Conta: admin@preprod.test | Palavra-passe inicial no ficheiro:', directory / 'initial-admin.key')
        print('Nenhum certificado foi instalado no Windows. O ensaio valida TLS com a CA exportada.')
    except (ValueError, OSError, subprocess.SubprocessError):
        parser.exit(1, 'Não foi possível concluir. Verifica Docker, portas 8443/8084, a rede privada e os ficheiros do ensaio. Os dados foram preservados.\n')


if __name__ == '__main__':
    main()
