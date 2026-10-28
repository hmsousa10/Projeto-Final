"""Prepare and manage local, isolated customer installation rehearsals."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent.parent


def validate_profile(value, instance):
    if set(value) != {'instance', 'company_id', 'port', 'email'} or value['instance'] != instance:
        raise ValueError('Perfil de instalação incompatível.')
    if not isinstance(value['company_id'], str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,23}', value['company_id']):
        raise ValueError('Identidade de ensaio inválida.')
    if type(value['port']) is not int or not 8003 <= value['port'] <= 8999:
        raise ValueError('A porta de ensaio deve estar entre 8003 e 8999.')
    if value['email'] != 'admin@' + value['company_id'] + '.test':
        raise ValueError('Conta inicial de ensaio inválida.')
    return value


def prepare(root, instance, port=None, create=False):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,23}', instance):
        raise ValueError('Usa um identificador com letras minúsculas, números e hífen; máximo 24 caracteres.')
    base = (root / 'data' / 'installations').resolve()
    directory = (base / instance).resolve()
    if directory.parent != base:
        raise ValueError('A instalação deve ficar dentro da pasta de ensaios.')
    profile_path = directory / 'profile.json'
    secret_names = ('initial-admin.key', 'enterprise-read.key')
    if directory.exists():
        if not profile_path.is_file():
            raise ValueError('Preparação incompleta; preserva os ficheiros existentes e verifica a pasta do ensaio.')
        profile = validate_profile(json.loads(profile_path.read_text(encoding='utf-8')), instance)
        if port is not None and profile['port'] != port:
            raise ValueError('Esta instalação já tem outra porta; usa a configuração existente.')
        if any(not (directory / name).is_file() or (directory / name).is_symlink() for name in secret_names):
            raise ValueError('Falta um segredo local da instalação. Recupera o original; não será recriado.')
    elif create:
        profile = validate_profile({'instance': instance, 'company_id': instance,
                                    'port': port if port is not None else 8003,
                                    'email': 'admin@' + instance + '.test'}, instance)
        for other in base.glob('*/profile.json'):
            if json.loads(other.read_text(encoding='utf-8')).get('port') == profile['port']:
                raise ValueError('A porta já pertence a outro ensaio; escolhe uma porta diferente.')
        directory.mkdir(parents=True, mode=0o700)
        for name in secret_names:
            with (directory / name).open('x', encoding='utf-8') as target:
                if os.name != 'nt':
                    os.chmod(target.name, 0o600)
                target.write(secrets.token_urlsafe(36))
        with profile_path.open('x', encoding='utf-8') as target:
            json.dump(profile, target, indent=2)
    else:
        raise ValueError('Instalação não preparada; executa primeiro preparar ou iniciar.')
    return profile, directory


def compose_command(root, profile, directory, action, build=False):
    docker = shutil.which('docker')
    fallback = Path(os.getenv('LOCALAPPDATA', '')) / 'Programs/DockerDesktop/resources/bin/docker.exe'
    if not docker and fallback.is_file():
        docker = str(fallback)
    if not docker:
        raise ValueError('Docker não encontrado. Abre o Docker Desktop e verifica a instalação.')
    environment = os.environ.copy()
    # These values come from validated local profiles, never shell interpolation.
    environment.update(NEXO_TEST_PORT=str(profile['port']), NEXO_TEST_COMPANY=profile['company_id'],
                       NEXO_TEST_EMAIL=profile['email'], NEXO_TEST_SECRET_DIR=directory.as_posix())
    command = [docker, 'compose', '--project-directory', str(root), '-p', 'nexo-test-' + profile['instance'],
               '-f', str(root / 'compose.customer-test.yaml')]
    if build:
        subprocess.run(command + ['build', 'nexo'], env=environment, check=True, timeout=240)
    arguments = {'iniciar': ['up', '-d', '--no-build', '--wait', '--wait-timeout', '60'],
                 'recriar': ['up', '-d', '--no-build', '--force-recreate', '--wait', '--wait-timeout', '60'],
                 'estado': ['ps'], 'parar': ['stop']}[action]
    subprocess.run(command + arguments, env=environment, check=True, timeout=90)


def main():
    parser = argparse.ArgumentParser(description='Instalações locais de ensaio, com dados e credenciais independentes.')
    parser.add_argument('action', choices=['preparar', 'iniciar', 'recriar', 'estado', 'parar'])
    parser.add_argument('--instancia', default='atlas')
    parser.add_argument('--porta', type=int)
    parser.add_argument('--build', action='store_true', help='Construir a imagem antes de iniciar.')
    args = parser.parse_args()
    try:
        if args.build and args.action != 'iniciar':
            raise ValueError('--build só pode ser usado com iniciar.')
        profile, directory = prepare(ROOT, args.instancia, args.porta, args.action in ('preparar', 'iniciar'))
        if args.action != 'preparar':
            compose_command(ROOT, profile, directory, args.action, args.build)
        print('Ensaio:', profile['instance'], '| Portal: http://localhost:' + str(profile['port']))
        print('Conta inicial:', profile['email'])
        print('Palavra-passe inicial no ficheiro local:', directory / 'initial-admin.key')
        print('Os valores dos segredos não são apresentados. Parar preserva os volumes e o histórico.')
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        # Do not echo subprocess environment or secret file contents.
        if isinstance(error, ValueError):
            parser.exit(1, str(error) + '\n')
        parser.exit(1, 'Não foi possível concluir o ensaio. Verifica o Docker e os ficheiros locais; os dados foram preservados.\n')


if __name__ == '__main__':
    main()
