"""Read-only incident dossiers; callers hold one SQLite read transaction."""
import json
import re

from fastapi import HTTPException

from .db import now
from .version import VERSION


def incident_snapshot(db, iid):
    row = db.execute('SELECT * FROM incidents WHERE id=?', (iid,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Incidente não encontrado.')
    result = dict(row)
    result['timeline'] = [dict(r) for r in db.execute(
        'SELECT * FROM timeline WHERE incident_id=? ORDER BY created_at,id', (iid,))]
    result['evidence'] = [{**dict(r), 'payload': json.loads(r['payload'])} for r in db.execute(
        'SELECT * FROM incident_evidence WHERE incident_id=? ORDER BY id', (iid,))]
    context = db.execute('SELECT * FROM incident_alert_context WHERE incident_id=?', (iid,)).fetchone()
    result['detection_context'] = {**dict(context), 'config': json.loads(context['config'])} if context else None
    escalation = db.execute('SELECT * FROM incident_escalations WHERE incident_id=?', (iid,)).fetchone()
    result['escalation'] = dict(escalation) if escalation else None
    return result


def build(db, iid):
    incident = incident_snapshot(db, iid)
    service = db.execute('SELECT id,name,team,description,criticality FROM services WHERE id=?',
                         (incident['service_id'],)).fetchone()
    assignee = db.execute('SELECT id,name FROM users WHERE id=?', (incident['assignee_id'],)).fetchone()
    return {'schema_version': 1, 'application_version': VERSION, 'exported_at': now(),
            'scope': 'Registo do incidente e evidências preservadas; não inclui logs em direto nem sugestões recalculadas.',
            'service_at_export': dict(service), 'assignee_at_export': dict(assignee) if assignee else None,
            'incident': incident}


def literal(value):
    """Fence untrusted text, using a delimiter longer than any embedded fence."""
    value = str(value if value is not None else 'Não registado')
    longest = max((len(m.group()) for m in re.finditer(r'`+', value)), default=0)
    fence = '`' * max(3, longest + 1)
    return f'{fence}\n{value}\n{fence}\n'


def markdown(report):
    incident = report['incident']
    sections = [f"# Nexo · Dossier INC-{incident['id']:03d}\n",
                'Exportação do registo disponível. Um caso ainda aberto pode mudar após esta exportação.\n',
                '## Identificação da exportação\n', literal(json.dumps({k: v for k, v in report.items()
                    if k not in ('incident', 'service_at_export', 'assignee_at_export')}, ensure_ascii=False, indent=2)),
                '## Serviço e responsável no momento da exportação\n',
                'Estes nomes e dados são atuais; não constituem versões históricas do inventário.\n',
                literal(json.dumps({'service': report['service_at_export'], 'assignee': report['assignee_at_export']},
                                   ensure_ascii=False, indent=2)), '## Estado e datas do incidente\n',
                literal(json.dumps({k: v for k, v in incident.items() if k not in
                    ('title','description','resolution','root_cause','prevention','runbook','timeline','evidence','detection_context','escalation')},
                                   ensure_ascii=False, indent=2))]
    for key, title in [('title','Título'),('description','Descrição'),('resolution','Resolução'),
                       ('root_cause','Causa raiz'),('prevention','Prevenção'),('runbook','Runbook')]:
        sections.extend([f'## {title}\n', literal(incident[key] or 'Não registado')])
    for key, title in [('detection_context','Regra preservada na deteção'),('escalation','Escalonamento registado')]:
        sections.extend([f'## {title}\n', literal(json.dumps(incident[key], ensure_ascii=False, indent=2))])
    sections.append('## Linha temporal completa\n')
    for n, entry in enumerate(incident['timeline'], 1):
        sections.extend([f'### Evento {n}\n', literal(json.dumps(entry, ensure_ascii=False, indent=2))])
    sections.append('## Evidências preservadas\n')
    for n, entry in enumerate(incident['evidence'], 1):
        sections.extend([f'### Recolha {n}\n', literal(json.dumps(entry, ensure_ascii=False, indent=2))])
    if not incident['evidence']:
        sections.append('Sem recolhas de logs preservadas neste caso.\n')
    sections.append('O dossier pode conter notas e nomes internos. Rever antes de partilhar. Não é uma cópia de segurança nem uma assinatura digital.\n')
    return '\n'.join(sections)
