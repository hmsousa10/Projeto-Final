"""Explicit, disposable end-to-end fixture. Never serves a persistent database."""
import hashlib
import os
from pathlib import Path
import uuid

from app.version import VERSION

FIXTURE = 'nexo-disposable-cycle-v1'
DATABASE = '/app/data/cycle-test.db'


def main():
    if os.getenv('CYCLE_TEST_MODE') != '1' or os.getenv('DATABASE_PATH') != DATABASE:
        raise RuntimeError('Only the disposable cycle database is allowed')
    if Path(DATABASE).exists():
        raise RuntimeError('A fresh tmpfs is required for every experiment')
    # Refuse a bind mount or persistent volume even if the path happens to be empty.
    mounts = Path('/proc/mounts').read_text().splitlines()
    if not any(line.split()[1:3] == ['/app/data', 'tmpfs'] for line in mounts):
        raise RuntimeError('The experiment database requires its own tmpfs mount')
    from app.main import create_app
    app = create_app(DATABASE, demo=True)
    run_id = str(uuid.uuid4())
    source = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in (
        'app/main.py', 'app/alerts.py', 'app/telemetry.py', 'app/knowledge.py',
        'evaluation/cycle_server.py', 'evaluation/cycle_test.py', 'evaluation/cycle_protocol.json')}

    @app.get('/api/cycle-test-marker', include_in_schema=False)
    def marker():
        return {'fixture': FIXTURE, 'run_id': run_id, 'version': VERSION,
                'database': DATABASE, 'storage': 'tmpfs', 'source_sha256': source}

    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000, limit_concurrency=32,
                backlog=64, timeout_keep_alive=5)


if __name__ == '__main__':
    main()
