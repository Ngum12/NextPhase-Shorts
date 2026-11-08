"""Readiness through the private TLS edge; never disables certificate validation."""
import argparse
import json
import ssl
from urllib.parse import urlsplit
import httpx


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--url',default='https://edge:8443')
    parser.add_argument('--ca-file',default='/var/nextphase/staging-agent/root.crt');args=parser.parse_args()
    try:
        url=urlsplit(args.url)
        if url.scheme!='https' or url.hostname not in ('edge','localhost','127.0.0.1') or url.username or url.password or url.query or url.fragment or url.path not in ('','/'):raise ValueError()
        with httpx.Client(verify=ssl.create_default_context(cafile=args.ca_file),trust_env=False,follow_redirects=False,timeout=10) as client:
            result=client.get(args.url.rstrip('/')+'/ready')
            if result.status_code!=200 or result.json()!={'ok':True,'service':'nextphase-shorts'}:raise ValueError()
        print(json.dumps({'private_https_readiness':True,'certificate_verification':True}))
    except Exception:parser.exit(1,'Private HTTPS readiness failed; check the private CA, edge and API.\n')

if __name__=='__main__':main()
