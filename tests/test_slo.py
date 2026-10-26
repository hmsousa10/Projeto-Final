import math
import time

import pytest

from app import slo, telemetry
from app.db import database, initialize
from tests.test_workflow import client, login

END=1_800_000_000
START=END-60


@pytest.fixture
def path(tmp_path):
    path=tmp_path/'slo.db'
    initialize(path)
    telemetry.initialize_targets(path)
    with database(path) as db:
        slo.record_policy(db,1,'Ensaio',START-10)
        slo.record_policy(db,2,'Ensaio',START-10)
    return path


def insert(path,stamps,available=1,latency=100,source='prometheus'):
    with database(path) as db:
        db.executemany('INSERT INTO observations(service_id,available,latency_ms,source,observed_at) VALUES(1,?,?,?,?)',
                       [(available,latency,source,slo.iso(stamp)) for stamp in stamps])


def first(path,window='1m',clock=END):
    return slo.report(path,window,clock+slo.SETTLEMENT_DELAY)['services'][0]


def test_full_healthy_window_meets_both_objectives(path):
    insert(path,range(START+2,END,10))
    row=first(path)
    assert row['status']=='met'
    assert row['observed_slots']==row['expected_slots']==6
    assert row['eligible_coverage_percent']==row['data_coverage_percent']==100
    assert row['availability']['lower_percent']==row['availability']['upper_percent']==100
    assert row['latency']['good_slots']==6 and row['p95_successful_ms']==100


def test_missing_slots_are_unknown_and_cannot_fake_full_availability(path):
    insert(path,range(START+2,END-10,10))
    row=first(path)
    assert row['status']=='insufficient_data'
    assert row['availability']['observed_percent']==100
    assert row['unknown_slots']==1
    assert row['availability']['lower_percent']==pytest.approx(5/6*100)
    assert row['availability']['upper_percent']==100
    budget=row['availability']['error_budget']
    assert budget['remaining_min_slots']<0<budget['remaining_max_slots']
    assert slo.metric(0,0,6,1e-12,True)['status']=='insufficient_data'
    assert slo.metric(29,100,100,29,True)['status']=='met'


def test_duplicates_do_not_increase_coverage_and_worst_probe_wins(path):
    insert(path,range(START+2,END,10))
    insert(path,[START+3],available=0,latency=1)
    row=first(path)
    assert row['raw_samples']==7 and row['observed_slots']==6
    assert row['availability']['bad_slots']==row['latency']['bad_slots']==1
    assert row['status']=='breached'
    assert row['p95_successful_slots']==5


def test_successful_but_slow_probe_breaches_latency_without_failing_availability(path):
    insert(path,range(START+2,END,10),latency=800)
    row=first(path)
    assert row['availability']['status']=='met'
    assert row['latency']['status']=='breached'
    assert row['p95_successful_ms']==800 and row['status']=='breached'


def test_known_failures_can_prove_breach_even_with_unknown_slots(path):
    insert(path,[START+2],available=0,latency=1)
    row=first(path)
    assert row['unknown_slots']==5
    assert row['availability']['upper_percent']<row['availability']['target_percent']
    assert row['availability']['status']=='breached'
    assert row['p95_successful_ms'] is None


def test_no_samples_does_not_mean_outage_or_success(path):
    row=first(path)
    assert row['status']=='insufficient_data'
    assert row['availability']['observed_percent'] is None
    assert row['availability']['bad_slots']==0
    assert row['availability']['lower_percent']==0 and row['availability']['upper_percent']==100


def test_synthetic_invalid_and_unfinished_interval_samples_are_excluded(path):
    insert(path,range(START+2,END,10),source='demo')
    insert(path,[START-1,END,END+2])
    insert(path,[START+2],latency=math.inf)
    insert(path,[START+12],latency=-1)
    row=first(path,clock=END+9)
    assert slo.report(path,'1m',END+slo.SETTLEMENT_DELAY+9)['end']==slo.iso(END)
    assert row['raw_samples']==row['observed_slots']==0
    assert row['status']=='insufficient_data'


def test_objective_change_preserves_data_but_requires_consistent_policy_window(path):
    insert(path,range(START+2,END,10))
    with database(path) as db:
        db.execute('UPDATE services SET slo_latency_percent=98 WHERE id=1')
        updated=slo.record_policy(db,1,'Administrador',START+30)
    row=first(path)
    assert updated['version']==2
    assert row['status']=='policy_partial'
    assert row['data_coverage_percent']==100 and row['eligible_coverage_percent']==50
    assert row['excluded_before_policy_slots']==3
    with database(path) as db:
        assert db.execute('SELECT count(*) FROM observations WHERE service_id=1').fetchone()[0]==6
        assert db.execute('SELECT count(*) FROM service_slo_policies WHERE service_id=1').fetchone()[0]==2


def test_policy_boundary_slot_must_be_fully_covered(path):
    insert(path,range(START+2,END,10))
    with database(path) as db:
        db.execute('UPDATE services SET slo_availability=99 WHERE id=1')
        slo.record_policy(db,1,'Administrador',START+1)
    row=first(path)
    assert row['observed_slots']==5 and not row['policy_covers_window']
    assert row['status']=='policy_partial'


def test_policy_initialization_is_idempotent_and_does_not_invent_history(tmp_path):
    path=tmp_path/'new.db'
    initialize(path)
    telemetry.initialize_targets(path)
    before=time.time()
    slo.initialize_policies(path)
    slo.initialize_policies(path)
    with database(path) as db:
        rows=db.execute('SELECT * FROM service_slo_policies').fetchall()
        assert len(rows)==2
        assert all(slo.datetime.fromisoformat(r['valid_from']).timestamp()>=before for r in rows)


def test_seven_day_response_is_aggregated_and_bounded(path):
    report=slo.report(path,'7d',END)
    assert report['expected_slots_per_service']==60480
    assert all(len(s['timeline'])==60 for s in report['services'])


def test_slo_api_auth_window_validation_and_policy_versioning(client):
    assert client.get('/api/slo').status_code==401
    login(client)
    telemetry.initialize_targets(client.app.state.db_path)
    slo.initialize_policies(client.app.state.db_path)
    report=client.get('/api/slo?window=1m')
    assert report.status_code==200
    assert all(s['status']=='policy_partial' for s in report.json()['services'])
    assert client.get('/api/slo?window=30d').status_code==422
    service=client.get('/api/services').json()[0]
    body={key:service[key] for key in ('name','team','description','criticality','slo_availability','slo_latency_ms','slo_latency_percent','dependencies')}
    body['slo_latency_percent']=98.5
    assert client.put('/api/services/1',json=body).status_code==200
    history=client.get('/api/services/1/slo/history').json()
    assert history[0]['version']==2 and history[0]['latency_percent']==98.5
    assert client.put('/api/services/1',json=body).status_code==200
    assert len(client.get('/api/services/1/slo/history').json())==2
    assert client.put('/api/services/1',json={**body,'slo_latency_percent':101}).status_code==422
    login(client,'leitor@local.test')
    assert client.get('/api/slo').status_code==200
    assert client.get('/api/services/1/slo/history').status_code==200
    assert client.put('/api/services/1',json=body).status_code==403
