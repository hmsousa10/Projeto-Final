"""Read-only HTTP rehearsal assertions, fixed port, demo credentials via stdin-free fixture."""
import http.cookiejar
import json
from urllib.request import build_opener, HTTPCookieProcessor, ProxyHandler, Request


def inspect():
    client = build_opener(ProxyHandler({}), HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def api(path, body=None):
        req = Request('http://127.0.0.1:8013/api/' + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={'Content-Type':'application/json'})
        with client.open(req, timeout=8) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError('Response too large')
        return json.loads(raw)
    api('login', {'email':'leitor@local.test','password':'EstudoLocal2026!'})
    try:
        cases = api('incidents')
        details = [api('incidents/' + str(case['id'])) for case in cases]
        result = {'health':api('health'), 'incidents':len(cases),
                  'timeline':sum(len(case['timeline']) for case in details),
                  'closed_postmortems':sum(bool(c['root_cause'] and c['prevention'] and c['resolution'])
                                          for c in details if c['status']=='closed'),
                  'knowledge_method':api('knowledge?q=HTTP%20503&method=bm25')['actual_method']}
        return result
    finally:
        api('logout', {})


if __name__ == '__main__':
    print(json.dumps(inspect(), ensure_ascii=True))
