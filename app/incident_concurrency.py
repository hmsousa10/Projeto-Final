"""Check under BEGIN IMMEDIATE so concurrent writers cannot both pass."""
from fastapi import HTTPException


def check_revision(row, expected):
    if expected is not None and row['revision'] != expected:
        raise HTTPException(409,
            'Este incidente foi alterado desde que o abriste. O teu texto continua no formulário. '
            'Consulta a versão atual antes de tentar novamente.',
            headers={'X-Nexo-Conflict': 'incident-revision'})
