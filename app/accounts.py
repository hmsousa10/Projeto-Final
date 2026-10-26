"""Account lifecycle without deleting attribution or disclosing password material."""
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Response

from .db import audit, database, now
from .models import PasswordChange, UserCreate, UserUpdate
from .security import check_password, hash_password, token_hash, password_capacity

PUBLIC = 'id,name,email,role,active,must_change_password'


def routes(app, path, current_user, admin, secure_cookie):
    @app.get('/api/admin/users')
    def list_users(user=Depends(admin)):
        with database(path) as db:
            return [dict(r) for r in db.execute(f'SELECT {PUBLIC} FROM users ORDER BY name,id')]

    @app.post('/api/admin/users', status_code=201)
    @password_capacity
    def create_user(data: UserCreate, user=Depends(admin)):
        password_hash = hash_password(data.password)
        with database(path) as db:
            try:
                result = db.execute('INSERT INTO users(name,email,password_hash,role,active,must_change_password) VALUES(?,?,?,?,1,1)',
                                    (data.name, data.email, password_hash, data.role))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Já existe uma conta com esse email.')
            audit(db, user['name'], 'user.created', f'user:{result.lastrowid}', data.role)
            return dict(db.execute(f'SELECT {PUBLIC} FROM users WHERE id=?', (result.lastrowid,)).fetchone())

    @app.put('/api/admin/users/{uid}')
    def update_user(uid: int, data: UserUpdate, user=Depends(admin)):
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
            if not old:
                raise HTTPException(404, 'Utilizador não encontrado.')
            if old['active'] and old['role'] == 'admin' and (not data.active or data.role != 'admin'):
                if db.execute("SELECT count(*) FROM users WHERE active=1 AND role='admin'").fetchone()[0] <= 1:
                    raise HTTPException(409, 'Tem de existir pelo menos um administrador ativo.')
            if not data.active or data.role == 'viewer':
                if db.execute("SELECT 1 FROM incidents WHERE assignee_id=? AND status NOT IN ('resolved','closed') LIMIT 1", (uid,)).fetchone():
                    raise HTTPException(409, 'Reatribui os incidentes ativos antes de desativar a conta ou alterar o perfil para Leitura.')
            try:
                db.execute('UPDATE users SET name=?,email=?,role=?,active=? WHERE id=?',
                           (data.name, data.email, data.role, int(data.active), uid))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Já existe uma conta com esse email.')
            if old['role'] != data.role or bool(old['active']) != data.active or old['email'] != data.email:
                db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
            changed = [key for key, value in {'name':data.name,'email':data.email,'role':data.role,'active':int(data.active)}.items() if old[key] != value]
            if changed:
                audit(db, user['name'], 'user.updated', f'user:{uid}', 'Campos alterados: ' + ', '.join(changed))
            return dict(db.execute(f'SELECT {PUBLIC} FROM users WHERE id=?', (uid,)).fetchone())

    @app.post('/api/account/password')
    @password_capacity
    def change_password(data: PasswordChange, response: Response, user=Depends(current_user)):
        stamp = datetime.now(timezone.utc)
        cutoff = (stamp-timedelta(minutes=10)).isoformat()
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM password_change_attempts WHERE attempted_at<?', (cutoff,))
            limited = db.execute('SELECT count(*) FROM password_change_attempts WHERE user_id=?', (user['id'],)).fetchone()[0] >= 5
            if not limited:
                db.execute('INSERT INTO password_change_attempts(user_id,attempted_at) VALUES(?,?)', (user['id'],stamp.isoformat()))
            old_hash = db.execute('SELECT password_hash FROM users WHERE id=?', (user['id'],)).fetchone()[0]
        if limited:
            raise HTTPException(429, 'Demasiadas tentativas de alteração. Tenta novamente mais tarde.', headers={'Retry-After':'600'})
        if not check_password(data.current_password, old_hash):
            raise HTTPException(400, 'A palavra-passe atual não está correta.')
        if check_password(data.new_password, old_hash):
            raise HTTPException(422, 'A nova palavra-passe tem de ser diferente da atual.')
        new_hash = hash_password(data.new_password)
        token = secrets.token_urlsafe(32)
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE')
            # Do not undo a concurrent deactivation, role change or password change.
            account = db.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
            if not account['active'] or account['password_hash'] != old_hash or account['role'] != user['role'] or account['email'] != user['email']:
                raise HTTPException(409, 'A conta mudou durante o pedido. Inicia sessão novamente.')
            db.execute('UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?', (new_hash,user['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
            db.execute('DELETE FROM password_change_attempts WHERE user_id=?', (user['id'],))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (token_hash(token),user['id'],(stamp+timedelta(hours=8)).isoformat()))
            audit(db,user['name'],'user.password.changed',f'user:{user["id"]}','Sessões anteriores revogadas.')
        response.set_cookie('nexo_session',token,httponly=True,samesite='strict',max_age=28800,secure=secure_cookie)
        return {'ok':True,'must_change_password':False}
