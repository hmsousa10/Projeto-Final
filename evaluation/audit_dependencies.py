"""Query OSV for public installed package names/versions; never send app data."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from urllib.request import Request,urlopen


def query(queries):
    request=Request('https://api.osv.dev/v1/querybatch',data=json.dumps({'queries':queries}).encode(),headers={'Content-Type':'application/json'})
    with urlopen(request,timeout=20) as response:raw=response.read(4*1024*1024+1)
    if len(raw)>4*1024*1024:raise ValueError('Oversized OSV response')
    result=json.loads(raw)['results']
    if len(result)!=len(queries):raise ValueError('Incomplete OSV response')
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('inventories',nargs='+');args=parser.parse_args()
    report={'checked_at':datetime.now(timezone.utc).isoformat(),'service':'https://api.osv.dev/v1/querybatch','inventories':{},'complete':True,
            'limitations':'Known advisories only. No malware/provenance review, OS/base-image scan, exploitability proof or guarantee of safety. Only public package names and installed versions transmitted.'}
    try:
        for filename in args.inventories:
            packages=json.loads(Path(filename).read_text(encoding='utf-8-sig'))
            queries=[{'package':{'ecosystem':'PyPI','name':p['name'].lower().replace('_','-').replace('.','-')},'version':p['version']} for p in packages]
            results=query(queries)
            for n,result in enumerate(results):
                ids={v['id'] for v in result.get('vulns',[])}
                token=result.get('next_page_token')
                pages=0
                while token:
                    pages+=1
                    if pages>10:raise ValueError('OSV pagination cap reached')
                    page=query([{**queries[n],'page_token':token}])[0]
                    ids.update(v['id'] for v in page.get('vulns',[]))
                    token=page.get('next_page_token')
                packages[n]['advisory_ids']=sorted(ids)
            report['inventories'][filename]=packages
    except (OSError,ValueError,KeyError,TypeError):
        report['complete']=False
        report['error']='Advisory lookup unavailable or incomplete; not a clean result.'
    report['affected_packages']=sum(bool(p['advisory_ids']) for ps in report['inventories'].values() for p in ps)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='inventories'}))
    if not report['complete'] or report['affected_packages']:raise SystemExit(1)


if __name__=='__main__':main()
