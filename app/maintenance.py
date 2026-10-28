"""Local, offline database promotion with a durable recovery journal. No HTTP route."""
import argparse
import base64
from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import uuid

from .db import audit, now
from . import recovery, monitoring

HISTORY = ('users', 'services', 'dependencies', 'incidents', 'timeline',
           'incident_evidence', 'alert_rules', 'alert_rule_history',
           'incident_alert_context', 'incident_escalations', 'service_slo_policies')
PENDING = {'prepared', 'switching', 'rolling_back'}


def sync_dir(path):
    if os.name == 'posix':
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def write_json(path, value):
    recovery.plain_path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.partial')
    with temp.open('x', encoding='utf-8') as stream:
        os.chmod(temp, 0o600)
        json.dump(value, stream, ensure_ascii=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)
    sync_dir(path.parent)


def read_json(path):
    recovery.plain_path(path)
    if path.stat().st_size > 65536:
        raise recovery.RecoveryError('Diário de manutenção inválido.')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise recovery.RecoveryError('Diário de manutenção inválido.')
    return value


def fingerprint(path):
    path = recovery.plain_path(path)
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
        db.execute('BEGIN')
        if db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0] > recovery.MAX_DB:
            raise recovery.RecoveryError('Base acima do limite de manutenção de 32 MiB.')
        result = recovery.inspect_db(db)
        result['history_sha256'] = {}
        for table in HISTORY:
            rows = db.execute('SELECT * FROM ' + table).fetchall()
            encoded = json.dumps(sorted(rows, key=lambda r: json.dumps(r)),
                                 ensure_ascii=True, separators=(',', ':')).encode()
            result['history_sha256'][table] = hashlib.sha256(encoded).hexdigest()
        result['enabled_targets'] = db.execute('SELECT count(*) FROM telemetry_targets WHERE enabled=1').fetchone()[0]
        return result


def require_ready(path):
    """Fail closed after an interrupted swap, before seed, workers or HTTP startup."""
    path = Path(path).absolute()
    state_path = recovery.plain_path(path.parent / 'maintenance' / 'state.json')
    if path.name == 'nexo.db' and state_path.exists():
        state = read_json(state_path)
        if state.get('phase') not in {'staged', 'promoted', 'committed', 'rolled_back', 'cancelled'}:
            raise RuntimeError('Manutenção incompleta. Executa a reversão local antes de iniciar o portal.')


def blocks_writes(path):
    path = Path(path).absolute()
    if path.name != 'nexo.db':
        return False
    state_path = recovery.plain_path(path.parent / 'maintenance' / 'state.json')
    if not state_path.exists():
        return False
    state = read_json(state_path)
    phase = state.get('phase')
    return phase not in {'staged', 'promoted', 'committed', 'rolled_back', 'cancelled'} or (phase == 'promoted' and not state.get('verified'))


class Maintenance:
    def __init__(self, root, company_id=None):
        self.root = recovery.plain_path(root)
        if not self.root.is_dir():
            raise recovery.RecoveryError('Diretório de dados inexistente.')
        self.live = self.root / 'nexo.db'
        self.company_id = company_id
        self.check_company(self.live)
        self.folder = recovery.plain_path(self.root / 'maintenance')
        self.folder.mkdir(mode=0o700, exist_ok=True)
        self.state_path = self.folder / 'state.json'

    def check_company(self, path):
        if self.company_id is not None:
            with closing(sqlite3.connect(recovery.plain_path(path).as_uri() + '?mode=ro', uri=True)) as db:
                recovery.check_company(db, self.company_id)

    @contextmanager
    def lock(self):
        # Cross-process helper lock. The web server is stopped by the orchestrator.
        path = recovery.plain_path(self.folder / 'operation.lock')
        with path.open('a+b') as stream:
            os.chmod(path, 0o600)
            if os.name != 'posix':
                import msvcrt
                stream.seek(0)
                if stream.read(1) == b'':
                    stream.write(b'0'); stream.flush()
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    yield
                finally:
                    stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    yield
                finally:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    def state(self):
        if not self.state_path.exists():
            return {'phase': 'none'}
        state = read_json(self.state_path)
        if state.get('company_id') != self.company_id:
            raise recovery.RecoveryError('O diário não corresponde à instalação selecionada.')
        if not re.fullmatch(r'[a-f0-9]{32}', state.get('generation', '')):
            raise recovery.RecoveryError('Identificador de manutenção inválido.')
        if state.get('phase') not in {'staged', 'promoted', 'committed', 'rolled_back', 'cancelled', *PENDING}:
            raise recovery.RecoveryError('Fase de manutenção inválida.')
        return state

    def generation(self, state):
        return recovery.plain_path(self.folder / state['generation'])

    def save(self, state, phase):
        state = {**state, 'phase': phase, 'updated_at': now()}
        write_json(self.generation(state) / 'journal.json', state)
        write_json(self.state_path, state)
        return state

    def stage(self, archive, key):
        with self.lock():
            self.check_company(self.live)
            if self.state()['phase'] not in {'none', 'committed', 'rolled_back', 'cancelled'}:
                raise recovery.RecoveryError('Conclui ou reverte a manutenção anterior antes de preparar outra.')
            generation = uuid.uuid4().hex
            folder = self.folder / generation
            folder.mkdir(mode=0o700)
            with tempfile.TemporaryDirectory(prefix='nexo-approved-targets-') as temp:
                snapshot, _ = recovery.checked_snapshot(archive, key, temp, self.company_id)
                with closing(sqlite3.connect(snapshot)) as db:
                    resume_targets = [{'service_id': sid, 'target_url': url} for sid, url in
                        db.execute('SELECT service_id,target_url FROM telemetry_targets WHERE enabled=1')]
            result = recovery.restore(archive, key, folder / 'candidate', self.company_id)
            candidate = folder / 'candidate' / 'nexo.db'
            state = {'generation': generation, 'created_at': now(), 'company_id': self.company_id,
                     'archive_sha256': result['archive_sha256'],
                     'resume_targets': resume_targets,
                     'candidate_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest(),
                     'candidate': fingerprint(candidate)}
            self.save(state, 'staged')
            return self.state()

    def offline(self):
        """Checkpoint before replacing a database; refuse existing readers/transactions."""
        recovery.plain_path(self.live)
        with closing(sqlite3.connect(self.live.as_uri() + '?mode=rw', uri=True, timeout=2)) as db:
            recovery.inspect_db(db)
            # DELETE mode checkpoints WAL and refuses a concurrent reader holding it.
            if db.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
                raise recovery.RecoveryError('A base ainda está em utilização.')
            db.execute('BEGIN EXCLUSIVE')
            db.rollback()
        for suffix in ('-wal', '-shm', '-journal'):
            sidecar = recovery.plain_path(str(self.live) + suffix)
            if sidecar.exists():
                raise recovery.RecoveryError('Ainda existem ficheiros transitórios. Não será feita a troca.')

    def copy(self, source, destination, action=None):
        source, destination = recovery.plain_path(source), recovery.plain_path(destination)
        with destination.open('xb'):
            os.chmod(destination, 0o600)
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src, \
             closing(sqlite3.connect(destination)) as dst:
            src.backup(dst)
            if action:
                dst.execute('PRAGMA secure_delete=ON')
                dst.execute('DELETE FROM sessions')
                if self.company_id is not None and action == 'maintenance.rolled_back':
                    from .enterprise_monitoring import pause_for_restore
                    pause_for_restore(dst)
                    dst.execute('UPDATE telemetry_targets SET enabled=0,updated_at=?', (now(),))
                    dst.execute('DELETE FROM alert_states')
                audit(dst, 'Manutenção local', action, 'database', str(source.relative_to(self.root)))
                dst.commit()
                dst.execute('VACUUM')
            recovery.inspect_db(dst)
        with destination.open('r+b') as stream:
            os.fsync(stream.fileno())
        sync_dir(destination.parent)

    def install(self, source, action):
        # New copy each time: immutable source and original rollback image survive failures.
        apply = self.folder / ('apply-' + uuid.uuid4().hex + '.db')
        self.copy(source, apply, action)
        os.replace(apply, self.live)
        sync_dir(self.root)

    def promote(self):
        with self.lock():
            state = self.state()
            if state['phase'] != 'staged':
                raise recovery.RecoveryError('É necessária uma cópia preparada para promover.')
            folder = self.generation(state)
            candidate = recovery.plain_path(folder / 'candidate' / 'nexo.db')
            if hashlib.sha256(candidate.read_bytes()).hexdigest() != state['candidate_sha256']:
                raise recovery.RecoveryError('A cópia preparada foi alterada; promoção recusada.')
            fingerprint(candidate)
            self.check_company(candidate)
            self.check_company(self.live)
            self.offline()
            # The state remains staged if the checkpoint fails; the live database is intact.
            self.copy(self.live, folder / 'rollback.db', 'maintenance.rollback.checkpoint')
            state['rollback'] = fingerprint(folder / 'rollback.db')
            state['rollback_sha256'] = hashlib.sha256((folder / 'rollback.db').read_bytes()).hexdigest()
            state = self.save(state, 'prepared')
            state = self.save(state, 'switching')
            self.install(candidate, 'maintenance.promoted')
            state['verified'] = False
            return self.save(state, 'promoted')

    def rollback(self):
        with self.lock():
            state = self.state()
            if state['phase'] == 'staged':
                return self.save(state, 'cancelled')
            if state['phase'] == 'rolled_back':
                return state
            if state['phase'] not in {'promoted', 'committed', *PENDING}:
                raise recovery.RecoveryError('Não existe uma promoção para reverter.')
            folder = self.generation(state)
            rollback = folder / 'rollback.db'
            self.check_company(rollback)
            if hashlib.sha256(recovery.plain_path(rollback).read_bytes()).hexdigest() != state['rollback_sha256']:
                raise recovery.RecoveryError('O ponto de retorno foi alterado.')
            if fingerprint(rollback)['history_sha256'] != state['rollback']['history_sha256']:
                raise recovery.RecoveryError('A base de retorno não corresponde ao ponto guardado.')
            self.offline()
            # Preserve writes made since promotion instead of silently losing the candidate.
            preserved = folder / ('before-rollback-' + uuid.uuid4().hex + '.db')
            self.copy(self.live, preserved, 'maintenance.before_rollback')
            state = self.save(state, 'rolling_back')
            self.install(rollback, 'maintenance.rolled_back')
            return self.save(state, 'rolled_back')

    def check(self):
        state = self.state()
        self.check_company(self.live)
        if state['phase'] not in {'promoted', 'committed', 'rolled_back'}:
            raise recovery.RecoveryError('A troca ainda não está concluída.')
        expected = state['candidate'] if state['phase'] in {'promoted', 'committed'} else state['rollback']
        current = fingerprint(self.live)
        if current['history_sha256'] != expected['history_sha256']:
            raise recovery.RecoveryError('O histórico ativo não corresponde ao esperado.')
        promoted = state['phase'] in {'promoted', 'committed'}
        action = 'maintenance.promoted' if promoted else 'maintenance.rolled_back'
        source = self.generation(state) / ('candidate/nexo.db' if promoted else 'rollback.db')
        with closing(sqlite3.connect(self.live.as_uri() + '?mode=ro', uri=True)) as db:
            audited = db.execute('SELECT count(*) FROM audit WHERE action=? AND detail=?',
                                 (action, str(source.relative_to(self.root)))).fetchone()[0] > 0
        if not audited:
            raise recovery.RecoveryError('Não foi confirmado o registo de auditoria desta geração.')
        return {'phase': state['phase'], 'historical_tables_match': list(HISTORY),
                'tables': current['tables'], 'enabled_targets': current['enabled_targets'],
                'generation_audit_verified': True}

    def resume(self):
        with self.lock():
            state = self.state()
            if state['phase'] not in {'promoted', 'committed'}:
                raise recovery.RecoveryError('A retoma exige uma base promovida.')
            if not state.get('verified'):
                raise recovery.RecoveryError('Verifica o arranque e o histórico antes de retomar.')
            allowed = monitoring.allowed_urls()
            with closing(sqlite3.connect(self.live.as_uri() + '?mode=rw', uri=True, timeout=5)) as db:
                db.execute('BEGIN IMMEDIATE')
                wanted = {t['service_id']: t['target_url'] for t in state['resume_targets']}
                paused = [(sid, url) for sid, url in db.execute(
                    'SELECT service_id,target_url FROM telemetry_targets WHERE enabled=0') if sid in wanted]
                if any(url != wanted[sid] for sid, url in paused):
                    raise recovery.RecoveryError('O endereço de uma ligação foi alterado.')
                if any(url not in allowed for _, url in paused):
                    raise recovery.RecoveryError('Existem endereços fora da política atual. Revê as ligações antes de retomar.')
                for sid, _ in paused:
                    db.execute('UPDATE telemetry_targets SET enabled=1,updated_at=? WHERE service_id=?', (now(), sid))
                    db.execute('DELETE FROM alert_states WHERE service_id=?', (sid,))
                audit(db, 'Manutenção local', 'maintenance.monitoring.resumed', 'database', str(len(paused)))
                db.commit()
            return {'resumed_targets': len(paused), 'fresh_probes_required': True}

    def commit(self):
        with self.lock():
            state = self.state()
            if state['phase'] != 'promoted' or not state.get('verified'):
                raise recovery.RecoveryError('Só uma promoção concluída pode ser confirmada.')
            fingerprint(self.live)
            return self.save(state, 'committed')

    def verify(self):
        with self.lock():
            result = self.check()
            state = self.state()
            if state['phase'] == 'promoted':
                state['verified'] = True
                self.save(state, 'promoted')
            return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['stage', 'promote', 'rollback', 'status', 'check', 'verify', 'resume', 'commit'])
    parser.add_argument('--company',help='Expected customer installation identity.')
    args = parser.parse_args()
    try:
        if os.getenv('NEXO_MAINTENANCE') != '1' or os.getenv('DATABASE_PATH') != '/app/data/nexo.db':
            raise recovery.RecoveryError('Comando reservado ao procedimento local de manutenção.')
        policy = os.getenv('NEXO_MAINTENANCE_POLICY_B64', '')
        if len(policy) > 65536:
            raise recovery.RecoveryError('Política acima do limite.')
        os.environ['MONITORING_ALLOWED_URLS'] = base64.b64decode(policy, validate=True).decode('utf-8')
        monitoring.allowed_urls()
        manager = Maintenance('/app/data', args.company)
        if args.action == 'stage':
            raw = sys.stdin.buffer.read(recovery.MAX_INPUT + 1)
            if len(raw) > recovery.MAX_INPUT:
                raise recovery.RecoveryError('Entrada acima do limite.')
            payload = json.loads(raw)
            result = manager.stage(base64.b64decode(payload['archive'], validate=True),
                                   base64.b64decode(payload['key'], validate=True))
        else:
            result = getattr(manager, {'status': 'state'}.get(args.action, args.action))()
        print(json.dumps(result, ensure_ascii=True))
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
        print('Manutenção recusada. Verifica a fase, a cópia, as ligações e se o portal está parado. Os pontos de retorno foram conservados.', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
