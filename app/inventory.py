from fastapi import HTTPException


def validate_dependencies(db, service_id, dependencies):
    graph = {}
    for row in db.execute('SELECT service_id,depends_on_id FROM dependencies'):
        graph.setdefault(row['service_id'],set()).add(row['depends_on_id'])
    for dependency in set(dependencies):
        if not db.execute('SELECT 1 FROM services WHERE id=?',(dependency,)).fetchone():
            raise HTTPException(404,'Serviço de dependência não encontrado.')
        if dependency == service_id:
            raise HTTPException(422,'Um serviço não pode depender de si próprio.')
        pending, seen = [dependency], set()
        while pending:
            current = pending.pop()
            if current == service_id:
                raise HTTPException(422,'Esta alteração criaria um ciclo de dependências.')
            if current not in seen:
                seen.add(current)
                pending.extend(graph.get(current,()))
