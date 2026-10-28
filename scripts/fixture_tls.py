"""Local, single-purpose TLS material for the fictitious enterprise API."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import secrets
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

from app.recovery import plain_path
from app.enterprise import read_token


def prepare_bundle(directory, hostname='enterprise-api', create=False):
    directory = plain_path(directory)
    files = {name:plain_path(directory/name) for name in ('ca.crt','server.crt','server.key','read.key')}
    if not directory.exists():
        if not create:
            raise ValueError('Prepara primeiro os ficheiros TLS da API de ensaio.')
        directory.mkdir(parents=True,mode=0o700)
        now = datetime.now(timezone.utc)
        ca_key = ec.generate_private_key(ec.SECP256R1())
        server_key = ec.generate_private_key(ec.SECP256R1())
        issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Nexo enterprise API rehearsal CA')])
        ca = (x509.CertificateBuilder().subject_name(issuer).issuer_name(issuer).public_key(ca_key.public_key())
              .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
              .not_valid_after(now+timedelta(days=365)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True)
              .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,key_encipherment=False,
                             data_encipherment=False,key_agreement=False,key_cert_sign=True,crl_sign=True,
                             encipher_only=False,decipher_only=False),True)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),False)
              .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),False)
              .sign(ca_key,hashes.SHA256()))
        leaf = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,hostname)]))
                .issuer_name(issuer).public_key(server_key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=90))
                .add_extension(x509.BasicConstraints(ca=False,path_length=None),True)
                .add_extension(x509.KeyUsage(True,False,False,False,False,False,False,False,False),True)
                .add_extension(x509.SubjectKeyIdentifier.from_public_key(server_key.public_key()),False)
                .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),False)
                .add_extension(x509.SubjectAlternativeName([x509.DNSName(hostname)]),False)
                .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),False)
                .sign(ca_key,hashes.SHA256()))
        values = {'ca.crt':ca.public_bytes(serialization.Encoding.PEM),
                  'server.crt':leaf.public_bytes(serialization.Encoding.PEM),
                  'server.key':server_key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()),
                  'read.key':secrets.token_urlsafe(36).encode()}
        # CA signing key stays in memory only; renewal needs an explicit new bundle.
        for name,value in values.items():
            with files[name].open('xb') as target:
                if os.name != 'nt':
                    os.chmod(files[name],0o600)
                target.write(value)
    if any(not p.is_file() or p.stat().st_size>16384 for p in files.values()):
        raise ValueError('Ficheiros TLS incompletos ou inválidos; não serão regenerados silenciosamente.')
    ca = x509.load_pem_x509_certificate(files['ca.crt'].read_bytes())
    leaf = x509.load_pem_x509_certificate(files['server.crt'].read_bytes())
    if not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError('A CA do ensaio é inválida.')
    leaf.verify_directly_issued_by(ca)
    if hostname not in leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName):
        raise ValueError('O certificado não identifica a API esperada.')
    now = datetime.now(timezone.utc)
    if not leaf.not_valid_before_utc <= now < leaf.not_valid_after_utc or not ca.not_valid_before_utc <= now < ca.not_valid_after_utc:
        raise ValueError('O certificado de ensaio não está dentro da validade; exige substituição explícita.')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(files['server.crt'],files['server.key'])
    read_token(files['read.key'])
    return directory
