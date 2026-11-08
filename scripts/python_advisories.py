"""Check installed Python versions against official PyPI published advisory metadata.

Not an OS/container/native scan or independent security certification.
"""
from concurrent.futures import ThreadPoolExecutor
import importlib.metadata
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request


def check(item):
    name,version=item
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',name):raise ValueError('Invalid distribution name')
    url='https://pypi.org/pypi/'+urllib.parse.quote(name,safe='')+'/'+urllib.parse.quote(version,safe='')+'/json'
    try:
        with urllib.request.urlopen(url,timeout=20) as response:data=response.read(2*1024*1024+1)
        if len(data)>2*1024*1024:raise ValueError()
        payload=json.loads(data)
        if 'vulnerabilities' not in payload or not isinstance(payload['vulnerabilities'],list):raise ValueError()
        advisory=[row.get('id','unknown') for row in payload['vulnerabilities'] if not row.get('withdrawn')]
        return {'name':name,'version':version,'status':'findings' if advisory else 'no_published_findings','advisory_ids':advisory}
    except Exception:return {'name':name,'version':version,'status':'unavailable','advisory_ids':[]}


def main():
    import argparse,os
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    packages=sorted({(dist.metadata['Name'],dist.version) for dist in importlib.metadata.distributions()})
    with ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(check,packages))
    result={'version':1,'source':'official PyPI version JSON vulnerabilities metadata','packages':rows,
        'findings':sum(row['status']=='findings' for row in rows),'unavailable':sum(row['status']=='unavailable' for row in rows),
        'scope':'installed cloud Python versions only; no full image/OS/native/legal clearance'}
    args.output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    descriptor=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as handle:json.dump(result,handle,indent=2)
    print(json.dumps({key:result[key] for key in ('findings','unavailable','scope')}))
    raise SystemExit(1 if result['findings'] else 2 if result['unavailable'] else 0)

if __name__=='__main__':main()
