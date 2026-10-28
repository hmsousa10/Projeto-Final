"""Recuperação verificável: BM25, embeddings locais e fusão por posição.

Não gera texto nem executa os procedimentos encontrados. Os vetores são uma cache,
e só são usados se o conteúdo atual e a versão do modelo coincidirem.
"""
import asyncio
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import threading
from urllib.request import Request, ProxyHandler, build_opener

from .db import database
from .search import retrieve, terms
from .telemetry import NoRedirect, validate_url

MODEL_KEY = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2@e8f8c211226b894fcb81acc59f3b34ba3efd5f42:quint8-avx2:mean128:v1'
FIELDS = ('title', 'description', 'root_cause', 'resolution', 'prevention', 'runbook', 'service_name')
LABELS = {'tfidf':'TF-IDF · cosseno', 'bm25':'BM25 · palavras', 'semantic':'Embeddings locais · cosseno', 'hybrid':'Híbrido · fusão RRF', 'catalog':'Histórico disponível'}
THRESHOLD = .35
CORPUS_LIMIT = 100


def corpus(path, service_id=None, scope='all', exclude_id=None):
    clauses = ["i.status IN ('resolved','closed')"]
    values = []
    if service_id is not None:
        clauses.append('i.service_id=?')
        values.append(service_id)
    if exclude_id is not None:
        clauses.append('i.id!=?')
        values.append(exclude_id)
    if scope == 'examples':
        clauses.append("i.source LIKE 'demo%'")
    elif scope == 'operational':
        clauses.append("i.source NOT LIKE 'demo%'")
    where = ' AND '.join(clauses)
    with database(path) as db:
        total = db.execute('SELECT COUNT(*) FROM incidents i WHERE '+where, values).fetchone()[0]
        # One bounded global corpus; filters restrict it before computing any ranks.
        rows = [dict(r) for r in db.execute('SELECT i.*,s.name service_name FROM incidents i JOIN services s ON s.id=i.service_id WHERE '+where+" AND i.id IN (SELECT id FROM incidents WHERE status IN ('resolved','closed') ORDER BY id DESC LIMIT ?) ORDER BY i.id DESC", [*values, CORPUS_LIMIT])]
    return rows, total


def chunks(document):
    # Three bounded sections keep symptoms separate from the subsequent solution.
    groups = [('Sintomas', ('title','service_name','description')),
              ('Causa e resolução', ('root_cause','resolution')),
              ('Prevenção e runbook', ('prevention','runbook'))]
    result = []
    for label, fields in groups:
        text = ' '.join(str(document.get(f) or '').strip() for f in fields).strip()
        if text:
            # Documented excerpt, not an assertion that all long fields were indexed.
            text = text[:600]
            key = hashlib.sha256((label+'\n'+text).encode()).hexdigest()
            result.append({'section':label, 'text':text, 'key':key})
    return result


def bm25(query, documents, limit=5):
    if not documents:
        return []
    tokens = [terms(' '.join(str(d.get(f) or '') for f in FIELDS)) for d in documents]
    average = sum(map(len,tokens))/len(tokens) or 1
    frequency = Counter(t for ts in tokens for t in set(ts))
    result = []
    for document, ts in zip(documents, tokens):
        counts = Counter(ts)
        score = 0
        for term in set(terms(query)):
            count = counts[term]
            if count:
                idf = math.log(1+(len(tokens)-frequency[term]+.5)/(frequency[term]+.5))
                score += idf*count*2.2/(count+1.2*(.25+.75*len(ts)/average))
        if score:
            result.append({**document, 'score':round(score,6)})
    return sorted(result,key=lambda d:(-d['score'],d['id']))[:limit]


def semantic_rank(documents, vectors, query_vector, limit=5):
    result = []
    for document in documents:
        scores = [(sum(a*b for a,b in zip(query_vector,vectors[c['key']])),c) for c in chunks(document)]
        if not scores:
            continue
        score, matched = max(scores,key=lambda x:x[0])
        if score >= THRESHOLD:
            result.append({**document, 'score':round(max(-1,min(1,score)),6),
                           'matched_section':matched['section'], 'excerpt':matched['text']})
    return sorted(result,key=lambda d:(-d['score'],d['id']))[:limit]


def fuse(lexical, semantic, limit=5):
    scores, rows = {}, {}
    for method, ranking in [('bm25',lexical),('semantic',semantic)]:
        for rank, row in enumerate(ranking,1):
            iid = row['id']
            rows.setdefault(iid,dict(row))
            if method == 'semantic':
                rows[iid].update({k:row[k] for k in ('matched_section','excerpt')})
            rows[iid][method+'_score'] = row['score']
            scores[iid] = scores.get(iid,0)+1/(60+rank)
    return [{**rows[iid], 'score':round(scores[iid],8)} for iid in sorted(scores,key=lambda iid:(-scores[iid],iid))[:limit]]


class Encoder:
    def __init__(self, url, token):
        self.url = validate_url(url)
        self.token = token
        self.opener = build_opener(ProxyHandler({}),NoRedirect())

    def embed(self, texts):
        if not 1 <= len(texts) <= 16:
            raise ValueError('Invalid batch')
        request = Request(self.url+'/embed',data=json.dumps({'texts':texts}).encode(),
                          headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token},method='POST')
        with self.opener.open(request,timeout=8) as response:
            raw = response.read(1024*1024+1)
        if len(raw)>1024*1024:
            raise ValueError('Embedding response too large')
        payload = json.loads(raw)
        if not isinstance(payload,dict):
            raise ValueError('Invalid embedding response')
        vectors = payload.get('vectors')
        if payload.get('model') != MODEL_KEY or not isinstance(vectors,list) or len(vectors)!=len(texts):
            raise ValueError('Unexpected embedding model or batch')
        for vector in vectors:
            if not isinstance(vector,list) or len(vector)!=384 or any(type(x) not in (int,float) or not math.isfinite(x) for x in vector):
                raise ValueError('Invalid embedding vector')
            norm = sum(x*x for x in vector)
            if not .98 <= norm <= 1.02:
                raise ValueError('Embedding vector must be normalized')
        return vectors


class Knowledge:
    def __init__(self,path,encoder=None):
        self.path, self.encoder = path, encoder
        self.query_gate = threading.BoundedSemaphore(2)

    @classmethod
    def configured(cls,path):
        url = os.getenv('SEMANTIC_URL','')
        encoder = None
        if url:
            token = Path(os.environ['SEMANTIC_TOKEN_FILE']).read_text().strip()
            if len(token)<32:
                raise RuntimeError('Semantic access secret must contain at least 32 characters')
            encoder = Encoder(url,token)
        return cls(path,encoder)

    def initialize(self):
        with database(self.path) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS knowledge_vectors (
                content_hash TEXT NOT NULL, model TEXT NOT NULL, vector TEXT NOT NULL,
                PRIMARY KEY(content_hash,model))''')

    def cached(self, documents):
        keys = {c['key'] for d in documents for c in chunks(d)}
        with database(self.path) as db:
            rows = db.execute('SELECT content_hash,vector FROM knowledge_vectors WHERE model=?',(MODEL_KEY,)).fetchall()
        return {r[0]:json.loads(r[1]) for r in rows if r[0] in keys}

    def index_step(self):
        if not self.encoder:
            return
        documents,_ = corpus(self.path)
        parts = {c['key']:c for d in documents for c in chunks(d)}
        cached = self.cached(documents)
        missing = [p for key,p in parts.items() if key not in cached][:16]
        if missing:
            vectors = self.encoder.embed([p['text'] for p in missing])
            with database(self.path) as db:
                db.executemany('INSERT OR REPLACE INTO knowledge_vectors VALUES(?,?,?)',
                               [(p['key'],MODEL_KEY,json.dumps(v)) for p,v in zip(missing,vectors)])
        # Bounded cache: remove obsolete content/model after each successful step.
        with database(self.path) as db:
            db.execute('DELETE FROM knowledge_vectors WHERE model!=?',(MODEL_KEY,))
            for row in db.execute('SELECT content_hash FROM knowledge_vectors').fetchall():
                if row[0] not in parts:
                    db.execute('DELETE FROM knowledge_vectors WHERE content_hash=?',(row[0],))

    async def run_indexer(self):
        while True:
            try:
                await asyncio.to_thread(self.index_step)
            except (OSError,ValueError,KeyError,TypeError):
                pass  # Search reports unavailable/incomplete explicitly; no text logged.
            await asyncio.sleep(5)

    def search(self,query,documents,method='hybrid',limit=5):
        actual = method
        warning = None
        needed = {c['key'] for d in documents for c in chunks(d)}
        vectors = self.cached(documents) if self.encoder else {}
        ready = needed <= vectors.keys()
        if not query.strip():
            actual, result = 'catalog', documents
        elif method == 'tfidf':
            result = retrieve(query,documents,limit)
        elif method == 'bm25':
            result = bm25(query,documents,limit)
        else:
            if not self.encoder:
                warning = 'Modelo semântico não configurado. Pesquisa textual BM25 utilizada.'
            elif not ready:
                warning = 'Índice semântico em preparação. Pesquisa textual BM25 utilizada; volta a pesquisar dentro de alguns segundos.'
            elif not self.query_gate.acquire(blocking=False):
                warning = 'Pesquisa semântica ocupada. Pesquisa textual BM25 utilizada.'
            else:
                try:
                    q = self.encoder.embed([query])[0]
                    semantic = semantic_rank(documents,vectors,q,len(documents))
                    result = semantic[:limit] if method=='semantic' else fuse(bm25(query,documents,len(documents)),semantic,limit)
                except (OSError,ValueError,KeyError,TypeError):
                    warning = 'Modelo semântico temporariamente indisponível. Pesquisa textual BM25 utilizada.'
                finally:
                    self.query_gate.release()
            if warning:
                actual, result = 'bm25', bm25(query,documents,limit)
        query_terms = set(terms(query))
        for row in result:
            row['provenance'] = 'Exemplo sintético' if str(row.get('source','')).startswith('demo') else 'Sondagens de laboratório' if row.get('source')=='prometheus-alert' else 'API empresarial autenticada' if row.get('source')=='enterprise-alert' else 'Registo manual'
            row['matched_terms'] = sorted(query_terms & set(terms(' '.join(str(row.get(f) or '') for f in FIELDS))))[:12]
            row['score_kind'] = actual
        return {'results':result,'method':LABELS[actual], 'requested_method':method,'actual_method':actual,
                'warning':warning, 'model':MODEL_KEY if actual in ('semantic','hybrid') else None,
                'index':{'configured':bool(self.encoder),'ready_chunks':len(vectors),'total_chunks':len(needed)},
                'semantic_threshold':THRESHOLD, 'corpus_size':len(documents)}
