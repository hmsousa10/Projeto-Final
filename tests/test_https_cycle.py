from copy import deepcopy
import pytest
from scripts.https_cycle import approved_api


def target():
    return {'Id':'owned-fixture-id','State':{'Running':True},'Config':{'Cmd':['python','-m','app.customer_fixture'],
        'Labels':{'com.docker.compose.project':'nexo-preproduction','com.docker.compose.service':'enterprise-api'},
        'Env':['ENTERPRISE_COMPANY_ID=aurora','FIXTURE_TLS_KEY_FILE=/run/secrets/enterprise_private']},
        'NetworkSettings':{'Ports':{'8080/tcp':None}}}


def test_target_guard_accepts_only_expected_running_private_tls_fixture():
    assert approved_api(target())=='owned-fixture-id'


@pytest.mark.parametrize('changed',['project','service','public_port','identity','stopped','command'])
def test_target_guard_refuses_other_installations_before_docker_stop(changed):
    value=target()
    if changed=='project':value['Config']['Labels']['com.docker.compose.project']='nexo-lab'
    if changed=='service':value['Config']['Labels']['com.docker.compose.service']='nexo'
    if changed=='public_port':value['NetworkSettings']['Ports']['8080/tcp']=[{'HostPort':'8002'}]
    if changed=='identity':value['Config']['Env']=[]
    if changed=='stopped':value['State']['Running']=False
    if changed=='command':value['Config']['Cmd']=['python','-m','unrelated_service']
    with pytest.raises(ValueError):approved_api(value)
