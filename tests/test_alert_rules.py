from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import time

import pytest

from app import alerts, telemetry
from app.db import database, initialize
from app.models import AlertRuleInput
from tests.test_workflow import client, login


def settings(db,sid,stamp='',**updates):
    config=AlertRuleInput(**updates).model_dump()
    db.execute('INSERT OR REPLACE INTO alert_rules VALUES(?,?,?,1)',(sid,json.dumps(config),stamp))
    return config


def sample(stamps,success='1',duration='0.8'):
    return [{'metric':{'service_key':'portal-lab','__name__':name},'values':[[stamp,value] for stamp in stamps]}
            for name,value in [('probe_success',success),('probe_duration_seconds',duration)]]


@pytest.fixture
def path(tmp_path):
    path=tmp_path/'rules.db'
    initialize(path)
    telemetry.initialize_targets(path)
    return path


def test_configurable_samples_threshold_priority_and_detection_context(path):
    stamp=time.time()
    with database(path) as db:
        settings(db,1,failure_samples=3,recovery_samples=3,latency_ms=700,latency_severity='P3')
    telemetry.import_samples(path,sample([stamp-20,stamp-10]),stamp)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incidents').fetchone()[0]==0
    telemetry.import_samples(path,sample([stamp]),stamp)
    with database(path) as db:
        incident=db.execute('SELECT * FROM incidents').fetchone()
        assert incident['severity']=='P3'
        context=json.loads(db.execute('SELECT config FROM incident_alert_context').fetchone()[0])
        assert context['failure_samples']==3 and context['effective_latency_ms']==700
    telemetry.import_samples(path,sample([stamp+10,stamp+20],duration='0.1'),stamp+20)
    with database(path) as db:
        assert not alerts.recovered(db,1,stamp+20)
    telemetry.import_samples(path,sample([stamp+30],duration='0.1'),stamp+30)
    with database(path) as db:
        assert alerts.recovered(db,1,stamp+30)
    telemetry.import_samples(path,sample([stamp+40],success='0'),stamp+40)
    with database(path) as db:
        assert not alerts.recovered(db,1,stamp+40)


def test_five_probes_can_confirm_with_collector_delay(path):
    stamp=time.time()
    with database(path) as db:
        settings(db,1,failure_samples=5)
    telemetry.import_samples(path,sample([stamp-i*10 for i in range(5)],success='0'),stamp+9)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incidents').fetchone()[0]==1


def test_muting_does_not_create_or_close_incidents_and_reenable_uses_new_data(path):
    stamp=time.time()
    with database(path) as db:
        settings(db,1,latency_enabled=False)
    telemetry.import_samples(path,sample([stamp-10,stamp]),stamp)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incidents').fetchone()[0]==0
        settings(db,1,stamp=datetime.fromtimestamp(stamp+1,timezone.utc).isoformat())
    telemetry.import_samples(path,sample([stamp-10,stamp]),stamp+1)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incidents').fetchone()[0]==0
    telemetry.import_samples(path,sample([stamp+10,stamp+20]),stamp+20)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incidents').fetchone()[0]==1
        settings(db,1,enabled=False)
    telemetry.import_samples(path,sample([stamp+30,stamp+40],success='0'),stamp+40)
    with database(path) as db:
        assert db.execute('SELECT severity FROM incidents').fetchone()[0]=='P2'
        assert db.execute('SELECT status FROM incidents').fetchone()[0]=='open'


def overdue_case(path,**policy):
    stamp=time.time()
    with database(path) as db:
        settings(db,1,escalation_enabled=True,acknowledge_seconds=15,**policy)
        created=datetime.fromtimestamp(stamp-30,timezone.utc).isoformat()
        iid=db.execute("INSERT INTO incidents(service_id,title,description,severity,status,created_at,source) VALUES(1,'Test','Test','P3','open',?,'prometheus-alert')",(created,)).lastrowid
    return iid,stamp


def test_time_escalation_is_once_even_with_concurrent_workers_and_restart(path):
    iid,stamp=overdue_case(path)
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _:alerts.tick(path,stamp),range(3)))
    initialize(path)
    alerts.tick(path,stamp+10)
    with database(path) as db:
        assert db.execute('SELECT severity FROM incidents WHERE id=?',(iid,)).fetchone()[0]=='P1'
        assert db.execute('SELECT count(*) FROM incident_escalations').fetchone()[0]==1
        assert db.execute("SELECT count(*) FROM timeline WHERE action='Escalonamento por falta de reconhecimento'").fetchone()[0]==1


@pytest.mark.parametrize('reason',['acknowledged','paused','muted','disabled_timer','manual'])
def test_time_escalation_ignores_ineligible_cases(path,reason):
    iid,stamp=overdue_case(path)
    with database(path) as db:
        if reason=='acknowledged':
            db.execute("UPDATE incidents SET status='acknowledged',acknowledged_at=? WHERE id=?",(datetime.now(timezone.utc).isoformat(),iid))
        elif reason=='paused':
            db.execute('UPDATE telemetry_targets SET enabled=0 WHERE service_id=1')
        elif reason=='muted':
            settings(db,1,enabled=False,escalation_enabled=True,acknowledge_seconds=15)
        elif reason=='disabled_timer':
            settings(db,1)
        else:
            db.execute("UPDATE incidents SET source='manual'")
    alerts.tick(path,stamp)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incident_escalations').fetchone()[0]==0
        assert db.execute('SELECT severity FROM incidents').fetchone()[0]=='P3'


def test_rule_update_and_monitoring_resume_grant_a_new_deadline(path):
    iid,_=overdue_case(path)
    stamp=1_800_000_000.1234567
    epoch=datetime.fromtimestamp(stamp,timezone.utc).isoformat()
    with database(path) as db:
        db.execute('UPDATE incidents SET created_at=? WHERE id=?',(datetime.fromtimestamp(stamp-30,timezone.utc).isoformat(),iid))
        settings(db,1,stamp=epoch,escalation_enabled=True,acknowledge_seconds=15)
    alerts.tick(path,stamp+14)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incident_escalations').fetchone()[0]==0
        db.execute('UPDATE telemetry_targets SET updated_at=? WHERE service_id=1',(datetime.fromtimestamp(stamp+10,timezone.utc).isoformat(),))
    alerts.tick(path,stamp+24)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incident_escalations').fetchone()[0]==0
    alerts.tick(path,stamp+25)
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM incident_escalations').fetchone()[0]==1


def test_p1_overdue_is_recorded_without_false_priority_change(path):
    iid,stamp=overdue_case(path)
    with database(path) as db:
        db.execute("UPDATE incidents SET severity='P1'")
    alerts.tick(path,stamp)
    with database(path) as db:
        assert db.execute("SELECT count(*) FROM timeline WHERE action='Prazo de reconhecimento ultrapassado'").fetchone()[0]==1
        row=db.execute('SELECT * FROM incident_escalations').fetchone()
        assert row['from_severity']==row['to_severity']=='P1'


def test_rule_api_permissions_versions_and_input_bounds(client):
    login(client)
    old=next(r for r in client.get('/api/alert-rules').json() if r['service_id']==1)
    assert old['version']==0 and not old['config']['escalation_enabled']
    body={**old['config'],'failure_samples':3,'latency_severity':'P3','escalation_enabled':True,'acknowledge_seconds':60}
    response=client.put('/api/services/1/alert-rule',json=body)
    assert response.status_code==200 and response.json()['version']==1
    assert client.put('/api/services/1/alert-rule',json=body).json()['version']==1
    assert len(client.get('/api/services/1/alert-rule/history').json())==1
    for values in ({'failure_samples':1},{'recovery_samples':6},{'acknowledge_seconds':14},{'latency_ms':0},{'outage_severity':'P4'},{'unknown':1}):
        assert client.put('/api/services/1/alert-rule',json={**body,**values}).status_code==422
    assert client.put('/api/services/99999/alert-rule',json=body).status_code==404
    login(client,'operacoes@local.test')
    assert client.get('/api/alert-rules').status_code==200
    assert client.get('/api/alert-engine').status_code==200
    assert client.put('/api/services/1/alert-rule',json=body).status_code==403
    assert client.get('/api/services/1/alert-rule/history').status_code==403
