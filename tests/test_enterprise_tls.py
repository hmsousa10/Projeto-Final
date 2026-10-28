import json
import ssl
import threading

from cryptography import x509
from cryptography.hazmat.primitives import serialization
import pytest

from app.customer_fixture import APIOnly, FixtureServer, tls_context
from app.enterprise import EnterpriseClient
from scripts.fixture_tls import prepare_bundle
from tests.test_enterprise import TOKEN


@pytest.fixture
def secured_api(tmp_path):
    directory=prepare_bundle(tmp_path/'tls','localhost',True)
    calls=[]

    class Recording(APIOnly):
        def do_GET(self):
            calls.append(self.headers.get('Authorization'))
            super().do_GET()

    with FixtureServer(('127.0.0.1',0),Recording) as server:
        server.company_id,server.company_name,server.enterprise_token='aurora','Aurora · TLS de ensaio',TOKEN
        server.tls_context=tls_context(directory/'server.crt',directory/'server.key')
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            yield directory,f'https://localhost:{server.server_port}/api/operations/summary',calls
        finally:
            server.shutdown();worker.join(timeout=3)


def test_real_tls_authentication_with_scoped_ca_and_system_trust_unchanged(secured_api):
    directory,url,calls=secured_api
    ca=x509.load_pem_x509_certificate((directory/'ca.crt').read_bytes()).public_bytes(serialization.Encoding.DER)
    assert ca not in ssl.create_default_context().get_ca_certs(binary_form=True)
    client=EnterpriseClient(url,TOKEN,ca_file=str(directory/'ca.crt'))
    assert client.ssl_context.check_hostname and client.ssl_context.verify_mode==ssl.CERT_REQUIRED
    result=client.fetch()
    assert result['status']=='connected' and result['summary']['environment']=='laboratory'
    assert result['summary']['orders']['total']==3 and calls==['Bearer '+TOKEN]
    assert ca in client.ssl_context.get_ca_certs(binary_form=True)
    assert ca not in ssl.create_default_context().get_ca_certs(binary_form=True)
    assert TOKEN not in json.dumps(result) and url not in json.dumps(result)


@pytest.mark.parametrize('failure',['missing_ca','other_ca','wrong_hostname'])
def test_tls_verification_failure_sends_no_http_credentials(secured_api,tmp_path,failure):
    directory,url,calls=secured_api
    ca=str(directory/'ca.crt')
    if failure=='missing_ca':
        ca=''
    if failure=='other_ca':
        other=prepare_bundle(tmp_path/'other','localhost',True)
        ca=str(other/'ca.crt')
    if failure=='wrong_hostname':
        url=url.replace('localhost','127.0.0.1')
    result=EnterpriseClient(url,TOKEN,ca_file=ca).fetch()
    assert result['status']=='unavailable' and 'summary' not in result
    assert calls==[] and TOKEN not in json.dumps(result)


def test_valid_tls_does_not_replace_bearer_authentication(secured_api):
    directory,url,calls=secured_api
    result=EnterpriseClient(url,'wrong-read-token-only-for-tests-123456',ca_file=str(directory/'ca.crt')).fetch()
    assert result['status']=='unauthorized' and 'summary' not in result
    assert len(calls)==1


@pytest.mark.parametrize('mode',['disabled','http','invalid_ca'])
def test_ca_configuration_fails_closed(tmp_path,monkeypatch,mode):
    key=tmp_path/'read.key';key.write_text(TOKEN)
    ca=tmp_path/'ca.crt';ca.write_text('not-a-certificate')
    monkeypatch.setenv('ENTERPRISE_API_CA_FILE',str(ca))
    monkeypatch.delenv('ENTERPRISE_API_URL',raising=False)
    monkeypatch.delenv('ENTERPRISE_API_TOKEN_FILE',raising=False)
    if mode!='disabled':
        monkeypatch.setenv('ENTERPRISE_API_URL','http://localhost:8080/summary' if mode=='http' else 'https://company.example/summary')
        monkeypatch.setenv('ENTERPRISE_API_TOKEN_FILE',str(key))
    with pytest.raises(RuntimeError) as error:
        EnterpriseClient.configured()
    assert TOKEN not in str(error.value) and 'not-a-certificate' not in str(error.value)


def test_fixture_tls_material_is_preserved_and_missing_keys_not_replaced(tmp_path):
    directory=prepare_bundle(tmp_path/'tls',create=True)
    before={p.name:p.read_bytes() for p in directory.iterdir()}
    prepare_bundle(directory,create=True)
    assert before=={p.name:p.read_bytes() for p in directory.iterdir()}
    assert set(before)=={'ca.crt','server.crt','server.key','read.key'}
    assert b'PRIVATE KEY' not in before['ca.crt'] and b'PRIVATE KEY' not in before['server.crt']
    (directory/'server.key').unlink()  # Disposable fixture only.
    with pytest.raises(ValueError):
        prepare_bundle(directory,create=True)
    assert not (directory/'server.key').exists()
