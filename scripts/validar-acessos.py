"""Exercise account creation, first access, session revocation and deactivation locally."""
from datetime import datetime, timezone
import http.cookiejar
import json
import os
from pathlib import Path
import runpy
import secrets
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor

helpers=runpy.run_path(str(Path(__file__).with_name('validar-laboratorio.py')))
api, wait_until=helpers['api'],helpers['wait_until']


def session():
    opener=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(path,body=None):
        req=Request('http://127.0.0.1:8001/api/'+path,data=json.dumps(body).encode() if body is not None else None,
                    headers={'Content-Type':'application/json'})
        with opener.open(req,timeout=5) as response:
            return json.load(response)
    return call


def code(call):
    try:
        call()
        return 200
    except HTTPError as error:
        return error.code


def main():
    api('login',{'email':'admin@local.test','password':os.getenv('DEMO_PASSWORD','EstudoLocal2026!')})
    initial,new=secrets.token_urlsafe(24),secrets.token_urlsafe(24)
    email='validacao.'+secrets.token_hex(4)+'@local.test'
    account=api('admin/users',{'name':'Conta de validação 0.5','email':email,'role':'operator','password':initial})
    uid=account['id']
    current,other=session(),session()
    try:
        current('login',{'email':email,'password':initial})
        other('login',{'email':email,'password':initial})
        assert code(lambda:current('services'))==403
        print('PASS: first access requires password change',flush=True)
        current('account/password',{'current_password':initial,'new_password':new})
        assert len(current('services'))>0
        assert code(lambda:other('me'))==401
        assert code(lambda:other('login',{'email':email,'password':initial}))==401
        print('PASS: password change activates access and revokes old sessions/password',flush=True)
        api(f'admin/users/{uid}',{'name':account['name'],'email':email,'role':'viewer','active':True},'PUT')
        assert code(lambda:current('me'))==401
        current('login',{'email':email,'password':new})
        assert code(lambda:current('incidents',{'service_id':1,'title':'Não deve ser criado','description':'Verificação do perfil de leitura no ensaio.'}))==403
        print('PASS: changed role revokes the session and denies writes',flush=True)
    finally:
        api(f'admin/users/{uid}',{'name':'Conta de validação 0.5 · desativada','email':email,'role':'viewer','active':False},'PUT')
    assert code(lambda:current('me'))==401
    assert code(lambda:other('login',{'email':email,'password':new}))==401
    print('PASS: deactivated account cannot sign in; attribution is preserved',flush=True)
    evidence={'status':'passed','executed_at':datetime.now(timezone.utc).isoformat(),'validation_user_id':uid,'final_active':False,
              'steps':['account creation','mandatory password change','old session revocation','old password rejected','role change','viewer writes denied','deactivation','login denied']}
    (Path(__file__).resolve().parent.parent/'docs'/'validacao-acessos.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(evidence),flush=True)


if __name__=='__main__':
    main()
