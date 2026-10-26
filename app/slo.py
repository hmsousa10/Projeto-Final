"""Windowed probe SLIs with explicit unknown slots and versioned objectives."""
from datetime import datetime, timezone
from decimal import Decimal
import math
import time
import threading

from .db import database, now
from .monitoring import allowed_urls

INTERVAL = 10
SETTLEMENT_DELAY = 30
WINDOWS = {'1m':60, '15m':900, '1h':3600, '24h':86400, '7d':604800}


def iso(stamp):
    return datetime.fromtimestamp(stamp,timezone.utc).isoformat()


def record_policy(db, service_id, actor, stamp=None):
    service=db.execute('SELECT * FROM services WHERE id=?',(service_id,)).fetchone()
    latest=db.execute('SELECT * FROM service_slo_policies WHERE service_id=? ORDER BY version DESC LIMIT 1',(service_id,)).fetchone()
    values=(service['slo_availability'],service['slo_latency_ms'],service['slo_latency_percent'])
    if latest and values==(latest['availability_percent'],latest['latency_ms'],latest['latency_percent']):
        return dict(latest)
    version=latest['version']+1 if latest else 1
    db.execute('INSERT INTO service_slo_policies VALUES(?,?,?,?,?,?,?)',
               (service_id,version,*values,now() if stamp is None else iso(stamp),actor))
    return dict(db.execute('SELECT * FROM service_slo_policies WHERE service_id=? AND version=?',(service_id,version)).fetchone())


def initialize_policies(path):
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        for row in db.execute('SELECT id FROM services').fetchall():
            record_policy(db,row['id'],'Inicialização')


def metric(good, observed, expected, target, policy_complete):
    unknown=expected-observed
    bad=observed-good
    lower=good/expected*100
    upper=(good+unknown)/expected*100
    target_decimal=Decimal(str(target))
    allowed=float(Decimal(expected)*(1-target_decimal/100))
    status=('policy_partial' if not policy_complete else
            'met' if Decimal(good)*100>=Decimal(expected)*target_decimal else
            'breached' if Decimal(good+unknown)*100<Decimal(expected)*target_decimal else 'insufficient_data')
    return {'target_percent':target,'good_slots':good,'bad_slots':bad,'unknown_slots':unknown,
            'observed_percent':good/observed*100 if observed else None,
            'lower_percent':lower,'upper_percent':upper,'status':status,
            'error_budget':{'allowed_slots':allowed,'confirmed_bad_slots':bad,
                            'remaining_min_slots':allowed-bad-unknown,'remaining_max_slots':allowed-bad}}


def assess(db, service, duration, end):
    start=end-duration
    expected=duration//INTERVAL
    policy=db.execute('SELECT * FROM service_slo_policies WHERE service_id=? ORDER BY version DESC LIMIT 1',(service['id'],)).fetchone()
    if not policy:
        return {'service_id':service['id'],'service_name':service['name'],'status':'policy_unavailable'}
    policy=dict(policy)
    first_eligible=max(start,math.ceil(datetime.fromisoformat(policy['valid_from']).timestamp()/INTERVAL)*INTERVAL)
    policy_complete=first_eligible<=start
    slots={}
    raw_count=0
    for row in db.execute("""SELECT available,latency_ms,observed_at FROM observations
        WHERE service_id=? AND source='prometheus' AND observed_at>=? AND observed_at<? ORDER BY observed_at,id""",
        (service['id'],iso(start),iso(end))):
        stamp=datetime.fromisoformat(row['observed_at']).timestamp()
        latency=row['latency_ms']
        if not start<=stamp<end or row['available'] not in (0,1) or not math.isfinite(latency) or latency<0:
            continue
        raw_count+=1
        key=int(stamp)//INTERVAL*INTERVAL
        available=bool(row['available'])
        timely=available and latency<=policy['latency_ms']
        existing=slots.get(key)
        if existing:
            existing['available'] &= available
            existing['timely'] &= timely
            existing['latency_ms']=max(existing['latency_ms'],latency)
        else:
            slots[key]={'available':available,'timely':timely,'latency_ms':latency}
    eligible={stamp:value for stamp,value in slots.items() if stamp>=first_eligible}
    observed=len(eligible)
    good_available=sum(r['available'] for r in eligible.values())
    good_timely=sum(r['timely'] for r in eligible.values())
    availability=metric(good_available,observed,expected,policy['availability_percent'],policy_complete)
    latency=metric(good_timely,observed,expected,policy['latency_percent'],policy_complete)
    states=(availability['status'],latency['status'])
    status=('policy_partial' if not policy_complete else 'breached' if 'breached' in states else
            'met' if all(s=='met' for s in states) else 'insufficient_data')
    successful_latencies=sorted(r['latency_ms'] for r in eligible.values() if r['available'])
    p95=successful_latencies[math.ceil(.95*len(successful_latencies))-1] if successful_latencies else None
    bins=min(60,expected)
    timeline=[]
    for index in range(bins):
        left=index*expected//bins
        right=(index+1)*expected//bins
        stamps=range(start+left*INTERVAL,start+right*INTERVAL,INTERVAL)
        observed_bin=[eligible[t] for t in stamps if t in eligible]
        timeline.append({'start':iso(start+left*INTERVAL),'end':iso(start+right*INTERVAL),
                         'expected':right-left,'observed':len(observed_bin),
                         'bad_availability':sum(not r['available'] for r in observed_bin),
                         'bad_latency':sum(not r['timely'] for r in observed_bin)})
    return {'service_id':service['id'],'service_name':service['name'],'team':service['team'],
            'status':status,'policy':policy,'policy_covers_window':policy_complete,
            'expected_slots':expected,'observed_slots':observed,'unknown_slots':expected-observed,
            'raw_samples':raw_count,'raw_observed_slots':len(slots),
            'data_coverage_percent':len(slots)/expected*100,'eligible_coverage_percent':observed/expected*100,
            'excluded_before_policy_slots':len(slots)-observed,
            'availability':availability,'latency':latency,'p95_successful_ms':p95,
            'p95_successful_slots':len(successful_latencies),'timeline':timeline}


def report(path, window, clock=None):
    end=math.floor(((time.time() if clock is None else clock)-SETTLEMENT_DELAY)/INTERVAL)*INTERVAL
    duration=WINDOWS[window]
    with database(path) as db:
        db.execute('BEGIN')
        rows=[dict(r) for r in db.execute('SELECT s.*,t.enabled AS monitoring_enabled,t.target_url FROM services s JOIN telemetry_targets t ON t.service_id=s.id ORDER BY s.id')]
        approved=allowed_urls()
        services=[{**assess(db,row,duration,end),'collection_state':'paused' if not row['monitoring_enabled'] else 'enabled' if row['target_url'] in approved else 'blocked'} for row in rows]
    return {'window':window,'start':iso(end-duration),'end':iso(end),'interval_seconds':INTERVAL,'settlement_delay_seconds':SETTLEMENT_DELAY,
            'expected_slots_per_service':duration//INTERVAL,'source':'prometheus',
            'generated_at':now(),'services':services}


class ReportCache:
    """One calculation at a time, at most three seconds of reuse per window.

    New observations, policies, service edits and target changes invalidate reuse.
    Out-of-band SQL updates are covered by the short TTL, not claimed immediate.
    """
    def __init__(self,path):
        self.path=path
        self.lock=threading.Lock()
        self.entries={}
        self.ttl=3
        self.wait_seconds=5

    def signature(self):
        with database(self.path) as db:
            db.execute('BEGIN')
            latest=db.execute('SELECT MAX(id) FROM observations').fetchone()[0]
            policies=tuple(tuple(r) for r in db.execute('SELECT service_id,MAX(version) FROM service_slo_policies GROUP BY service_id ORDER BY service_id'))
            targets=tuple(tuple(r) for r in db.execute('SELECT service_id,enabled,target_url,updated_at FROM telemetry_targets ORDER BY service_id'))
            services=tuple(tuple(r) for r in db.execute('SELECT id,name,team,slo_availability,slo_latency_ms,slo_latency_percent FROM services ORDER BY id'))
        return latest,policies,targets,services

    def get(self,window):
        from fastapi import HTTPException
        if not self.lock.acquire(timeout=self.wait_seconds):
            raise HTTPException(503,'Cálculo de SLO ocupado. Tenta novamente dentro de instantes.',headers={'Retry-After':'1'})
        try:
            end=math.floor((time.time()-SETTLEMENT_DELAY)/INTERVAL)*INTERVAL
            signature=(end,self.signature())
            entry=self.entries.get(window)
            age=time.monotonic()-entry[0] if entry else self.ttl+1
            if entry and entry[1]==signature and age<self.ttl:
                result=entry[2]
            else:
                result=report(self.path,window)
                self.entries[window]=(time.monotonic(),signature,result)
                age=0
            return {**result,'cache_age_seconds':round(age,3),'cache_max_age_seconds':self.ttl}
        finally:
            self.lock.release()
