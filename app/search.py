"""Baseline de recuperação TF-IDF e similaridade de cosseno, sem modelo generativo.

O corpus é formado apenas por incidentes resolvidos/fechados. O vocabulário e o IDF
são calculados nesse corpus; a consulta é projetada no mesmo espaço vetorial.
"""
import math
import re
import unicodedata
from collections import Counter

STOP = set('a o as os de da do das dos e em um uma para por com que no na nos nas ao se'.split())


def terms(text):
    text = unicodedata.normalize('NFKD', text.lower())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return [t for t in re.findall(r'[a-z0-9]+', text) if len(t) > 1 and t not in STOP]


def retrieve(query, documents, limit=5):
    if not documents:
        return []
    corpus = [terms(' '.join(str(d.get(k) or '') for k in
                            ('title', 'description', 'resolution', 'root_cause'))) for d in documents]
    frequencies = Counter(term for document in corpus for term in set(document))
    idf = {term: math.log((1 + len(corpus)) / (1 + count)) + 1 for term, count in frequencies.items()}

    def vector(tokens):
        counts = Counter(tokens)
        values = {term: (1 + math.log(count)) * idf[term]
                  for term, count in counts.items() if term in idf}
        norm = math.sqrt(sum(v * v for v in values.values()))
        return {term: value / norm for term, value in values.items()} if norm else {}

    q = vector(terms(query))
    results = []
    for document, tokens in zip(documents, corpus):
        v = vector(tokens)
        score = sum(weight * v.get(term, 0) for term, weight in q.items())
        if score > 0:
            results.append({**document, 'score': round(score, 4)})
    return sorted(results, key=lambda r: (-r['score'], r['id']))[:limit]
