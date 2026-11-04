"""Self-contained, script-free print view over the existing consistent dossier."""
import base64
import hashlib
import json
from datetime import datetime, timezone
from html import escape

CSS = '''
@page{size:A4;margin:18mm 17mm 20mm}
*{box-sizing:border-box}body{margin:0;background:#eef3f0;color:#203a3e;font:14px/1.7 "Segoe UI",sans-serif}
main{max-width:900px;margin:36px auto;padding:54px 62px;background:white;border-top:6px solid #16756d}
header{border-bottom:1px solid #d9e4df;padding-bottom:26px;margin-bottom:30px}.brand{font-weight:750;font-size:25px;letter-spacing:-1px}.eyebrow{font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#557770;margin:22px 0 10px}h1,h2{font-family:Georgia,serif;font-weight:normal;line-height:1.25}h1{font-size:34px;margin:8px 0 18px;overflow-wrap:anywhere}h2{font-size:23px;margin:36px 0 16px;break-after:avoid}h3{font-size:14px;margin:20px 0 8px;break-after:avoid}p{margin:8px 0 15px}.muted,dt,small{color:#607575}.notice{border-left:3px solid #b99a56;padding:12px 18px;background:#faf7ef;font-size:12px}.status{font-size:12px;font-weight:600;color:#17675d}dl{display:grid;grid-template-columns:180px minmax(0,1fr);gap:9px 22px;margin:0}dd{margin:0;overflow-wrap:anywhere}dt{font-size:12px}.text{white-space:pre-wrap;overflow-wrap:anywhere}.entry{border-left:2px solid #c6dcd2;padding:0 0 18px 22px;margin-bottom:12px;break-inside:avoid}.entry h3{margin:0 0 5px}.entry small{display:block;margin-bottom:10px;font-size:11px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.65 Consolas,monospace;padding:16px;background:#f3f6f4;border:1px solid #dce6e0;max-width:100%}.appendix{break-before:page}.appendix article{margin-bottom:28px}footer{margin-top:40px;border-top:1px solid #d9e4df;padding-top:16px;font-size:10px;color:#607575}.print-help{font-size:12px;color:#43665e;padding:12px 0}.entry:has(pre){break-inside:auto}
@media screen and (max-width:700px){main{margin:0;padding:28px 22px}h1{font-size:28px}dl{grid-template-columns:1fr;gap:3px}dd{margin-bottom:12px}}
@media print{body{background:white;font-size:10pt;line-height:1.55}main{max-width:none;margin:0;padding:0;border:0}.print-help{display:none}h1{font-size:25pt}h2{font-size:17pt}pre{font-size:8pt;background:white}.notice{background:white}.entry{padding-bottom:12px}a{color:inherit}}
'''.strip()
STYLE_HASH = base64.b64encode(hashlib.sha256(CSS.encode()).digest()).decode()
CSP = ("default-src 'none'; style-src 'sha256-" + STYLE_HASH +
       "'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
STATES = {'open':'Aberto','acknowledged':'Reconhecido','investigating':'Em investigação',
          'resolved':'Resolvido','closed':'Fechado'}


def text(value):
    return escape(str(value if value is not None else 'Não registado'), quote=True)


def stamp(value):
    if not value:
        return 'Não registado'
    try:
        date = datetime.fromisoformat(value)
        if date.tzinfo is not None:
            return date.astimezone(timezone.utc).strftime('%d/%m/%Y · %H:%M:%S UTC')
    except (ValueError, TypeError):
        pass
    return str(value)


def definitions(items):
    return '<dl>'+''.join(f'<dt>{text(label)}</dt><dd>{text(value)}</dd>' for label,value in items)+'</dl>'


def preserved(value):
    return '<pre>'+text(json.dumps(value,ensure_ascii=False,indent=2))+'</pre>'


def render(report):
    i = report['incident']
    service = report['service_at_export']
    assignee = report['assignee_at_export']
    identifier = f"INC-{i['id']:03d}"
    provenance = 'Exemplo sintético de demonstração' if i['source'].startswith('demo') else 'Registo operacional · '+i['source']
    sections = ['<!doctype html><html lang="pt-PT"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="referrer" content="no-referrer">',
        f'<meta http-equiv="Content-Security-Policy" content="{text(CSP)}">',
        f'<title>Nexo · Dossier {text(identifier)}</title><style>{CSS}</style></head><body><main>',
        '<header><div class="brand">nexo / operações</div><p class="eyebrow">Dossier de incidente</p>',
        f'<p class="status">{text(identifier)} · {text(STATES.get(i["status"],i["status"]))} · {text(i["severity"])}</p>',
        f'<h1>{text(i["title"])}</h1><p class="muted">Exportado em {text(stamp(report["exported_at"]))}</p></header>',
        '<p class="print-help">Para guardar como PDF: Ctrl+P → Guardar como PDF. Escolhe papel A4 e desativa os cabeçalhos e rodapés do navegador.</p>',
        '<p class="notice">Fotografia do registo no momento da exportação. O caso pode mudar posteriormente. Os nomes do serviço e do responsável correspondem ao inventário atual. Rever informação interna antes de partilhar.</p>',
        '<h2>01 / Identificação e datas</h2>',
        definitions([('Serviço',service['name']),('Equipa',service['team']),
            ('Responsável',assignee['name'] if assignee else 'Por atribuir'),('Origem',provenance),
            ('Registado',stamp(i['created_at'])),('Reconhecido',stamp(i.get('acknowledged_at'))),
            ('Resolvido',stamp(i.get('resolved_at'))),('Fechado',stamp(i.get('closed_at')))]),
        '<h2>02 / Sintomas e tratamento</h2>']
    for key,label in [('description','Descrição'),('resolution','Resolução'),('root_cause','Causa raiz'),
                      ('prevention','Prevenção'),('runbook','Runbook')]:
        sections.append(f'<h3>{label}</h3><p class="text">{text(i.get(key) or "Não registado")}</p>')
    sections.append('<h2>03 / Linha temporal completa</h2>')
    for entry in i['timeline']:
        sections.append(f'<article class="entry"><h3>{text(entry["action"])}</h3><small>{text(stamp(entry["created_at"]))} · {text(entry["actor"])}</small><p class="text">{text(entry["note"])}</p></article>')
    if not i['timeline']:
        sections.append('<p>Sem eventos registados.</p>')
    sections.append('<h2>04 / Ações de prevenção</h2>')
    for action in i.get('follow_ups',[]):
        state = {'open':'Pendente','completed':'Concluída','cancelled':'Cancelada'}[action['status']]
        sections.append('<article class="entry"><h3>'+text(action['title'])+'</h3>'+definitions([
            ('Estado',state+(' · Prazo ultrapassado' if action['overdue'] else '')),
            ('Responsável na criação',action['owner_name']),('Prazo · dia UTC',action['due_date']),
            ('Decisão final',action['completion_note'] or 'Não registada'),
            ('Decisão por',action['finished_by'] or 'Não registado'),('Terminada em',stamp(action['finished_at']))])+'</article>')
    if not i.get('follow_ups'):
        sections.append('<p>Sem ações de prevenção registadas.</p>')
    sections.append('<section class="appendix"><h2>05 / Evidências e contexto técnico</h2>')
    for key,label in [('detection_context','Regra preservada na deteção'),('escalation','Escalonamento registado')]:
        sections.append(f'<h3>{label}</h3>'+ (preserved(i[key]) if i.get(key) else '<p>Não registado.</p>'))
    sections.append('<h3>Recolhas de evidência</h3>')
    for entry in i['evidence']:
        sections.append(f'<article><h3>Recolha {text(entry["id"])} · {text(entry["source"])}</h3><p class="muted">{text(stamp(entry["captured_at"]))} · {text(entry["actor"])}</p>{preserved(entry["payload"])}</article>')
    if not i['evidence']:
        sections.append('<p>Sem recolhas de logs preservadas neste caso.</p>')
    sections.append('</section><footer>'+text(report['scope'])+'<br>'+text(
        f"Nexo {report['application_version']} · Esquema de exportação {report['schema_version']}")+
        '<br>Este dossier não é uma cópia de segurança nem uma assinatura digital. Datas apresentadas em UTC quando registadas com fuso horário.</footer></main></body></html>')
    return ''.join(sections)
