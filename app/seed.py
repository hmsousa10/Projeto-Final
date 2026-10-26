"""Dados sintéticos para explorar o protótipo. Nunca representam uma empresa real."""
import os
from datetime import datetime, timedelta, timezone

from .db import audit, database, event, now
from .security import hash_password


def seed(path):
    with database(path) as db:
        if db.execute('SELECT count(*) FROM users').fetchone()[0]:
            return
        db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('demo_initialized','1')")
        password = os.getenv('DEMO_PASSWORD', 'EstudoLocal2026!')
        # A mesma palavra-passe é intencional neste ambiente académico de demonstração.
        for name, email, role in [('Hugo Sousa', 'admin@local.test', 'admin'),
                                  ('Equipa de operações', 'operacoes@local.test', 'operator'),
                                  ('Consulta', 'leitor@local.test', 'viewer')]:
            db.execute('INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)',
                       (name, email, hash_password(password), role))
        services = [
            ('Portal de vendas', 'Comércio digital', 'Compras e pedidos dos clientes.', 'Alta', 99.9, 500),
            ('API de pagamentos', 'Serviços financeiros', 'Autorização de pagamentos e confirmações.', 'Alta', 99.95, 350),
            ('Faturação', 'Backoffice', 'Emissão e consulta de documentos de faturação.', 'Alta', 99.5, 800),
            ('Base de dados', 'Infraestrutura', 'Persistência partilhada pelos serviços empresariais.', 'Alta', 99.95, 100),
        ]
        for values in services:
            db.execute('INSERT INTO services(name,team,description,criticality,slo_availability,slo_latency_ms,created_at) VALUES(?,?,?,?,?,?,?)',
                       (*values, now()))
        db.executemany('INSERT INTO dependencies VALUES(?,?)', [(1, 2), (1, 4), (2, 4), (3, 4)])
        stamp = datetime.now(timezone.utc)
        for service_id in range(1, 5):
            for index in range(24):
                db.execute('INSERT INTO observations(service_id,available,latency_ms,source,observed_at) VALUES(?,?,?,?,?)',
                           (service_id, 1, 25 + service_id * 17 + (index * 13 % 37), 'demo',
                            (stamp - timedelta(minutes=(24-index)*5)).isoformat()))
        examples = [
            (2, 'Timeout na API de pagamentos', 'Pedidos de pagamento com timeout e aumento de latência nas ligações à base de dados.',
             'P2', 'Pool de ligações à base de dados esgotado.',
             'Libertar ligações presas e reiniciar o worker afetado depois de validar transações pendentes.',
             'Definir limite de ligações e alerta de saturação do pool.',
             '1. Consultar ligações ativas.\n2. Identificar transações presas.\n3. Validar pagamentos pendentes.\n4. Libertar ligações com autorização.\n5. Confirmar recuperação da latência.'),
            (1, 'Portal de vendas indisponível', 'Erros HTTP 503 no portal de vendas depois de uma alteração de configuração.',
             'P1', 'Variável de ambiente incorreta na nova versão.',
             'Reverter a configuração para a versão anterior e validar o endpoint de saúde.',
             'Validar configuração no pipeline antes de disponibilizar novas versões.',
             '1. Consultar logs do último deploy.\n2. Comparar configuração.\n3. Aprovar rollback.\n4. Reverter.\n5. Testar uma compra de demonstração.'),
            (3, 'Fila de faturação em atraso', 'Emissão de faturas lenta e fila de tarefas a crescer sem novos workers disponíveis.',
             'P3', 'Worker de faturação sem memória disponível.',
             'Reiniciar o worker e reprocessar as tarefas pendentes após verificar duplicados.',
             'Limitar memória por tarefa e monitorizar o comprimento da fila.',
             '1. Verificar tamanho da fila.\n2. Consultar memória do worker.\n3. Verificar tarefas duplicadas.\n4. Reiniciar worker.\n5. Confirmar emissão das faturas.'),
        ]
        for index, (sid, title, description, severity, cause, resolution, prevention, runbook) in enumerate(examples):
            created = stamp - timedelta(days=index+1, minutes=30)
            ack = created + timedelta(minutes=2+index)
            resolved = created + timedelta(minutes=18+index*4)
            closed = resolved + timedelta(minutes=5)
            cursor = db.execute('''INSERT INTO incidents(service_id,title,description,severity,status,assignee_id,
                created_at,acknowledged_at,resolved_at,closed_at,resolution,root_cause,prevention,runbook,source)
                VALUES(?,?,?,?,'closed',2,?,?,?,?,?,?,?,?, 'demo-history')''',
                (sid, title, description, severity, created.isoformat(), ack.isoformat(), resolved.isoformat(),
                 closed.isoformat(), resolution, cause, prevention, runbook))
            iid = cursor.lastrowid
            event(db, iid, 'Demonstração', 'Incidente criado', description, created.isoformat())
            event(db, iid, 'Demonstração', 'Reconhecido', 'Exemplo sintético.', ack.isoformat())
            event(db, iid, 'Demonstração', 'Em investigação', 'Análise dos registos.', (ack+timedelta(minutes=1)).isoformat())
            event(db, iid, 'Demonstração', 'Resolvido', resolution, resolved.isoformat())
            event(db, iid, 'Demonstração', 'Fechado', cause, closed.isoformat())
        audit(db, 'Sistema', 'demo.seed', 'ambiente', 'Dados sintéticos de demonstração criados.')
