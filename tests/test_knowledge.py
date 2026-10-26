import json

import pytest
from fastapi.testclient import TestClient

from app.db import initialize, database
from app.evaluate_knowledge import metrics
from app.knowledge import Encoder, Knowledge, MODEL_KEY, bm25, chunks, fuse, semantic_rank
from app.main import create_app
from app.seed import seed


def test_lexical_runbook_accents_and_empty():
    docs=[{'id':1,'title':'Outro erro','runbook':'Renovar certificado e validar ligação'},
          {'id':2,'title':'Disco cheio','resolution':'Libertar espaço'}]
    assert bm25('LIGACAO certificado',docs)[0]['id']==1
    assert bm25('astronomia',docs)==[]
    assert bm25('disco',[])==[]


def test_semantic_threshold_and_rrf_unique_deterministic():
    docs=[{'id':1,'title':'a'},{'id':2,'title':'b'}]
    vectors={chunks(d)[0]['key']:([1.,0.] if d['id']==1 else [0.,1.]) for d in docs}
    ranked=semantic_rank(docs,vectors,[1.,0.])
    assert [r['id'] for r in ranked]==[1]
    assert ranked[0]['excerpt']=='a'
    rows=fuse([{'id':2,'score':3},{'id':1,'score':2}],ranked)
    assert [r['id'] for r in rows]==[1,2]
    assert rows[0]['bm25_score']==2 and rows[0]['semantic_score']==1
    assert rows[0]['score']<.04


class FakeEncoder:
    calls=0
    def embed(self,texts):
        self.calls+=1
        return [[1.]+[0.]*383 for _ in texts]


@pytest.fixture
def engine(tmp_path):
    path=str(tmp_path/'knowledge.db')
    initialize(path)
    seed(path)
    engine=Knowledge(path,FakeEncoder())
    engine.initialize()
    return engine


def test_cache_content_addressing_and_provenance(engine):
    docs=[{'id':1,'title':'certificado expirado','source':'demo_history'}]
    assert 'preparação' in engine.search('certificado',docs)['warning']
    vectors=engine.encoder.embed([c['text'] for c in chunks(docs[0])])
    with database(engine.path) as db:
        db.executemany('INSERT INTO knowledge_vectors VALUES(?,?,?)',[(c['key'],MODEL_KEY,json.dumps(v)) for c,v in zip(chunks(docs[0]),vectors)])
    result=engine.search('certificado',docs)
    assert result['actual_method']=='hybrid' and result['warning'] is None
    assert result['results'][0]['provenance']=='Exemplo sintético'
    assert result['results'][0]['matched_terms']==['certificado']
    docs[0]['source']='prometheus-alert'
    assert engine.search('certificado',docs)['results'][0]['provenance']=='Sondagens de laboratório'
    docs[0]['title']='certificado alterado'
    assert engine.search('certificado',docs)['actual_method']=='bm25'


def test_index_step_reuses_and_removes_stale_content(engine):
    engine.index_step()
    calls=engine.encoder.calls
    engine.index_step()
    assert engine.encoder.calls==calls
    with database(engine.path) as db:
        db.execute("UPDATE incidents SET runbook='Novo procedimento xpto' WHERE id=1")
    engine.index_step()
    assert engine.encoder.calls==calls+1
    with database(engine.path) as db:
        db.execute("UPDATE incidents SET status='investigating' WHERE id=1")
    engine.index_step()
    from app.knowledge import corpus
    docs,_=corpus(engine.path)
    assert len(engine.cached(docs))==sum(len(chunks(d)) for d in docs)


def test_explicit_fallback_and_busy_gate(engine):
    from app.knowledge import corpus
    docs,_=corpus(engine.path)
    engine.index_step()
    engine.encoder.embed=lambda texts: (_ for _ in ()).throw(OSError('SECRET upstream URL'))
    result=engine.search('timeout',docs)
    assert result['actual_method']=='bm25'
    assert 'SECRET' not in json.dumps(result)
    engine.query_gate.acquire();engine.query_gate.acquire()
    try:
        assert 'ocupada' in engine.search('timeout',docs)['warning']
    finally:
        engine.query_gate.release();engine.query_gate.release()
    engine.encoder=None
    assert 'não configurado' in engine.search('timeout',docs)['warning']
    assert engine.search('',docs)['actual_method']=='catalog'


def test_authenticated_filters_validation_and_exclusion(tmp_path,monkeypatch):
    monkeypatch.setenv('DEMO_PASSWORD','EstudoLocal2026!')
    monkeypatch.delenv('SEMANTIC_URL',raising=False)
    path=str(tmp_path/'test.db')
    with TestClient(create_app(path,demo=True),base_url='http://localhost') as client:
        assert client.get('/api/knowledge').status_code==401
        client.post('/api/login',json={'email':'leitor@local.test','password':'EstudoLocal2026!'})
        rows=client.get('/api/knowledge').json()['results']
        assert rows and all(r['status'] in ('resolved','closed') for r in rows)
        iid,sid=rows[0]['id'],rows[0]['service_id']
        filtered=client.get('/api/knowledge',params={'service_id':sid,'exclude_id':iid}).json()
        assert all(r['service_id']==sid and r['id']!=iid for r in filtered['results'])
        assert client.get('/api/knowledge?scope=operational').json()['results']==[]
        assert client.get('/api/knowledge?scope=examples').json()['corpus_size']==len(rows)
        for params in ({'method':'custom'},{'scope':'secret'},{'service_id':-1},{'q':'x'*2001}):
            assert client.get('/api/knowledge',params=params).status_code==422


@pytest.mark.parametrize('bad',['model','size','nan','norm'])
def test_encoder_rejects_invalid_upstream(bad):
    encoder=Encoder('http://semantic:8080','x'*32)
    payload={'model':MODEL_KEY,'vectors':[[1.]+[0.]*383]}
    if bad=='model':payload['model']='unexpected'
    if bad=='size':payload['vectors'][0]=[1.]
    if bad=='nan':payload['vectors'][0][0]=float('nan')
    if bad=='norm':payload['vectors'][0][0]=2.
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,limit):return json.dumps(payload).encode()
    class Opener:
        def open(self,*args,**kwargs):return Response()
    encoder.opener=Opener()
    with pytest.raises(ValueError):encoder.embed(['text'])


def test_evaluation_metrics_denominators():
    result=metrics([{'relevant':[1],'ids':[3,1],'ms':1},
                    {'relevant':[2],'ids':[],'ms':2},
                    {'relevant':[],'ids':[],'ms':3},
                    {'relevant':[],'ids':[1],'ms':4}])
    assert result['precision_at_3']==.1667 and result['recall_at_3']==.5
    assert result['mrr_at_3']==.25 and result['no_answer_accuracy']==.5


def test_corpus_cap_applies_consistently_to_all_filters(engine):
    from app.knowledge import corpus
    with database(engine.path) as db:
        for n in range(105):
            db.execute("""INSERT INTO incidents(service_id,title,description,severity,status,created_at,source)
                VALUES(1,?,'Registo de teste','P3','closed','2026-10-24T00:00:00+00:00','manual')""",(f'Caso {n}',))
    rows,total=corpus(engine.path)
    assert len(rows)==100 and total==108
    assert all(r['source']=='manual' for r in rows)
    examples,total=corpus(engine.path,scope='examples')
    assert examples==[] and total==3
    operational,total=corpus(engine.path,scope='operational')
    assert len(operational)==100 and total==105
