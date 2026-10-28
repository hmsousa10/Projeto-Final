"""Password-protected key transport. No DPAPI, network, web route or live promotion.

Format 1 has fixed KDF parameters: untrusted input cannot request arbitrary work.
"""
import argparse
import base64
import json
import getpass
import warnings
import secrets
import sqlite3
import sys
from pathlib import Path

from cryptography.exceptions import InvalidTag, UnsupportedAlgorithm
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import recovery

MAGIC=b'NEXOKEY1'
SIZE=84  # 8-byte version, 16-byte salt, 12-byte nonce, 32-byte key + 16-byte tag
AAD=MAGIC+b'|scrypt:N=131072,r=8,p=1|AES-256-GCM'


def phrase_bytes(phrase):
    if not isinstance(phrase,str) or not 20<=len(phrase)<=256 or phrase.isspace() or len(set(phrase))==1 or any(c in phrase for c in '\r\n\0'):
        raise recovery.RecoveryError('Usa uma frase-passe de 20 a 256 caracteres, sem quebras de linha.')
    return phrase.encode('utf-8')


def derive(phrase,salt):
    return Scrypt(salt=salt,length=32,n=2**17,r=8,p=1).derive(phrase_bytes(phrase))


def wrap(key,phrase):
    recovery.check_key(key)
    phrase_bytes(phrase)
    salt=secrets.token_bytes(16)
    nonce=secrets.token_bytes(12)
    ciphertext=AESGCM(derive(phrase,salt)).encrypt(nonce,key,AAD)
    return MAGIC+salt+nonce+ciphertext


def unwrap(blob,phrase):
    if not isinstance(blob,bytes) or len(blob)!=SIZE or not blob.startswith(MAGIC):
        raise recovery.RecoveryError('Formato de chave portátil inválido.')
    try:
        key=AESGCM(derive(phrase,blob[8:24])).decrypt(blob[24:36],blob[36:],AAD)
    except InvalidTag:
        raise recovery.RecoveryError('Frase-passe incorreta ou chave portátil alterada.') from None
    recovery.check_key(key)
    return key


def export(archive,key,phrase,company_id=None):
    phrase_bytes(phrase)
    report=recovery.verify(archive,key,company_id)
    blob=wrap(key,phrase)
    # A matching archive and a decryptable key are required before publication.
    recovery.verify(archive,unwrap(blob,phrase),company_id)
    return blob,report


def read_phrase():
    if not sys.stdin.isatty():
        raise recovery.RecoveryError('Usa um terminal interativo para introduzir a frase-passe.')
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        try:
            return getpass.getpass('Frase-passe do kit (entrada oculta): ')
        except getpass.GetPassWarning:
            raise recovery.RecoveryError('O terminal não suporta entrada oculta.') from None


def read_kit(folder):
    root=recovery.plain_path(folder)
    values=[]
    for name,limit in [('copia.nexobak',recovery.MAX_ARCHIVE),('chave.nexokey',SIZE)]:
        with recovery.plain_path(root/name).open('rb') as handle:
            raw=handle.read(limit+1)
        if len(raw)>limit:
            raise recovery.RecoveryError('Ficheiro do kit acima do limite.')
        values.append(raw)
    return values


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['export','verify','restore'])
    parser.add_argument('--destination')
    parser.add_argument('--company',help='Expected installation identity for customer recovery.')
    parser.add_argument('--kit',help='Pasta com copia.nexobak e chave.nexokey; pede a frase em entrada oculta.')
    args=parser.parse_args()
    try:
        if args.kit:
            if args.action=='export':
                raise recovery.RecoveryError('A exportação da chave DPAPI usa o script Windows.')
            archive,blob=read_kit(args.kit)
            phrase=read_phrase()
        else:
            raw=sys.stdin.buffer.read(recovery.MAX_INPUT+1)
            if len(raw)>recovery.MAX_INPUT:
                raise recovery.RecoveryError('Entrada acima do limite.')
            payload=json.loads(raw)
            phrase=base64.b64decode(payload['passphrase_b64'],validate=True).decode('utf-8')
            archive=base64.b64decode(payload['archive'],validate=True)
        if args.action=='export':
            key=base64.b64decode(payload['key'],validate=True)
            blob,report=export(archive,key,phrase,args.company)
            result={'wrapped_key':base64.b64encode(blob).decode(),'report':report}
        else:
            if not args.kit:
                blob=base64.b64decode(payload['wrapped_key'],validate=True)
            key=unwrap(blob,phrase)
            if args.action=='restore':
                if not args.destination:
                    raise recovery.RecoveryError('Falta o destino novo.')
                result=recovery.restore(archive,key,args.destination,args.company)
            else:
                result=recovery.verify(archive,key,args.company)
        print(json.dumps(result,ensure_ascii=True))
    except (recovery.RecoveryError,OSError,sqlite3.Error,ValueError,KeyError,TypeError,UnsupportedAlgorithm):
        print('Operação recusada. Confirma a frase-passe, o par de ficheiros, os limites e um destino novo compatível.',file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':main()
