import base64
from contextlib import closing
import json
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys

import pytest

from app import portable,recovery
from tests.test_recovery import fixture

PHRASE='Ensaio descartável: ação, Ω e 漢字; não usar como segredo!'


def test_authenticated_key_transport_and_randomness():
    key=secrets.token_bytes(32)
    blob=portable.wrap(key,PHRASE)
    assert len(blob)==84 and portable.unwrap(blob,PHRASE)==key
    assert key not in blob and PHRASE.encode() not in blob
    assert portable.wrap(key,PHRASE)!=blob
    with pytest.raises(recovery.RecoveryError):portable.unwrap(blob,PHRASE.swapcase())


@pytest.mark.parametrize('mutation',['prefix','salt','nonce','ciphertext','tag','truncated','oversized'])
def test_tampered_key_rejected(mutation):
    blob=portable.wrap(secrets.token_bytes(32),PHRASE)
    position={'prefix':0,'salt':8,'nonce':24,'ciphertext':36,'tag':83}.get(mutation)
    if position is not None:
        blob=blob[:position]+bytes([blob[position]^1])+blob[position+1:]
    else:blob=blob[:-1] if mutation=='truncated' else blob+b'x'
    with pytest.raises(recovery.RecoveryError):portable.unwrap(blob,PHRASE)


@pytest.mark.parametrize('phrase',['curta',' '*24,'a'*24,'x'*257,'Uma frase bastante longa\nmas com quebra'])
def test_invalid_phrase_rejected(phrase):
    with pytest.raises(recovery.RecoveryError):portable.wrap(secrets.token_bytes(32),phrase)


def test_portable_restore_without_windows_context(fixture,tmp_path):
    source,key=fixture
    archive,manifest=recovery.create(source,key)
    wrapped,report=portable.export(archive,key,PHRASE)
    assert report['tables']==manifest['tables']
    result=recovery.restore(archive,portable.unwrap(wrapped,PHRASE),tmp_path/'portable')
    assert result['sessions_revoked'] and result['monitoring_paused']
    with closing(sqlite3.connect(result['path'])) as db:
        assert db.execute('SELECT COUNT(*) FROM timeline').fetchone()[0]==manifest['tables']['timeline']
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM telemetry_targets WHERE enabled=1').fetchone()[0]==0


def test_wrong_pair_and_invalid_export_do_not_publish_database(fixture,tmp_path,monkeypatch):
    source,key=fixture
    archive,_=recovery.create(source,key)
    other=portable.wrap(secrets.token_bytes(32),PHRASE)
    with pytest.raises(recovery.RecoveryError):
        recovery.restore(archive,portable.unwrap(other,PHRASE),tmp_path/'wrong')
    assert not (tmp_path/'wrong').exists()
    def forbidden(*args):raise AssertionError('Derivation should not run for an invalid archive')
    monkeypatch.setattr(portable,'derive',forbidden)
    with pytest.raises(recovery.RecoveryError):portable.export(b'invalid',key,PHRASE)


def test_cli_never_echoes_phrase_or_unwrapped_key(fixture):
    source,key=fixture
    archive,_=recovery.create(source,key)
    phrase='cli-secret-value-not-for-production-123'
    wrapped=portable.wrap(key,PHRASE)
    payload={'archive':base64.b64encode(archive).decode(),'wrapped_key':base64.b64encode(wrapped).decode(),
             'passphrase_b64':base64.b64encode(phrase.encode()).decode()}
    result=subprocess.run([sys.executable,'-m','app.portable','verify'],input=json.dumps(payload).encode(),capture_output=True)
    assert result.returncode==1 and not result.stdout
    assert phrase.encode() not in result.stderr and base64.b64encode(key) not in result.stderr


def test_interactive_kit_verification(fixture,tmp_path,monkeypatch,capsys):
    source,key=fixture
    archive,_=recovery.create(source,key)
    kit=tmp_path/'kit';kit.mkdir()
    (kit/'copia.nexobak').write_bytes(archive)
    (kit/'chave.nexokey').write_bytes(portable.wrap(key,PHRASE))
    monkeypatch.setattr(portable,'read_phrase',lambda:PHRASE)
    monkeypatch.setattr(sys,'argv',['portable','verify','--kit',str(kit)])
    portable.main()
    output=capsys.readouterr()
    assert json.loads(output.out)['verified']
    assert PHRASE not in output.out and PHRASE not in output.err


def test_interactive_phrase_refuses_echo_fallback(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(portable.sys,'stdin',SimpleNamespace(isatty=lambda:False))
    with pytest.raises(recovery.RecoveryError):portable.read_phrase()
    monkeypatch.setattr(portable.sys,'stdin',SimpleNamespace(isatty=lambda:True))
    def warning(prompt):raise portable.getpass.GetPassWarning('Echo cannot be disabled')
    monkeypatch.setattr(portable.getpass,'getpass',warning)
    with pytest.raises(recovery.RecoveryError):portable.read_phrase()
