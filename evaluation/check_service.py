"""Read-only checks against the isolated local encoder; no incident mutations."""
import json
import math
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

from app.knowledge import Encoder

url=os.environ['SEMANTIC_URL']
token=Path(os.environ['SEMANTIC_TOKEN_FILE']).read_text().strip()
opener=build_opener(ProxyHandler({}))


def rejected(payload,expected,authorized=True):
    headers={'Content-Type':'application/json'}
    if authorized:
        headers['Authorization']='Bearer '+token
    try:
        opener.open(Request(url+'/embed',data=json.dumps(payload).encode(),headers=headers),timeout=8)
    except HTTPError as error:
        assert error.code==expected,(error.code,expected)
        assert b'secret-example-content' not in error.read()
    else:
        raise AssertionError('Invalid request was accepted')


rejected({'texts':['secret-example-content']},401,False)
rejected({'texts':['x']*17},422)
rejected({'texts':['x'*2001]},422)
rejected({'texts':['   ']},422)
rejected({'texts':['secret-example-content'],'extra':'invalid'},422)
rejected({'texts':['x'*70000]},413)
vectors=Encoder(url,token).embed(['Serviço indisponível','O portal deixou de responder'])
assert len(vectors)==2 and all(len(v)==384 for v in vectors)
assert all(math.isclose(sum(x*x for x in v),1,abs_tol=.001) for v in vectors)
print('6 rejection checks and normalized 384-dimensional inference passed.')
