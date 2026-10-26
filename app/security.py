import hashlib
import hmac
import secrets
import threading
from functools import wraps
from fastapi import HTTPException

PASSWORD_SLOTS = threading.BoundedSemaphore(2)


def password_capacity(function):
    """Bound expensive password work per process; do not queue unbounded hashes."""
    @wraps(function)
    def guarded(*args,**kwargs):
        if not PASSWORD_SLOTS.acquire(blocking=False):
            raise HTTPException(429,'Autenticação ocupada. Tenta novamente dentro de instantes.',headers={'Retry-After':'2'})
        try:
            return function(*args,**kwargs)
        finally:
            PASSWORD_SLOTS.release()
    return guarded


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000).hex()
    return f'{salt}${digest}'


def check_password(password, stored):
    salt, expected = stored.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600_000).hex()
    return hmac.compare_digest(actual, expected)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()
