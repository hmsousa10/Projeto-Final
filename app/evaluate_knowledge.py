"""Offline benchmark. Never reads/writes the application's incident database."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

from .knowledge import Encoder, MODEL_KEY, THRESHOLD, bm25, chunks, fuse, semantic_rank
from .search import retrieve


def metrics(runs,k=3):
    positives = [r for r in runs if r['relevant']]
    negatives = [r for r in runs if not r['relevant']]
    def mean(values):
        return round(statistics.mean(values),4) if values else None
    return {'positive_queries':len(positives),'negative_queries':len(negatives),
            'precision_at_3':mean([len(set(r['ids'])&set(r['relevant']))/k for r in positives]),
            'recall_at_3':mean([len(set(r['ids'])&set(r['relevant']))/len(r['relevant']) for r in positives]),
            'mrr_at_3':mean([next((1/n for n,iid in enumerate(r['ids'],1) if iid in r['relevant']),0) for r in positives]),
            'no_answer_accuracy':mean([float(not r['ids']) for r in negatives]),
            'mean_query_ms':mean([r['ms'] for r in runs]),
            'max_query_ms':round(max(r['ms'] for r in runs),2) if runs else None}


def evaluate(dataset,encoder):
    raw = Path(dataset).read_bytes()
    fixture = json.loads(raw)
    documents = fixture['documents']
    parts = {c['key']:c for d in documents for c in chunks(d)}
    start = time.perf_counter()
    vectors = {}
    items = list(parts.values())
    for i in range(0,len(items),16):
        batch = items[i:i+16]
        vectors.update(zip([c['key'] for c in batch],encoder.embed([c['text'] for c in batch])))
    index_ms = (time.perf_counter()-start)*1000
    runs = {m:[] for m in ('tfidf','bm25','semantic','hybrid')}
    # No threshold/model/weights are adjusted from either split.
    for query in fixture['queries']:
        for method in runs:
            start = time.perf_counter()
            if method == 'tfidf':
                result = retrieve(query['text'],documents,3)
            elif method == 'bm25':
                result = bm25(query['text'],documents,3)
            else:
                qvector = encoder.embed([query['text']])[0]
                semantic = semantic_rank(documents,vectors,qvector,len(documents))
                result = semantic[:3] if method=='semantic' else fuse(bm25(query['text'],documents,len(documents)),semantic,3)
            runs[method].append({**query,'ids':[r['id'] for r in result],'ms':round((time.perf_counter()-start)*1000,2)})
    return {'created_at':datetime.now(timezone.utc).isoformat(),'dataset_sha256':hashlib.sha256(raw).hexdigest(),
            'dataset_version':fixture['version'],'model':MODEL_KEY,'threshold':THRESHOLD,'rrf_constant':60,
            'documents':len(documents),'chunks':len(parts),'index_ms':round(index_ms,2),
            'limitations':'Small hand-authored synthetic corpus. No statistical/generalization or MTTR claim. No tuning after test. Query timing excludes indexing and HTTP/UI overhead; semantic includes local inference. P@3 uses denominator 3; MRR is truncated at 3.',
            'metrics':{split:{m:metrics([r for r in rows if r['split']==split]) for m,rows in runs.items()} for split in ('dev','test')},
            'runs':runs}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset',default='evaluation/benchmark.json')
    parser.add_argument('--output',required=True)
    args = parser.parse_args()
    encoder = Encoder(os.environ['SEMANTIC_URL'],Path(os.environ['SEMANTIC_TOKEN_FILE']).read_text().strip())
    report = evaluate(args.dataset,encoder)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report['metrics'],ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
