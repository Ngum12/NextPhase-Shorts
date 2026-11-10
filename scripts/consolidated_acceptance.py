"""One local acceptance report for backups, TLS staging, operations and review.

Runs isolated fixtures only. No public hosting, provider billing or real email.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import uuid
import zipfile
ROOT=Path(__file__).resolve().parents[1]


def caddy_binary():
    system=platform.system().lower();machine=platform.machine().lower()
    arch={'x86_64':'amd64','amd64':'amd64','aarch64':'arm64','arm64':'arm64'}.get(machine)
    if system not in ('linux','windows','darwin') or not arch:raise RuntimeError('Provide an official supported Caddy binary with --caddy')
    extension='zip' if system=='windows' else 'tar.gz';name=f'caddy_2.11.9_{system}_{arch}.{extension}'
    checks=(ROOT/'deploy/private-staging/caddy-2.11.9-checksums.txt').read_text().splitlines()
    expected=next(line.split()[0] for line in checks if line.split()[-1].lstrip('*')==name)
    directory=Path(tempfile.mkdtemp(prefix='nextphase-caddy-verified-'));archive=directory/('release.'+extension)
    request=urllib.request.Request('https://github.com/caddyserver/caddy/releases/download/v2.11.9/'+name)
    with urllib.request.urlopen(request,timeout=60) as response,archive.open('xb') as out:
        size=0
        while block:=response.read(1024*1024):
            size+=len(block)
            if size>64*1024*1024:raise RuntimeError('Tool download too large')
            out.write(block)
    if hashlib.sha512(archive.read_bytes()).hexdigest()!=expected:raise RuntimeError('Caddy release checksum mismatch')
    member='caddy.exe' if system=='windows' else 'caddy';target=directory/member
    if extension=='zip':
        with zipfile.ZipFile(archive) as container:target.write_bytes(container.read(member))
    else:
        with tarfile.open(archive) as container:
            item=container.getmember(member)
            if not item.isfile():raise RuntimeError('Invalid binary entry')
            target.write_bytes(container.extractfile(item).read())
    target.chmod(0o700);archive.unlink();return str(target),directory


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--caddy');parser.add_argument('--postgres',action='store_true')
    parser.add_argument('--review-evidence',type=Path,default=ROOT/'deploy/private-staging/release-evidence.example.json')
    args=parser.parse_args()
    if os.name=='nt':raise SystemExit('Run this Linux acceptance runner in CI/cloud or a Linux environment; use the documented Docker profile for Windows host activation.')
    caddy=args.caddy;owned=None
    if not caddy:caddy,owned=caddy_binary()
    evidence=ROOT/'.data'/('consolidated-acceptance-'+uuid.uuid4().hex);evidence.mkdir(parents=True,mode=0o700)
    env={**os.environ,'PYTHONPATH':str(ROOT/'apps/api'),'BUDGET_STATE_FILE':''}
    checks={key:False for key in ('encrypted_restore','private_https_renderer','monitoring_delivery','budget_admission_gate','regression_suite')}
    try:
        def run(label,command):
            with (evidence/(label+'.log')).open('w') as log:
                result=subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
            if result.returncode:raise RuntimeError(label+' failed; inspect private log')
        run('backend-tests',[sys.executable,'-m','pytest','apps/api/tests','-q']);checks['regression_suite']=True
        command=[sys.executable,'scripts/smoke_restore_journal.py','--encrypted-backup']
        if args.postgres:command+=['--postgres']
        run('encrypted-restore',command);checks['encrypted_restore']=True
        run('private-staging',[sys.executable,'scripts/private_staging_smoke.py','--caddy',caddy])
        run('trial-https-routing',[sys.executable,'scripts/smoke_trial_https.py','--caddy',caddy])
        checks.update(private_https_renderer=True,monitoring_delivery=True,budget_admission_gate=True)
    finally:
        sys.path.insert(0,str(ROOT/'apps/api'))
        from app.release_review import review
        approval=json.loads(args.review_evidence.read_bytes())
        result=review(checks,approval['approvals'])
        result['source_commit']=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()
        result['working_tree_dirty']=bool(subprocess.run(['git','status','--porcelain'],cwd=ROOT,capture_output=True,text=True,check=True).stdout)
        fingerprint=hashlib.sha256()
        for folder in ('apps/api/app','scripts','deploy'):
            for source in sorted((ROOT/folder).rglob('*')):
                if source.is_file() and source.suffix in ('.py','.yaml','.json','.ps1') or source.is_file() and source.name=='Caddyfile':
                    fingerprint.update(source.relative_to(ROOT).as_posix().encode()+b'\0'+source.read_bytes())
        result['software_tree_sha256']=fingerprint.hexdigest()
        (evidence/'report.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result));print('Evidence:',evidence)
        if owned:
            import shutil;shutil.rmtree(owned)
    if not all(checks.values()):raise SystemExit(1)

if __name__=='__main__':main()
