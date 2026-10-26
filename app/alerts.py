"""Confirmed probe alerts and durable, one-time acknowledgement escalation."""
import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone

from .db import audit, database, event, now
from .models import AlertRuleInput
from .monitoring import active_targets


def rule_for(db, service_id):
    row = db.execute('SELECT * FROM alert_rules WHERE service_id=?', (service_id,)).fetchone()
    return {'service_id':service_id, 'config':json.loads(row['config']) if row else AlertRuleInput().model_dump(),
            'version':row['version'] if row else 0, 'updated_at':row['updated_at'] if row else ''}


def confirmed(rows, count, clock):
    if len(rows) < count:
        return False
    stamps = [datetime.fromisoformat(r['observed_at']).timestamp() for r in rows[:count]]
    return clock-stamps[0] <= 45 and all(0 < a-b <= 25 for a,b in zip(stamps,stamps[1:]))


def recovered(db, service_id, clock):
    target = next((t for t in active_targets(db).values() if t['service_id']==service_id),None)
    state = db.execute('SELECT * FROM alert_states WHERE service_id=?',(service_id,)).fetchone()
    rule = rule_for(db,service_id)
    if not target or not state or state['condition']!='healthy' or not state['last_sample']:
        return False
    config=rule['config']
    threshold=config['latency_ms']
    if threshold is None:
        threshold=db.execute('SELECT slo_latency_ms FROM services WHERE id=?',(service_id,)).fetchone()[0]
    cutoff=max(target['updated_at'],rule['updated_at'])
    rows=db.execute("SELECT * FROM observations WHERE service_id=? AND source='prometheus' AND observed_at>=? ORDER BY observed_at DESC LIMIT ?",
                    (service_id,cutoff,config['recovery_samples'])).fetchall()
    return state['last_sample']>=cutoff and confirmed(rows,config['recovery_samples'],clock) and all(r['available'] and r['latency_ms']<=threshold for r in rows)


def evaluate(db, clock):
    for target in active_targets(db).values():
        service = db.execute('SELECT * FROM services WHERE id=?', (target['service_id'],)).fetchone()
        rule = rule_for(db,service['id'])
        config = rule['config']
        threshold = config['latency_ms'] if config['latency_ms'] is not None else service['slo_latency_ms']
        count = max(config['failure_samples'],config['recovery_samples'])
        rows = db.execute("SELECT * FROM observations WHERE service_id=? AND source='prometheus' AND observed_at>=? ORDER BY observed_at DESC LIMIT ?",
                          (service['id'],max(target['updated_at'],rule['updated_at']),count)).fetchall()
        if not rows:
            continue
        previous = db.execute('SELECT * FROM alert_states WHERE service_id=?', (service['id'],)).fetchone()
        if previous and rows[0]['observed_at'] <= previous['last_sample']:
            continue
        bad, good = rows[:config['failure_samples']], rows[:config['recovery_samples']]
        if confirmed(rows,config['failure_samples'],clock) and all(not r['available'] for r in bad):
            condition = 'down'
        elif confirmed(rows,config['failure_samples'],clock) and all(r['available'] and r['latency_ms']>threshold for r in bad):
            condition = 'latency'
        elif confirmed(rows,config['recovery_samples'],clock) and all(r['available'] and r['latency_ms']<=threshold for r in good):
            condition = 'healthy'
        else:
            continue
        prior = previous['condition'] if previous else 'healthy'
        iid = previous['incident_id'] if previous else None
        can_alert = config['enabled'] and (config['outage_enabled'] if condition=='down' else config['latency_enabled'])
        severity = config['outage_severity'] if condition=='down' else config['latency_severity']
        if condition == 'healthy':
            if prior != 'healthy' and iid and db.execute("SELECT 1 FROM incidents WHERE id=? AND status NOT IN ('resolved','closed')",(iid,)).fetchone():
                event(db,iid,'Monitorização','Serviço recuperado',
                      f'{config["recovery_samples"]} sondagens HTTP recentes confirmam recuperação dentro do limite de {threshold} ms. O incidente aguarda resolução e fecho pela equipa.')
                audit(db,'Monitorização','alert.recovered',f'incident:{iid}')
        elif can_alert and (prior=='healthy' or not previous or iid is None):
            existing = db.execute("SELECT id FROM incidents WHERE service_id=? AND source='prometheus-alert' AND status NOT IN ('resolved','closed')", (service['id'],)).fetchone()
            description = (f'{config["failure_samples"]} sondagens HTTP reais consecutivas confirmam {"indisponibilidade" if condition=="down" else "latência elevada"}. '
                           f'Origem: Prometheus. Última sondagem: {rows[0]["observed_at"]}. Sucesso: {rows[0]["available"]}; '
                           f'duração: {rows[0]["latency_ms"]:.2f} ms; limite de alerta: {threshold} ms; versão da regra: {rule["version"]}.')
            if existing:
                iid = existing['id']
                event(db,iid,'Monitorização','Falha recorrente agrupada',description)
            else:
                title = ('Serviço indisponível' if condition=='down' else 'Latência acima do limite de alerta')+' · '+service['name']
                cursor = db.execute("""INSERT INTO incidents(service_id,title,description,severity,status,created_at,source)
                    VALUES(?,?,?,?,'open',?,'prometheus-alert')""", (service['id'],title,description,severity,now()))
                iid = cursor.lastrowid
                context = {**config,'effective_latency_ms':threshold,'target_key':target['target_key']}
                db.execute('INSERT INTO incident_alert_context VALUES(?,?,?,?)',(iid,json.dumps(context),rule['version'],now()))
                event(db,iid,'Monitorização','Alerta confirmado por sondagens',description)
                audit(db,'Monitorização','incident.created',f'incident:{iid}',title)
        if condition!='healthy' and can_alert and iid:
            incident = db.execute('SELECT severity,status FROM incidents WHERE id=?',(iid,)).fetchone()
            if int(severity[1]) < int(incident['severity'][1]) and incident['status'] not in ('resolved','closed'):
                db.execute('UPDATE incidents SET severity=? WHERE id=?',(severity,iid))
                event(db,iid,'Monitorização',f'Prioridade elevada para {severity}','Condição técnica confirmada pela regra de alerta.')
                audit(db,'Monitorização','incident.escalated',f'incident:{iid}',severity)
        db.execute('INSERT OR REPLACE INTO alert_states VALUES(?,?,?,?)',(service['id'],condition,rows[0]['observed_at'],iid))


def escalate(db, clock):
    targets = {t['service_id']:t for t in active_targets(db).values()}
    rows = db.execute("""SELECT i.* FROM incidents i WHERE i.source='prometheus-alert' AND i.status='open'
        AND i.acknowledged_at IS NULL AND NOT EXISTS (SELECT 1 FROM incident_escalations e WHERE e.incident_id=i.id)""").fetchall()
    for incident in rows:
        target = targets.get(incident['service_id'])
        if not target:
            continue
        rule = rule_for(db,incident['service_id'])
        config = rule['config']
        if not config['enabled'] or not config['escalation_enabled']:
            continue
        start = max(incident['created_at'],rule['updated_at'],target['updated_at'])
        deadline=datetime.fromisoformat(start)+timedelta(seconds=config['acknowledge_seconds'])
        if datetime.fromtimestamp(clock,timezone.utc) < deadline:
            continue
        stamp = datetime.fromtimestamp(clock,timezone.utc).isoformat()
        db.execute('INSERT INTO incident_escalations VALUES(?,?,?,?,?,?)',
                   (incident['id'],stamp,incident['severity'],'P1',config['acknowledge_seconds'],rule['version']))
        changed = incident['severity']!='P1'
        if changed:
            db.execute("UPDATE incidents SET severity='P1' WHERE id=?",(incident['id'],))
        action = 'Escalonamento por falta de reconhecimento' if changed else 'Prazo de reconhecimento ultrapassado'
        note = f'Prazo de {config["acknowledge_seconds"]} s ultrapassado. {incident["severity"]} → P1. Regra v{rule["version"]}. Não foi enviada uma notificação externa.'
        event(db,incident['id'],'Monitorização',action,note,stamp)
        audit(db,'Monitorização','incident.escalated' if changed else 'incident.ack_deadline.overdue',f'incident:{incident["id"]}',note)


def tick(path, clock=None):
    clock=time.time() if clock is None else clock
    with database(path) as db:
        db.execute('BEGIN IMMEDIATE')
        escalate(db,clock)
        db.execute("INSERT OR REPLACE INTO settings VALUES('alert_engine_tick',?)",(datetime.fromtimestamp(clock,timezone.utc).isoformat(),))


def engine_status(path):
    with database(path) as db:
        row=db.execute("SELECT value FROM settings WHERE key='alert_engine_tick'").fetchone()
    stamp=row['value'] if row else None
    return {'status':'waiting' if not stamp else 'running' if time.time()-datetime.fromisoformat(stamp).timestamp()<=20 else 'stale',
            'last_tick':stamp,'interval_seconds':5}


async def run_engine(path):
    while True:
        try:
            await asyncio.to_thread(tick,path)
        except Exception:
            logging.getLogger(__name__).error('Motor de escalonamento indisponível; será tentado novamente.')
        await asyncio.sleep(5)
