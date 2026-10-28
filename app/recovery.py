"""Local CLI only: consistent SQLite snapshots, authenticated encryption, new-target restore.

Secrets travel through stdin, never command-line arguments or HTTP. No live restore.
"""
import argparse
import base64
from contextlib import closing
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import struct
import sys
import tempfile
import time

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .db import audit, initialize, now
from .knowledge import Knowledge
from .version import VERSION

MAGIC = b'NEXOBAK1'
MAX_DB = 32 * 1024 * 1024
MAX_ARCHIVE = MAX_DB + 65536 + 64
MAX_INPUT = 48 * 1024 * 1024


class RecoveryError(ValueError):
    pass


def plain_path(path):
    """Reject existing links/junctions, including parents, before resolving a target."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise RecoveryError('Não são aceites ligações simbólicas ou junctions.')
    return path


def schema(db):
    # Legacy migrations changed indentation, not structure. Preserve quoted literals.
    import re
    def normalize(sql):
        return re.sub(r"'(?:(?:'')|[^'])*'|\s+",lambda m:m[0] if m[0].startswith("'") else ' ',sql).strip() if sql else sql
    return [(kind,name,table,normalize(sql)) for kind,name,table,sql in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]


def schema_hash(items):
    return hashlib.sha256(json.dumps(items,separators=(',',':')).encode()).hexdigest()


@lru_cache(maxsize=1)
def expected_schema():
    with tempfile.TemporaryDirectory(prefix='nexo-schema-') as folder:
        path = str(Path(folder)/'expected.db')
        initialize(path)
        Knowledge(path).initialize()
        with closing(sqlite3.connect(path)) as db:
            return schema(db)


def inspect_db(db):
    db.execute('PRAGMA trusted_schema=OFF')
    actual = schema(db)
    expected = expected_schema()
    # Semantic cache is optional in older/text-only installations of this schema.
    if actual != expected and actual != [r for r in expected if r[1]!='knowledge_vectors']:
        raise RecoveryError('Esquema incompatível com esta versão da aplicação.')
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise RecoveryError('A base não passou a verificação de integridade.')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise RecoveryError('A base contém referências inválidas.')
    counts = {}
    for kind,name,_,_ in actual:
        if kind=='table':
            counts[name] = db.execute('SELECT COUNT(*) FROM "'+name.replace('"','""')+'"').fetchone()[0]
    return {'schema_sha256':schema_hash(actual),'tables':counts}


def check_key(key):
    if not isinstance(key,bytes) or len(key)!=32:
        raise RecoveryError('É necessária uma chave aleatória de 32 bytes.')


def check_company(db, company_id):
    if company_id is None:
        return
    import re
    if not isinstance(company_id,str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,23}',company_id):
        raise RecoveryError('Identidade de instalação inválida.')
    row = db.execute("SELECT value FROM settings WHERE key='enterprise_monitoring_binding'").fetchone()
    try:
        actual = json.loads(row[0])['company_id'] if row else None
    except (ValueError,KeyError,TypeError):
        raise RecoveryError('A base não identifica a instalação esperada.') from None
    if actual != company_id:
        raise RecoveryError('A base pertence a outra instalação ou não tem identidade empresarial.')


def create(database,key,company_id=None):
    check_key(key)
    source = plain_path(database)
    if not source.is_file():
        raise RecoveryError('Base de origem inexistente.')
    started = now()
    deadline = time.monotonic()+20
    with tempfile.TemporaryDirectory(prefix='nexo-snapshot-') as folder:
        target = Path(folder)/'snapshot.db'
        def progress(status,remaining,total):
            if time.monotonic()>deadline:
                raise RecoveryError('Snapshot excedeu o prazo de 20 segundos.')
            if total*page_size > MAX_DB:
                raise RecoveryError('Base acima do limite de 32 MiB desta entrega.')
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=5)) as live, closing(sqlite3.connect(target)) as snapshot:
            page_size=live.execute('PRAGMA page_size').fetchone()[0]
            if live.execute('PRAGMA page_count').fetchone()[0]*page_size>MAX_DB:
                raise RecoveryError('Base acima do limite de 32 MiB desta entrega.')
            live.backup(snapshot,pages=128,progress=progress,sleep=.05)
            snapshot.execute('PRAGMA journal_mode=DELETE')
            inspect_db(snapshot)
            check_company(snapshot,company_id)
            snapshot.execute('PRAGMA secure_delete=ON')
            snapshot.execute('DELETE FROM sessions')
            snapshot.commit()
            snapshot.execute('VACUUM')
            report = inspect_db(snapshot)
        raw = target.read_bytes()
        if len(raw)>MAX_DB:
            raise RecoveryError('Base acima do limite de 32 MiB desta entrega.')
    manifest = {'format':1,'app_version':VERSION,'started_at':started,'completed_at':now(),
                'database_sha256':hashlib.sha256(raw).hexdigest(),'database_bytes':len(raw),
                'sessions_removed':True,**report}
    if company_id is not None:
        manifest['installation_id'] = company_id
    metadata = json.dumps(manifest,separators=(',',':')).encode()
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(key).encrypt(nonce,struct.pack('!I',len(metadata))+metadata+raw,MAGIC)
    return MAGIC+nonce+encrypted, manifest


def decode(archive,key):
    check_key(key)
    if not isinstance(archive,bytes) or not 40<=len(archive)<=MAX_ARCHIVE or not archive.startswith(MAGIC):
        raise RecoveryError('Formato ou tamanho de cópia inválido.')
    try:
        payload = AESGCM(key).decrypt(archive[8:20],archive[20:],MAGIC)
    except InvalidTag:
        raise RecoveryError('Cópia alterada, danificada ou chave incorreta.') from None
    if len(payload)<4:
        raise RecoveryError('Conteúdo inválido.')
    size = struct.unpack('!I',payload[:4])[0]
    if not 1<=size<=65536 or size+4>=len(payload):
        raise RecoveryError('Manifesto inválido.')
    try:
        manifest = json.loads(payload[4:4+size])
    except (ValueError,UnicodeError):
        raise RecoveryError('Manifesto inválido.') from None
    raw = payload[4+size:]
    if not isinstance(manifest,dict) or manifest.get('format')!=1 or len(raw)>MAX_DB or manifest.get('database_bytes')!=len(raw) or manifest.get('database_sha256')!=hashlib.sha256(raw).hexdigest():
        raise RecoveryError('Conteúdo e manifesto não coincidem.')
    return raw,manifest


def checked_snapshot(archive,key,folder,company_id=None):
    raw,manifest = decode(archive,key)
    if company_id is not None and manifest.get('installation_id') != company_id:
        raise RecoveryError('A cópia não identifica a instalação esperada.')
    path = Path(folder)/'snapshot.db'
    with path.open('xb') as output:
        output.write(raw)
    with closing(sqlite3.connect(path)) as db:
        report = inspect_db(db)
        check_company(db,company_id)
    if any(report[k]!=manifest.get(k) for k in ('schema_sha256','tables')):
        raise RecoveryError('Contagens ou esquema não coincidem com o manifesto.')
    return path,manifest


def verify(archive,key,company_id=None):
    with tempfile.TemporaryDirectory(prefix='nexo-check-') as folder:
        _,manifest = checked_snapshot(archive,key,folder,company_id)
    return {**manifest,'archive_sha256':hashlib.sha256(archive).hexdigest(),'verified':True}


def restore(archive,key,destination,company_id=None):
    target = plain_path(destination)
    if target.exists() or not target.parent.is_dir():
        raise RecoveryError('O restauro exige uma pasta nova, num diretório existente.')
    with tempfile.TemporaryDirectory(prefix='nexo-restore-') as folder:
        snapshot,manifest = checked_snapshot(archive,key,folder,company_id)
        with closing(sqlite3.connect(snapshot)) as db:
            db.execute('PRAGMA secure_delete=ON')
            db.execute('DELETE FROM sessions')
            db.execute('UPDATE telemetry_targets SET enabled=0,updated_at=?',(now(),))
            from .enterprise_monitoring import pause_for_restore
            pause_for_restore(db)
            db.execute('DELETE FROM alert_states')
            audit(db,'Recuperação local','recovery.restored','database',hashlib.sha256(archive).hexdigest())
            db.commit()
            final = inspect_db(db)
        # No overwrite, no switch of DATABASE_PATH, no changes to the running volume.
        target.mkdir(mode=0o700)
        output = target/'nexo.db'
        created = False
        try:
            with output.open('xb') as handle:
                created = True
                os.chmod(output,0o600)
                handle.write(snapshot.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            if created:
                output.unlink()
            try:
                target.rmdir()
            except OSError:
                pass
            raise
    return {'restored':True,'path':str(output),'archive_sha256':hashlib.sha256(archive).hexdigest(),
            'snapshot_completed_at':manifest['completed_at'],'sessions_revoked':True,
            'monitoring_paused':True,**final}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['create','verify','restore'])
    parser.add_argument('--database')
    parser.add_argument('--destination')
    parser.add_argument('--company',help='Expected installation identity, for dedicated customer backups.')
    args = parser.parse_args()
    try:
        raw_input = sys.stdin.buffer.read(MAX_INPUT+1)
        if len(raw_input)>MAX_INPUT:
            raise RecoveryError('Entrada acima do limite.')
        payload = json.loads(raw_input)
        key = base64.b64decode(payload['key'],validate=True)
        if args.action=='create':
            if not args.database:
                raise RecoveryError('Falta a base de origem.')
            archive,report = create(args.database,key,args.company)
            result = {'archive':base64.b64encode(archive).decode(),'report':report}
        else:
            archive = base64.b64decode(payload['archive'],validate=True)
            if args.action=='restore' and not args.destination:
                raise RecoveryError('Falta o destino novo.')
            result = verify(archive,key,args.company) if args.action=='verify' else restore(archive,key,args.destination,args.company)
        print(json.dumps(result,ensure_ascii=True))
    except (RecoveryError,OSError,sqlite3.Error,ValueError,KeyError,TypeError):
        # Never echo stdin, decrypted bytes, keys, SQL rows or upstream exceptions.
        print('Não foi possível concluir. Confirma a chave, o ficheiro, o espaço, o limite de 32 MiB e um destino novo compatível.',file=sys.stderr)
        raise SystemExit(1)


if __name__=='__main__':
    main()
