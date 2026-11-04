import os
import asyncio
import json
import hashlib
from contextlib import suppress
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .incident_concurrency import check_revision
from .db import audit, database, event, initialize, now
from .models import Assignment, Comment, IncidentInput, IncidentUpdate, Login, Scenario, ServiceInput, LabFault, MonitoringInput, AlertRuleInput
from .models import password_policy
from .security import check_password, hash_password, token_hash, password_capacity
from .seed import seed
from .request_limits import BodyLimitMiddleware
from . import telemetry, dossier, incident_knowledge, audit_log, incident_browse, incident_impact, enterprise, enterprise_monitoring
from . import lab, logs, monitoring
from . import accounts, alerts, slo
from .knowledge import Knowledge, corpus as knowledge_corpus
from .version import VERSION
from . import printable_dossier, follow_ups
from .bootstrap import initial_password
from .accesslog import install as install_access_filter
from .inventory import validate_dependencies

ROOT = Path(__file__).resolve().parent.parent
STATES = {'open': 'Aberto', 'acknowledged': 'Reconhecido', 'investigating': 'Em investigação',
          'resolved': 'Resolvido', 'closed': 'Fechado'}
NEXT = dict(zip(list(STATES)[:-1], list(STATES)[1:]))


def create_app(db_path=None, demo=None):
    install_access_filter()
    path = str(db_path or os.getenv('DATABASE_PATH', ROOT / 'data' / 'nexo.db'))
    demo_mode = demo if demo is not None else os.getenv('DEMO_MODE', '1') == '1'
    production = os.getenv('APP_ENV', 'local') == 'production'
    lab_mode = os.getenv('LAB_MODE', '0') == '1'
    if lab_mode and (production or not demo_mode):
        raise RuntimeError('Os controlos de falha só podem ser ativados na demonstração local.')
    loki_url = telemetry.validate_url(os.environ['LOKI_URL']) if os.getenv('LOKI_URL') else ''
    prometheus_url = os.getenv('PROMETHEUS_URL', '')
    monitoring.allowed_urls()  # Fail early on invalid deployment policy.
    sd_token = monitoring.discovery_token() if os.getenv('MONITORING_SD_TOKEN_FILE') else ''
    if prometheus_url:
        prometheus_url = telemetry.validate_url(prometheus_url)
    hosts = [host.strip() for host in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if host.strip()]
    public_origin = os.getenv('APP_ORIGIN', '').rstrip('/')
    secure_cookie = production or os.getenv('COOKIE_SECURE', '0') == '1'
    if not hosts or any('*' in host or '/' in host for host in hosts):
        raise RuntimeError('ALLOWED_HOSTS exige nomes explícitos, sem wildcards nem URLs.')
    # Igualar o trabalho criptográfico para contas existentes e inexistentes.
    dummy_password_hash = hash_password(secrets.token_urlsafe(32))
    knowledge_engine = Knowledge.configured(path)
    enterprise_client = enterprise.EnterpriseClient.configured()
    slo_cache = slo.ReportCache(path)

    @asynccontextmanager
    async def lifespan(app):
        from .maintenance import require_ready
        require_ready(path)
        if production:
            origin = urlsplit(public_origin)
            if demo_mode:
                raise RuntimeError('O modo de demonstração não pode ser usado em produção.')
            if origin.scheme != 'https' or not origin.hostname or origin.hostname not in hosts or origin.path or origin.query or origin.fragment or origin.username:
                raise RuntimeError('Produção exige APP_ORIGIN HTTPS e o respetivo domínio em ALLOWED_HOSTS.')
        initialize(path)
        knowledge_engine.initialize()
        if lab_mode:
            lab.control_token()
        if demo_mode:
            seed(path)
        else:
            with database(path) as db:
                marked = db.execute("SELECT 1 FROM settings WHERE key='demo_initialized' AND value='1'").fetchone()
                legacy = db.execute("SELECT 1 FROM incidents WHERE source LIKE 'demo%' LIMIT 1").fetchone()
                demo_users = db.execute("SELECT name FROM users WHERE email IN ('operacoes@local.test','leitor@local.test') LIMIT 1").fetchone()
                if marked or legacy or demo_users:
                    raise RuntimeError('Esta base contém dados/contas de demonstração. Usa uma base vazia para o ambiente sem demonstração; os dados existentes foram preservados.')
                if not db.execute('SELECT id FROM users LIMIT 1').fetchone():
                    password = initial_password()
                    minimum = 15 if production else 12
                    if not minimum <= len(password) <= 200:
                        raise RuntimeError(f'Defina INITIAL_ADMIN_PASSWORD com {minimum} a 200 caracteres.')
                    if production:
                        try:
                            password_policy(password)
                        except ValueError:
                            raise RuntimeError('Produção exige uma palavra-passe inicial de 15 a 200 caracteres, diferente das palavras-passe comuns e da demonstração.') from None
                    db.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',
                               ('Administrador', os.getenv('INITIAL_ADMIN_EMAIL', 'admin@local.test'),
                                hash_password(password), 'admin'))
        enterprise_monitoring.configure(path, enterprise_client)
        worker = None
        if prometheus_url:
            if demo_mode:
                telemetry.initialize_targets(path)
            worker = asyncio.create_task(telemetry.run_collector(path, prometheus_url))
        slo.initialize_policies(path)
        enterprise_worker = asyncio.create_task(enterprise_monitoring.run(path, enterprise_client)) if enterprise_client.url else None
        escalation_worker = asyncio.create_task(alerts.run_engine(path))
        knowledge_worker = asyncio.create_task(knowledge_engine.run_indexer()) if knowledge_engine.encoder else None
        try:
            yield
        finally:
            if enterprise_worker:
                enterprise_worker.cancel()
                with suppress(asyncio.CancelledError):
                    await enterprise_worker
            if knowledge_worker:
                knowledge_worker.cancel()
                with suppress(asyncio.CancelledError):
                    await knowledge_worker
            escalation_worker.cancel()
            with suppress(asyncio.CancelledError):
                await escalation_worker
            if worker:
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker

    app = FastAPI(title='Nexo · Operações', version=VERSION, lifespan=lifespan,
                  docs_url=None if production else '/docs', redoc_url=None,
                  openapi_url=None if production else '/openapi.json')
    app.state.db_path = path

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Validation errors must not echo passwords or other submitted values.
        return JSONResponse(status_code=422, content={'detail':[
            {key:item[key] for key in ('loc','msg','type')} for item in error.errors()]})

    @app.middleware('http')
    async def browser_security(request, call_next):
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and request.url.path not in ('/api/login', '/api/logout'):
            from .maintenance import blocks_writes
            try:
                blocked = blocks_writes(path)
            except (OSError, ValueError):
                blocked = True
            if blocked:
                return JSONResponse(status_code=503, content={'detail': 'Verificação de manutenção em curso. Aguarda a conclusão local.'}, headers={'Retry-After': '5'})
        if production and request.url.scheme != 'https' and request.url.path != '/api/health':
            return Response('HTTPS obrigatório.', status_code=400)
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
            expected_origin = public_origin or str(request.base_url).rstrip('/')
            if origin != expected_origin:
                return Response('Origem não permitida.', status_code=403)
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and request.headers.get('sec-fetch-site') == 'cross-site':
            return Response('Origem não permitida.', status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if production:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        if not request.url.path.startswith('/docs') and 'Content-Security-Policy' not in response.headers:
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            )
        if request.url.path.startswith(('/api/', '/internal/')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    def current_user(request: Request):
        cookie = request.cookies.get('nexo_session', '')
        with database(path) as db:
            user = db.execute('''SELECT u.id,u.name,u.email,u.role,u.must_change_password FROM sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.expires_at>? AND u.active=1''', (token_hash(cookie), now())).fetchone()
        if not user:
            raise HTTPException(401, 'Inicia sessão para continuar.')
        if user['must_change_password'] and request.url.path not in ('/api/me','/api/logout','/api/account/password'):
            raise HTTPException(403, 'Altera a palavra-passe inicial antes de continuar.')
        return dict(user)

    def writer(user=Depends(current_user)):
        if user['role'] not in ('admin', 'operator'):
            raise HTTPException(403, 'O perfil de leitura não pode alterar dados.')
        return user

    def admin(user=Depends(current_user)):
        if user['role'] != 'admin':
            raise HTTPException(403, 'Esta operação exige o perfil de administrador.')
        return user

    accounts.routes(app,path,current_user,admin,secure_cookie)
    from .notifications import routes as notification_routes
    notification_routes(app, path, current_user)
    enterprise.routes(app, enterprise_client, current_user, lambda: enterprise_monitoring.status(path))
    enterprise_monitoring.routes(app, path, enterprise_client, admin)

    def require(db, table, identifier):
        # table is selected by application code only, never from request input.
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Registo não encontrado.')
        return dict(row)

    @app.get('/api/health')
    def health():
        with database(path) as db:
            db.execute('SELECT 1')
        return {'status': 'ok', 'version': VERSION}

    @app.get('/api/config')
    def config():
        return {'demo': demo_mode, 'version': VERSION, 'environment': 'production' if production else 'local', 'enterprise': bool(enterprise_client.url), 'monitoring': bool(prometheus_url and sd_token), 'laboratory': lab_mode, 'logs': bool(loki_url), 'telemetry': 'prometheus' if prometheus_url else 'synthetic' if demo_mode else 'not_connected'}

    @app.get('/internal/targets', include_in_schema=False)
    def discover_targets(request: Request):
        if not sd_token:
            raise HTTPException(404, 'Descoberta desativada.')
        if not secrets.compare_digest(request.headers.get('authorization', '').encode(), ('Bearer ' + sd_token).encode()):
            raise HTTPException(401, 'Descoberta não autorizada.')
        with database(path) as db:
            return monitoring.discovery(db)

    @app.get('/api/monitoring/options')
    def monitoring_options(user=Depends(admin)):
        return {'urls': sorted(monitoring.allowed_urls()), 'enabled': bool(prometheus_url and sd_token)}

    @app.put('/api/services/{sid}/monitoring')
    def configure_monitoring(sid: int, data: MonitoringInput, user=Depends(admin)):
        if not prometheus_url or not sd_token:
            raise HTTPException(503, 'A descoberta de serviços não está configurada nesta instalação.')
        try:
            monitoring.valid_target_url(data.url)
        except ValueError as error:
            raise HTTPException(422, str(error))
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            require(db, 'services', sid)
            target = db.execute('SELECT * FROM telemetry_targets WHERE service_id=?', (sid,)).fetchone()
            enterprise_binding=enterprise_monitoring.binding(db)
            if enterprise_binding and enterprise_binding['service_id']==sid:
                raise HTTPException(409, 'Este serviço é gerido pela integração empresarial autenticada.')
            if (data.enabled or not target) and data.url not in monitoring.allowed_urls():
                raise HTTPException(403, 'Este endereço não consta da lista autorizada da instalação.')
            if target and target['kind'] == 'laboratory':
                raise HTTPException(409, 'Os alvos de referência do laboratório são geridos pela instalação.')
            if target and target['target_url'] != data.url:
                raise HTTPException(409, 'O endereço deste histórico é imutável. Cria um serviço separado para outro endereço.')
            stamp = now()
            if not target:
                if db.execute('SELECT 1 FROM observations WHERE service_id=? LIMIT 1', (sid,)).fetchone():
                    raise HTTPException(409, 'Este serviço já tem observações de outra origem. Cria um serviço novo para preservar a separação dos históricos.')
                if db.execute("SELECT count(*) FROM telemetry_targets WHERE kind='configured'").fetchone()[0] >= 50:
                    raise HTTPException(409, 'Limite de 50 ligações configuráveis atingido.')
                db.execute('INSERT INTO telemetry_targets(target_key,service_id,target_url,enabled,kind,updated_at) VALUES(?,?,?,?,?,?)',
                           (f'service-{sid}', sid, data.url, int(data.enabled), 'configured', stamp))
                action = 'monitoring.connected'
            elif bool(target['enabled']) == data.enabled:
                return dict(target)
            else:
                db.execute('UPDATE telemetry_targets SET enabled=?,updated_at=? WHERE service_id=?', (int(data.enabled), stamp, sid))
                action = 'monitoring.resumed' if data.enabled else 'monitoring.paused'
                for incident in db.execute("SELECT id FROM incidents WHERE service_id=? AND source IN ('prometheus-alert','enterprise-alert') AND status NOT IN ('resolved','closed')", (sid,)):
                    event(db, incident['id'], user['name'], 'Monitorização retomada' if data.enabled else 'Monitorização pausada', 'O estado do incidente mantém-se; são necessárias novas sondagens para confirmar recuperação.')
            audit(db, user['name'], action, f'service:{sid}', data.url)
            return dict(db.execute('SELECT * FROM telemetry_targets WHERE service_id=?', (sid,)).fetchone())

    @app.get('/api/telemetry')
    def telemetry_status(user=Depends(current_user)):
        return telemetry.status(path, bool(prometheus_url))

    @app.get('/api/slo')
    def slo_report(window: Literal['1m','15m','1h','24h','7d']='15m', user=Depends(current_user)):
        return slo_cache.get(window)

    @app.get('/api/services/{sid}/slo/history')
    def slo_policy_history(sid: int, user=Depends(current_user)):
        with database(path) as db:
            require(db,'services',sid)
            return [dict(row) for row in db.execute('SELECT * FROM service_slo_policies WHERE service_id=? ORDER BY version DESC LIMIT 50',(sid,))]

    @app.get('/api/alert-engine')
    def alert_engine_status(user=Depends(current_user)):
        return alerts.engine_status(path)

    @app.get('/api/alert-rules')
    def list_alert_rules(user=Depends(current_user)):
        with database(path) as db:
            return [{**alerts.rule_for(db,row['id']), 'service_name':row['name'],
                     'effective_latency_ms':alerts.rule_for(db,row['id'])['config']['latency_ms'] or row['slo_latency_ms']}
                    for row in db.execute('SELECT id,name,slo_latency_ms FROM services ORDER BY id')]

    @app.put('/api/services/{sid}/alert-rule')
    def save_alert_rule(sid: int, data: AlertRuleInput, user=Depends(admin)):
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            require(db,'services',sid)
            old=alerts.rule_for(db,sid)
            config=data.model_dump()
            if old['config']==config:
                return old
            stamp=now()
            version=old['version']+1
            payload=json.dumps(config)
            db.execute('INSERT OR REPLACE INTO alert_rules VALUES(?,?,?,?)',(sid,payload,stamp,version))
            db.execute('INSERT INTO alert_rule_history VALUES(?,?,?,?,?)',(sid,version,payload,stamp,user['name']))
            changed=[key for key,value in config.items() if old['config'][key]!=value]
            audit(db,user['name'],'alert_rule.updated',f'service:{sid}',f'Versão {version}. Campos: '+', '.join(changed))
            for incident in db.execute("SELECT id FROM incidents WHERE service_id=? AND source IN ('prometheus-alert','enterprise-alert') AND status NOT IN ('resolved','closed')",(sid,)):
                event(db,incident['id'],user['name'],'Regra de alerta alterada',f'Versão {version}. Exige novas sondagens e reinicia a contagem do prazo de reconhecimento.')
            return alerts.rule_for(db,sid)

    @app.get('/api/services/{sid}/alert-rule/history')
    def alert_rule_history(sid: int, user=Depends(admin)):
        with database(path) as db:
            require(db,'services',sid)
            return [{**dict(r),'config':json.loads(r['config'])} for r in db.execute(
                'SELECT * FROM alert_rule_history WHERE service_id=? ORDER BY version DESC LIMIT 50',(sid,))]

    @app.post('/api/lab/fault')
    def lab_fault(data: LabFault, user=Depends(writer)):
        if not lab_mode:
            raise HTTPException(404, 'Laboratório desativado.')
        with database(path) as db:
            audit(db, user['name'], 'lab.fault.requested', data.target, data.kind)
        try:
            result = lab.set_fault(data.target, data.kind)
        except Exception:
            with database(path) as db:
                audit(db, user['name'], 'lab.fault.failed', data.target, data.kind)
            raise HTTPException(503, 'Não foi possível confirmar o controlo do serviço de laboratório.')
        with database(path) as db:
            audit(db, user['name'], 'lab.fault.applied', data.target, data.kind)
        return result

    @app.get('/api/services/{sid}/logs')
    def service_logs(sid: int, user=Depends(current_user)):
        with database(path) as db:
            service = require(db, 'services', sid)
            target = db.execute('SELECT * FROM telemetry_targets WHERE service_id=?', (sid,)).fetchone()
            scope = logs.binding(target)
        if not loki_url or scope is None:
            raise HTTPException(404, 'Este serviço não tem logs ligados.')
        try:
            entries = logs.read_logs(loki_url, scope['service_key'], scope['path'])
        except Exception:
            raise HTTPException(503, 'Não foi possível consultar o Loki. Não significa ausência de erros no serviço.')
        return {'source': 'loki', 'service_id': sid, 'service_name': service['name'],
                'queried_at': now(), 'scope': scope, 'window_minutes': 15, 'limit': 50, 'entries': entries}

    @app.post('/api/login')
    @password_capacity
    def login(data: Login, request: Request, response: Response):
        ip = request.client.host if request.client else 'local'
        timestamp = datetime.now(timezone.utc)
        cutoff = (timestamp-timedelta(minutes=10)).isoformat()
        ip_cutoff = (timestamp-timedelta(minutes=1)).isoformat()
        account_hash, ip_hash = token_hash(data.email.lower()), token_hash(ip)
        # A reserva é persistida antes da verificação da password e não é apagada
        # por um login bem-sucedido noutra conta. A transação coordena processos.
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_attempts WHERE attempted_at<?', (cutoff,))
            account_count = db.execute('SELECT count(*) FROM login_attempts WHERE account_hash=? AND succeeded=0 AND attempted_at>=?', (account_hash,cutoff)).fetchone()[0]
            ip_count = db.execute('SELECT count(*) FROM login_attempts WHERE ip_hash=? AND attempted_at>=?', (ip_hash,ip_cutoff)).fetchone()[0]
            limited = account_count >= 8 or ip_count >= 30
            if limited:
                audit(db, 'Autenticação', 'session.rate_limited', 'login', 'Limite de tentativas atingido.')
            else:
                attempt_id = db.execute('INSERT INTO login_attempts(ip_hash,account_hash,attempted_at) VALUES(?,?,?)',
                                        (ip_hash,account_hash,timestamp.isoformat())).lastrowid
        if limited:
            raise HTTPException(429, 'Demasiadas tentativas. Tenta novamente mais tarde.', headers={'Retry-After': '600'})
        with database(path) as db:
            user = db.execute('SELECT * FROM users WHERE email=? AND active=1', (data.email.lower(),)).fetchone()
            valid = check_password(data.password, user['password_hash'] if user else dummy_password_hash)
        if not user or not valid:
            with database(path) as db:
                audit(db, 'Autenticação', 'session.failed', 'login', 'Credenciais inválidas.')
            raise HTTPException(401, 'Email ou palavra-passe incorretos.')
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            live = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
            if not live['active'] or live['password_hash'] != user['password_hash']:
                raise HTTPException(401, 'Email ou palavra-passe incorretos.')
            user = live
            db.execute('UPDATE login_attempts SET succeeded=1 WHERE id=?', (attempt_id,))
            token = secrets.token_urlsafe(32)
            old = request.cookies.get('nexo_session')
            if old:
                db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(old),))
            db.execute('DELETE FROM sessions WHERE expires_at<=?', (now(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?)',
                       (token_hash(token), user['id'], (datetime.now(timezone.utc)+timedelta(hours=8)).isoformat()))
            audit(db, user['name'], 'session.login', f'user:{user["id"]}')
        response.set_cookie('nexo_session', token, httponly=True, samesite='strict', max_age=28800,
                            secure=secure_cookie)
        return {k: user[k] for k in ('id', 'name', 'email', 'role','must_change_password')}

    @app.post('/api/logout')
    def logout(request: Request, response: Response, user=Depends(current_user)):
        with database(path) as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(request.cookies.get('nexo_session', '')),))
            audit(db, user['name'], 'session.logout', f'user:{user["id"]}')
        response.delete_cookie('nexo_session', secure=secure_cookie, httponly=True, samesite='strict')
        return {'ok': True}

    @app.get('/api/me')
    def me(user=Depends(current_user)):
        return user

    @app.get('/api/users')
    def users(user=Depends(current_user)):
        with database(path) as db:
            return [dict(r) for r in db.execute('SELECT id,name,role,active,must_change_password FROM users ORDER BY name')]

    def service_list(db):
        services = []
        enterprise_binding = enterprise_monitoring.binding(db)
        since = (datetime.now(timezone.utc)-timedelta(hours=24)).isoformat()
        stale = (datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
        for row in db.execute('SELECT * FROM services ORDER BY id'):
            service = dict(row)
            target = db.execute('SELECT * FROM telemetry_targets WHERE service_id=?', (row['id'],)).fetchone()
            is_enterprise = bool(enterprise_binding and enterprise_binding['service_id']==row['id'])
            enterprise_enabled = is_enterprise and enterprise_binding['enabled'] and enterprise_binding['configured'] and bool(enterprise_client.url)
            service['enterprise_monitoring'] = {'enabled':bool(enterprise_enabled)} if is_enterprise else None
            service['telemetry_source'] = 'enterprise' if is_enterprise else 'prometheus' if target else 'manual'
            service['monitoring'] = {**dict(target), 'approved': target['target_url'] in monitoring.allowed_urls()} if target else None
            service['log_scope'] = logs.binding(target) if loki_url else None
            service['logs_available'] = service['log_scope'] is not None
            counts = db.execute('SELECT COUNT(*),SUM(available) FROM observations WHERE service_id=? AND observed_at>=?',(row['id'],since)).fetchone()
            recent = [dict(r) for r in db.execute('''SELECT * FROM observations WHERE service_id=? AND observed_at>=?
                ORDER BY observed_at DESC,id DESC LIMIT 48''', (row['id'], since))]
            latest = recent[0] if recent else None
            service['dependencies'] = [r[0] for r in db.execute('SELECT depends_on_id FROM dependencies WHERE service_id=?', (row['id'],))]
            service['sample_count'] = counts[0]
            service['availability'] = round(counts[1]/counts[0]*100, 3) if counts[0] else None
            service['latest'] = latest
            cutoff = ((datetime.now(timezone.utc)-timedelta(seconds=telemetry.FRESH_SECONDS)).isoformat()
                      if latest and latest['source'] in ('prometheus','enterprise-api') else stale)
            service['status'] = ('unknown' if (is_enterprise and (not enterprise_enabled or not latest or latest['observed_at']<enterprise_binding['updated_at'])) or (target and (not target['enabled'] or target['target_url'] not in monitoring.allowed_urls() or not latest or latest['observed_at'] < target['updated_at'])) or not latest or latest['observed_at'] < cutoff else
                                 'down' if not latest['available'] else
                                 'degraded' if latest['latency_ms'] > row['slo_latency_ms'] else 'healthy')
            service['history'] = list(reversed(recent))
            services.append(service)
        return services

    @app.get('/api/services')
    def services(user=Depends(current_user)):
        with database(path) as db:
            return service_list(db)

    @app.post('/api/services', status_code=201)
    def create_service(data: ServiceInput, user=Depends(admin)):
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            validate_dependencies(db, None, data.dependencies)
            try:
                cursor = db.execute('''INSERT INTO services(name,team,description,criticality,slo_availability,slo_latency_ms,slo_latency_percent,created_at)
                    VALUES(?,?,?,?,?,?,?,?)''', (data.name, data.team, data.description, data.criticality,
                                               data.slo_availability, data.slo_latency_ms, data.slo_latency_percent, now()))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Já existe um serviço com esse nome.')
            sid = cursor.lastrowid
            db.executemany('INSERT INTO dependencies VALUES(?,?)', [(sid, d) for d in set(data.dependencies)])
            slo.record_policy(db,sid,user['name'])
            audit(db, user['name'], 'service.created', f'service:{sid}', data.name)
            return require(db, 'services', sid)

    @app.put('/api/services/{sid}')
    def edit_service(sid: int, data: ServiceInput, user=Depends(admin)):
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            old = require(db,'services',sid)
            old_dependencies = {r[0] for r in db.execute('SELECT depends_on_id FROM dependencies WHERE service_id=?',(sid,))}
            validate_dependencies(db,sid,data.dependencies)
            try:
                db.execute('UPDATE services SET name=?,team=?,description=?,criticality=?,slo_availability=?,slo_latency_ms=?,slo_latency_percent=? WHERE id=?',
                           (data.name,data.team,data.description,data.criticality,data.slo_availability,data.slo_latency_ms,data.slo_latency_percent,sid))
            except sqlite3.IntegrityError:
                raise HTTPException(409,'Já existe um serviço com esse nome.')
            db.execute('DELETE FROM dependencies WHERE service_id=?',(sid,))
            db.executemany('INSERT INTO dependencies VALUES(?,?)',[(sid,d) for d in set(data.dependencies)])
            changed = [key for key in ('name','team','description','criticality','slo_availability','slo_latency_ms','slo_latency_percent') if old[key]!=getattr(data,key)]
            if old_dependencies != set(data.dependencies):
                changed.append('dependencies')
            if changed:
                audit(db,user['name'],'service.updated',f'service:{sid}','Campos alterados: '+', '.join(changed))
                for incident in db.execute("SELECT id FROM incidents WHERE service_id=? AND status NOT IN ('resolved','closed')",(sid,)):
                    event(db,incident['id'],user['name'],'Inventário atualizado','Campos alterados: '+', '.join(changed))
            if old['slo_latency_ms'] != data.slo_latency_ms:
                enterprise_monitoring.touch(db,sid)
                # A changed threshold requires fresh samples; old observations remain intact.
                db.execute('UPDATE telemetry_targets SET updated_at=? WHERE service_id=?',(now(),sid))
            if any(key in changed for key in ('slo_availability','slo_latency_ms','slo_latency_percent')):
                policy=slo.record_policy(db,sid,user['name'])
                audit(db,user['name'],'slo.policy.updated',f'service:{sid}',f'Versão {policy["version"]}')
            return require(db,'services',sid)

    @app.get('/api/incidents')
    def incidents(user=Depends(current_user)):
        with database(path) as db:
            return [dict(r) for r in db.execute('''SELECT i.*,s.name AS service_name,u.name AS assignee_name
                FROM incidents i JOIN services s ON s.id=i.service_id LEFT JOIN users u ON u.id=i.assignee_id
                ORDER BY CASE WHEN i.status IN ('resolved','closed') THEN 1 ELSE 0 END,i.severity,i.created_at DESC''')]

    @app.post('/api/incidents', status_code=201)
    def create_incident(data: IncidentInput, user=Depends(writer)):
        with database(path) as db:
            require(db, 'services', data.service_id)
            cursor = db.execute('''INSERT INTO incidents(service_id,title,description,severity,status,created_at)
                VALUES(?,?,?,?,'open',?)''', (data.service_id, data.title, data.description, data.severity, now()))
            iid = cursor.lastrowid
            event(db, iid, user['name'], 'Incidente criado', data.description)
            audit(db, user['name'], 'incident.created', f'incident:{iid}', data.title)
            return require(db, 'incidents', iid)

    incident_browse.routes(app, path, current_user)

    @app.get('/api/incidents/{iid}')
    def incident(iid: int, user=Depends(current_user)):
        with database(path) as db:
            db.execute('BEGIN')
            return dossier.incident_snapshot(db, iid)

    @app.get('/api/incidents/{iid}/export')
    def export_incident(iid: int, format: Literal['markdown','json','html']='markdown', user=Depends(current_user)):
        with database(path) as db:
            db.execute('BEGIN')
            report = dossier.build(db, iid)
        if format == 'html':
            return HTMLResponse(printable_dossier.render(report), headers={
                'Content-Disposition': f'inline; filename="nexo-incidente-{iid}.html"',
                'Content-Security-Policy': printable_dossier.CSP,
                'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
        content = dossier.markdown(report) if format == 'markdown' else json.dumps(report, ensure_ascii=False, indent=2)
        extension = 'md' if format == 'markdown' else 'json'
        return Response(content, media_type='text/markdown' if format == 'markdown' else 'application/json',
            headers={'Content-Disposition': f'attachment; filename="nexo-incidente-{iid}.{extension}"',
                     'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    @app.post('/api/incidents/{iid}/evidence', status_code=201)
    def preserve_evidence(iid: int, user=Depends(writer)):
        with database(path) as db:
            row = require(db, 'incidents', iid)
            if row['status'] == 'closed':
                raise HTTPException(409, 'O incidente está fechado.')
        # Query through the same bounded, fixed-target facade as the service view.
        snapshot = service_logs(row['service_id'], user)
        if not snapshot['entries']:
            raise HTTPException(409, 'Não existem logs nesta janela para preservar.')
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            if require(db, 'incidents', iid)['status'] == 'closed':
                raise HTTPException(409, 'O incidente está fechado.')
            if db.execute('SELECT count(*) FROM incident_evidence WHERE incident_id=?', (iid,)).fetchone()[0] >= 20:
                raise HTTPException(409, 'Limite de 20 recolhas de evidência atingido para este caso.')
            stamp = now()
            cursor = db.execute('INSERT INTO incident_evidence(incident_id,source,captured_at,actor,payload) VALUES(?,?,?,?,?)',
                                (iid, 'loki', stamp, user['name'], json.dumps(snapshot)))
            event(db, iid, user['name'], 'Logs preservados', f'Evidência {cursor.lastrowid}: {len(snapshot["entries"])} pedidos HTTP. Janela de 15 minutos no momento da recolha.')
            audit(db, user['name'], 'incident.evidence.saved', f'incident:{iid}', str(cursor.lastrowid))
            return {'id': cursor.lastrowid, 'captured_at': stamp}

    @app.patch('/api/incidents/{iid}')
    def update_incident(iid: int, data: IncidentUpdate, user=Depends(writer)):
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = require(db, 'incidents', iid)
            check_revision(row, data.expected_revision)
            if NEXT.get(row['status']) != data.status:
                raise HTTPException(409, 'Transição inválida. Segue a ordem do ciclo de incidente.')
            if data.status == 'acknowledged' and not row['assignee_id']:
                raise HTTPException(422, 'Atribui um responsável antes de reconhecer o incidente.')
            if data.status == 'resolved' and len(data.note) < 10:
                raise HTTPException(422, 'Descreve a resolução com pelo menos 10 caracteres.')
            if data.status == 'resolved' and row['source'] in ('prometheus-alert','enterprise-alert'):
                if not alerts.recovered(db,row['service_id'],datetime.now(timezone.utc).timestamp()):
                    raise HTTPException(409, 'Aguarda as sondagens recentes de recuperação exigidas pela regra antes de resolver o incidente.')
            if data.status == 'closed' and (len(data.root_cause) < 10 or len(data.prevention) < 10):
                raise HTTPException(422, 'O fecho exige causa raiz e prevenção com pelo menos 10 caracteres cada.')
            timestamp = now()
            db.execute('UPDATE incidents SET status=? WHERE id=?', (data.status, iid))
            date_column = {'acknowledged': 'acknowledged_at', 'resolved': 'resolved_at', 'closed': 'closed_at'}.get(data.status)
            if date_column:
                db.execute(f'UPDATE incidents SET {date_column}=? WHERE id=?', (timestamp, iid))
            if data.status == 'resolved':
                db.execute('UPDATE incidents SET resolution=? WHERE id=?', (data.note, iid))
            if data.status == 'closed':
                db.execute('UPDATE incidents SET root_cause=?,prevention=?,runbook=? WHERE id=?',
                           (data.root_cause, data.prevention, data.runbook, iid))
            event(db, iid, user['name'], STATES[data.status], data.note, timestamp)
            audit(db, user['name'], 'incident.transition', f'incident:{iid}', f'{row["status"]} -> {data.status}')
            return require(db, 'incidents', iid)

    @app.post('/api/incidents/{iid}/assign')
    def assign(iid: int, data: Assignment, user=Depends(writer)):
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = require(db, 'incidents', iid)
            check_revision(row, data.expected_revision)
            if row['status'] in ('resolved', 'closed'):
                raise HTTPException(409, 'Este incidente já está resolvido.')
            assigned = require(db, 'users', data.user_id)
            if assigned['role'] == 'viewer':
                raise HTTPException(422, 'Um leitor não pode ser responsável por um incidente.')
            if not assigned['active'] or assigned['must_change_password']:
                raise HTTPException(422, 'O responsável precisa de uma conta ativa com a palavra-passe inicial já alterada.')
            db.execute('UPDATE incidents SET assignee_id=? WHERE id=?', (data.user_id, iid))
            event(db, iid, user['name'], 'Responsável atribuído', assigned['name'])
            audit(db, user['name'], 'incident.assigned', f'incident:{iid}', assigned['name'])
        return {'ok': True}

    @app.post('/api/incidents/{iid}/comments', status_code=201)
    def comment(iid: int, data: Comment, user=Depends(writer)):
        with database(path) as db:
            row = require(db, 'incidents', iid)
            if row['status'] == 'closed':
                raise HTTPException(409, 'O incidente está fechado.')
            event(db, iid, user['name'], 'Nota de investigação', data.note)
            audit(db, user['name'], 'incident.comment', f'incident:{iid}', data.note)
        return {'ok': True}

    follow_ups.routes(app, path, writer, require)
    incident_knowledge.routes(app, path, writer, require)
    incident_impact.routes(app, path, writer, require, service_list)

    @app.get('/api/knowledge')
    def knowledge(q: str = Query(default='', max_length=2000),
                  method: Literal['tfidf','bm25','semantic','hybrid']='hybrid',
                  scope: Literal['all','examples','operational']='all',
                  service_id: int | None = Query(default=None,ge=1),
                  exclude_id: int | None = Query(default=None,ge=1), user=Depends(current_user)):
        rows,total = knowledge_corpus(path,service_id,scope,exclude_id)
        return {**knowledge_engine.search(q,rows,method),'eligible_total':total,'corpus_limit':100,
                'scope':scope,'service_id':service_id}

    @app.get('/api/summary')
    def summary(user=Depends(current_user)):
        with database(path) as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM incidents')]
            def mean_elapsed(end):
                values = [(datetime.fromisoformat(r[end])-datetime.fromisoformat(r['created_at'])).total_seconds()
                          for r in rows if r[end]]
                return {'seconds': round(sum(values)/len(values), 1) if values else None, 'count': len(values)}
            return {'services': service_list(db), 'active_incidents': sum(r['status'] not in ('resolved', 'closed') for r in rows),
                    'critical_incidents': sum(r['severity'] == 'P1' and r['status'] not in ('resolved', 'closed') for r in rows),
                    'mtta': mean_elapsed('acknowledged_at'), 'mttr': mean_elapsed('resolved_at'),
                    'demo': demo_mode, 'generated_at': now()}

    audit_log.routes(app, path, admin)

    @app.get('/api/audit')
    def recent_audit_log(user=Depends(admin)):
        with database(path) as db:
            return [dict(r) for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 200')]

    @app.post('/api/demo/scenario')
    def scenario(data: Scenario, user=Depends(writer)):
        if not demo_mode:
            raise HTTPException(404, 'Demonstração desativada.')
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            service = require(db, 'services', data.service_id)
            enterprise_binding=enterprise_monitoring.binding(db)
            if (enterprise_binding and enterprise_binding['service_id']==data.service_id) or db.execute('SELECT 1 FROM telemetry_targets WHERE service_id=?', (data.service_id,)).fetchone():
                raise HTTPException(409, 'Este serviço usa sondagens reais. O simulador só altera os exemplos sintéticos.')
            available = int(data.kind != 'outage')
            latency = service['slo_latency_ms']*3 if data.kind == 'latency' else 0 if data.kind == 'outage' else min(50, service['slo_latency_ms'])
            db.execute('INSERT INTO observations(service_id,available,latency_ms,source,observed_at) VALUES(?,?,?,?,?)',
                       (data.service_id, available, latency, 'demo', now()))
            iid = None
            if data.kind != 'recovery':
                active = db.execute("SELECT id FROM incidents WHERE service_id=? AND source='demo-alert' AND status NOT IN ('resolved','closed')",
                                    (data.service_id,)).fetchone()
                if active:
                    iid = active['id']
                    event(db, iid, 'Simulador', 'Alerta repetido', 'Alerta agrupado no incidente existente.')
                else:
                    title = ('Serviço indisponível' if not available else 'Latência acima do objetivo') + ' · ' + service['name']
                    description = ('Erros HTTP 503: serviço indisponível.' if not available else
                                   f'Tempo de resposta de {latency} ms, superior ao SLO de {service["slo_latency_ms"]} ms.')
                    cursor = db.execute('''INSERT INTO incidents(service_id,title,description,severity,status,created_at,source)
                        VALUES(?,?,?,?,'open',?,'demo-alert')''',
                        (data.service_id, title, description, 'P1' if not available else 'P2', now()))
                    iid = cursor.lastrowid
                    event(db, iid, 'Simulador', 'Alerta de demonstração', description)
                    audit(db, 'Simulador', 'incident.created', f'incident:{iid}', title)
            audit(db, user['name'], 'demo.scenario', f'service:{data.service_id}', data.kind)
            return {'incident_id': iid, 'kind': data.kind, 'source': 'demo'}

    app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')

    @app.get('/', include_in_schema=False)
    def index():
        asset_tag = VERSION + '-' + hashlib.sha256((ROOT / 'web/app.js').read_bytes() + (ROOT / 'web/style.css').read_bytes()).hexdigest()[:12]
        html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8').replace('__ASSET_VERSION__', asset_tag)
        return HTMLResponse(html, headers={'Cache-Control': 'no-store'})

    app.add_middleware(BodyLimitMiddleware, max_bytes=65536)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts, www_redirect=False)
    return app


app = create_app()
