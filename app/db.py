import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def database(path):
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with database(path) as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin','operator','viewer'))
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
            expires_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, team TEXT NOT NULL,
            description TEXT NOT NULL, criticality TEXT NOT NULL CHECK(criticality IN ('Alta','Média','Baixa')),
            slo_availability REAL NOT NULL, slo_latency_ms INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS dependencies (
            service_id INTEGER NOT NULL REFERENCES services(id),
            depends_on_id INTEGER NOT NULL REFERENCES services(id),
            PRIMARY KEY(service_id, depends_on_id), CHECK(service_id != depends_on_id)
        );
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY, service_id INTEGER NOT NULL REFERENCES services(id),
            available INTEGER NOT NULL CHECK(available IN (0,1)), latency_ms REAL NOT NULL,
            source TEXT NOT NULL, observed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS observations_time ON observations(service_id, observed_at);
        CREATE TABLE IF NOT EXISTS telemetry_targets (
            target_key TEXT PRIMARY KEY, service_id INTEGER UNIQUE NOT NULL REFERENCES services(id));
        CREATE UNIQUE INDEX IF NOT EXISTS unique_prometheus_sample
            ON observations(service_id,source,observed_at) WHERE source='prometheus';
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY, service_id INTEGER NOT NULL REFERENCES services(id),
            title TEXT NOT NULL, description TEXT NOT NULL, severity TEXT NOT NULL,
            status TEXT NOT NULL, assignee_id INTEGER REFERENCES users(id),
            created_at TEXT NOT NULL, acknowledged_at TEXT, resolved_at TEXT, closed_at TEXT,
            resolution TEXT NOT NULL DEFAULT '', root_cause TEXT NOT NULL DEFAULT '',
            prevention TEXT NOT NULL DEFAULT '', runbook TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'manual'
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_demo_alert ON incidents(service_id, source)
            WHERE source = 'demo-alert' AND status NOT IN ('resolved','closed');
        CREATE TABLE IF NOT EXISTS timeline (
            id INTEGER PRIMARY KEY, incident_id INTEGER NOT NULL REFERENCES incidents(id),
            actor TEXT NOT NULL, action TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_prometheus_alert ON incidents(service_id, source)
            WHERE source='prometheus-alert' AND status NOT IN ('resolved','closed');
        CREATE TABLE IF NOT EXISTS alert_states (
            service_id INTEGER PRIMARY KEY REFERENCES services(id),
            condition TEXT NOT NULL, last_sample TEXT NOT NULL,
            incident_id INTEGER REFERENCES incidents(id));
        CREATE TABLE IF NOT EXISTS incident_evidence (
            id INTEGER PRIMARY KEY, incident_id INTEGER NOT NULL REFERENCES incidents(id),
            source TEXT NOT NULL, captured_at TEXT NOT NULL, actor TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
            entity TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY, ip_hash TEXT NOT NULL, account_hash TEXT NOT NULL,
            attempted_at TEXT NOT NULL, succeeded INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS login_attempts_time ON login_attempts(attempted_at);
        CREATE TABLE IF NOT EXISTS password_change_attempts (
            id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), attempted_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS password_change_time ON password_change_attempts(user_id,attempted_at);
        CREATE TABLE IF NOT EXISTS alert_rules (
            service_id INTEGER PRIMARY KEY REFERENCES services(id), config TEXT NOT NULL,
            updated_at TEXT NOT NULL, version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS alert_rule_history (
            service_id INTEGER NOT NULL REFERENCES services(id), version INTEGER NOT NULL,
            config TEXT NOT NULL, changed_at TEXT NOT NULL, actor TEXT NOT NULL,
            PRIMARY KEY(service_id,version));
        CREATE TABLE IF NOT EXISTS incident_alert_context (
            incident_id INTEGER PRIMARY KEY REFERENCES incidents(id), config TEXT NOT NULL,
            rule_version INTEGER NOT NULL, detected_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS incident_escalations (
            incident_id INTEGER PRIMARY KEY REFERENCES incidents(id), escalated_at TEXT NOT NULL,
            from_severity TEXT NOT NULL, to_severity TEXT NOT NULL,
            deadline_seconds INTEGER NOT NULL, rule_version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS service_slo_policies (
            service_id INTEGER NOT NULL REFERENCES services(id), version INTEGER NOT NULL,
            availability_percent REAL NOT NULL, latency_ms INTEGER NOT NULL,
            latency_percent REAL NOT NULL, valid_from TEXT NOT NULL, actor TEXT NOT NULL,
            PRIMARY KEY(service_id,version));
        """)
        # Existing installations gain a monotonic concurrency token without rewriting history.
        if 'revision' not in {r['name'] for r in db.execute('PRAGMA table_info(incidents)')}:
            db.execute('ALTER TABLE incidents ADD COLUMN revision INTEGER NOT NULL DEFAULT 0')
        db.execute("""CREATE TRIGGER IF NOT EXISTS incident_revision AFTER UPDATE ON incidents
            WHEN NEW.revision = OLD.revision BEGIN
                UPDATE incidents SET revision=OLD.revision+1 WHERE id=NEW.id;
            END""")
        # Additive migration: preserve observations, incidents and legacy lab mappings.
        columns = {r['name'] for r in db.execute('PRAGMA table_info(telemetry_targets)')}
        for name, definition in {
            'target_url': "TEXT NOT NULL DEFAULT ''",
            'enabled': 'INTEGER NOT NULL DEFAULT 1',
            'kind': "TEXT NOT NULL DEFAULT 'laboratory'",
            'updated_at': "TEXT NOT NULL DEFAULT ''",
        }.items():
            if name not in columns:
                db.execute(f'ALTER TABLE telemetry_targets ADD COLUMN {name} {definition}')
        user_columns = {r['name'] for r in db.execute('PRAGMA table_info(users)')}
        for name, definition in {'active':'INTEGER NOT NULL DEFAULT 1',
                                 'must_change_password':'INTEGER NOT NULL DEFAULT 0'}.items():
            if name not in user_columns:
                db.execute(f'ALTER TABLE users ADD COLUMN {name} {definition}')
        if 'slo_latency_percent' not in {r['name'] for r in db.execute('PRAGMA table_info(services)')}:
            db.execute('ALTER TABLE services ADD COLUMN slo_latency_percent REAL NOT NULL DEFAULT 95')


def audit(db, actor, action, entity, detail=''):
    db.execute("INSERT INTO audit(actor, action, entity, detail, created_at) VALUES(?,?,?,?,?)",
               (actor, action, entity, detail, now()))


def event(db, incident_id, actor, action, note='', timestamp=None):
    db.execute("INSERT INTO timeline(incident_id, actor, action, note, created_at) VALUES(?,?,?,?,?)",
               (incident_id, actor, action, note, timestamp or now()))
