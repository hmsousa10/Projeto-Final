"""Validate actual probe coverage, latency objective and unknown data during a scrape outage."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import runpy

helpers=runpy.run_path(str(Path(__file__).with_name('validar-laboratorio.py')))
api,wait_until,compose=helpers['api'],helpers['wait_until'],helpers['compose']


def main():
    api('login',{'email':'admin@local.test','password':os.getenv('DEMO_PASSWORD','EstudoLocal2026!')})
    services=api('services')
    portal=next(s['id'] for s in services if s.get('monitoring') and s['monitoring']['target_key']=='portal-lab')
    slow=next(s['id'] for s in services if s.get('monitoring') and s['monitoring']['target_key']=='api-lab')
    def report():
        return api('slo?window=1m')
    def item(sid):
        return next(s for s in report()['services'] if s['service_id']==sid)
    wait_until(lambda:item(portal)['status']=='met' and item(portal)['observed_slots']==6,
               'complete one-minute probe window meets portal objectives',timeout=125)
    before=item(portal)
    delayed=item(slow)
    assert delayed['availability']['status']=='met'
    assert delayed['latency']['status']=='breached'
    assert delayed['p95_successful_ms']>delayed['policy']['latency_ms']
    print('PASS: HTTP availability and slow successful responses have different outcomes',flush=True)
    try:
        compose('stop','prometheus')
        wait_until(lambda:item(portal)['status']=='insufficient_data' and item(portal)['unknown_slots']>0,
                   'missing scrape data makes availability inconclusive',timeout=90)
        missing=item(portal)
        assert missing['availability']['bad_slots']==0
        assert missing['availability']['status']=='insufficient_data'
        assert missing['availability']['lower_percent']<missing['availability']['target_percent']<=missing['availability']['upper_percent']
        assert api('alert-engine')['status']=='running'
        print('PASS: missing probes are unknown, not fabricated successes or service failures',flush=True)
    finally:
        compose('start','prometheus')
    wait_until(lambda:item(portal)['status']=='met' and item(portal)['observed_slots']==6,
               'coverage returns after the missing intervals leave the rolling window',timeout=125)
    after=item(portal)
    def summary(value):
        return {key:value[key] for key in ('service_id','status','policy_covers_window','observed_slots','unknown_slots','eligible_coverage_percent','availability')}
    evidence={'status':'passed','executed_at':datetime.now(timezone.utc).isoformat(),'window':'1m',
              'settlement_delay_seconds':report()['settlement_delay_seconds'],
              'before':summary(before),'during_collection_outage':summary(missing),'after':summary(after),
              'slow_service_latency_status':delayed['latency']['status'],
              'steps':['full real probe coverage','separate latency outcome','Prometheus outage','unknown slots','conservative bounds','collection restored']}
    (Path(__file__).resolve().parent.parent/'docs'/'validacao-slo.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=True),flush=True)


if __name__=='__main__':
    main()
