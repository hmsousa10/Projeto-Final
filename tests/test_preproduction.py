from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
import pytest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.main import create_app
from scripts.preproduction import HOST, ORIGIN, prepare, export_root


def ca(common_name):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
                   .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
                   .not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=1),True)
                   .sign(key,hashes.SHA256()))
    return certificate.public_bytes(serialization.Encoding.PEM)


def test_preparation_preserves_secret_and_refuses_silent_replacement(tmp_path):
    directory = prepare(tmp_path, True)
    secret = (directory/'initial-admin.key').read_bytes()
    assert len(secret) >= 32 and prepare(tmp_path) == directory
    assert (directory/'initial-admin.key').read_bytes() == secret
    (directory/'initial-admin.key').unlink()  # Disposable fixture only.
    with pytest.raises(ValueError):
        prepare(tmp_path, True)


def test_public_ca_export_never_replaces_an_existing_trust_anchor(tmp_path, monkeypatch):
    first, second = ca('First disposable CA'), ca('Second disposable CA')
    monkeypatch.setattr('scripts.preproduction.subprocess.run', lambda *a,**k:SimpleNamespace(returncode=0,stdout=first))
    export_root([],{},tmp_path)
    assert (tmp_path/'root.crt').read_bytes() == first
    export_root([],{},tmp_path)
    monkeypatch.setattr('scripts.preproduction.subprocess.run', lambda *a,**k:SimpleNamespace(returncode=0,stdout=second))
    with pytest.raises(ValueError,match='mudou'):
        export_root([],{},tmp_path)
    assert (tmp_path/'root.crt').read_bytes() == first


@pytest.mark.parametrize('peer,expected', [('172.30.250.2',200),('172.30.250.4',400),('127.0.0.1',400)])
def test_only_the_selected_proxy_can_claim_https(tmp_path,monkeypatch,peer,expected):
    monkeypatch.setenv('APP_ENV','production')
    monkeypatch.setenv('APP_ORIGIN',ORIGIN)
    monkeypatch.setenv('ALLOWED_HOSTS',HOST)
    monkeypatch.setenv('INITIAL_ADMIN_PASSWORD','Disposable production bootstrap secret 2026!')
    app = ProxyHeadersMiddleware(create_app(tmp_path/'nexo.db',demo=False),trusted_hosts='172.30.250.2')
    with TestClient(app,base_url='http://'+HOST,client=(peer,4567)) as client:
        response=client.get('/api/config',headers={'X-Forwarded-Proto':'https','X-Forwarded-For':'198.51.100.42'})
        assert response.status_code == expected
        if expected==200:
            assert response.json()['environment']=='production' and response.json()['demo'] is False
