"""Initial administrator secret, read only when an empty database is bootstrapped."""
import os
from pathlib import Path


def initial_password():
    filename = os.getenv('INITIAL_ADMIN_PASSWORD_FILE', '')
    value = os.getenv('INITIAL_ADMIN_PASSWORD', '')
    if filename and value:
        raise RuntimeError('Usa apenas INITIAL_ADMIN_PASSWORD_FILE ou INITIAL_ADMIN_PASSWORD.')
    if filename:
        try:
            return Path(filename).read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            raise RuntimeError('Não foi possível ler a palavra-passe inicial no ficheiro configurado.') from None
    return value
