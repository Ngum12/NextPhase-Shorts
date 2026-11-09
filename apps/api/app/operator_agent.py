"""Explicit private TLS export of fixed traces and coarse alerts; no paid sender."""
import argparse
import hashlib
import json
import ssl
import time
from urllib.parse import urlsplit
import httpx
from .secret_config import read_secret


def deliver(endpoint,payload,token,ca_file,*,client=None):
    url=urlsplit(endpoint)
    if url.scheme!='https' or url.hostname not in ('localhost','127.0.0.1','edge') or url.username or url.password or url.query or url.fragment or url.path not in ('/v1/traces','/v1/alerts') or len(token)<32:raise ValueError('Private TLS operator endpoint required')
    raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(raw)>2*1024*1024:raise ValueError('Delivery batch too large')
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json','X-NextPhase-Delivery':hashlib.sha256(raw).hexdigest()}
    def send(transport):
        response=transport.post(endpoint,headers=headers,content=raw)
        if response.status_code!=200 or response.json()!={'accepted':True,'kind':url.path.rsplit('/',1)[1]}:raise ValueError('Delivery not acknowledged')
    if client is not None:send(client)
    else:
        with httpx.Client(verify=ssl.create_default_context(cafile=str(ca_file)),trust_env=False,follow_redirects=False,timeout=10) as transport:send(transport)


def once(base_url,ca_file,*,rates=None,ceiling=None):
    from .db import engine,SessionLocal
    from .migrate import require_current_schema
    from .monitoring import snapshot
    from .observability import export
    from .models import utcnow
    from datetime import timedelta
    require_current_schema(engine);token=read_secret('OPERATOR_RECEIVER_TOKEN','')
    with SessionLocal() as db:
        report=snapshot(db,rates=rates,ceiling=ceiling,check_disk=False)
        traces=export(db,limit=1000,since_ns=int((utcnow()-timedelta(minutes=5)).timestamp()*1e9))
    alerts={'version':1,'status':report['status'],'issues':report['issues']}
    deliver(base_url.rstrip('/')+'/v1/traces',traces,token,ca_file)
    deliver(base_url.rstrip('/')+'/v1/alerts',alerts,token,ca_file)
    return {'delivered':True,'status':report['status'],'scope':'private local receiver; not human notification/provider billing'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url',required=True);parser.add_argument('--ca-file',required=True)
    parser.add_argument('--rates');parser.add_argument('--cost-alert-usd');parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    from .costs import load_rates
    from decimal import Decimal
    while True:
        try:result=once(args.url,args.ca_file,rates=load_rates(args.rates),ceiling=Decimal(args.cost_alert_usd) if args.cost_alert_usd else None)
        except Exception:result={'delivered':False,'status':'unavailable'}
        print(json.dumps(result),flush=True)
        if args.once:raise SystemExit(0 if result['delivered'] else 1)
        time.sleep(60)

if __name__=='__main__':main()
