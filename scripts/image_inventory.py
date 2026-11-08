"""Read-only inventory of an existing local application image, never a security signoff."""
import argparse,json,os,re,subprocess,sys
from pathlib import Path

PROGRAM=r'''
import hashlib,importlib.metadata as m,json,platform,subprocess,sysconfig
from pathlib import Path
os_release={}
for line in Path('/etc/os-release').read_text().splitlines():
    if '=' in line:
        key,value=line.split('=',1)
        if key in ('ID','VERSION_ID'):os_release[key]=value.strip('"')
rows=subprocess.check_output(['dpkg-query','-W','-f','${Package}\t${Version}\t${Architecture}\t${source:Package}\t${source:Version}\n'],text=True,timeout=30)
packages=[]
for line in rows.splitlines():
    name,version,arch,source,source_version=(line.split('\t')+['']*5)[:5]
    notice=Path('/usr/share/doc')/name/'copyright'
    packages.append({'name':name,'version':version,'architecture':arch,'source_package':source,
        'source_version':source_version,'copyright_sha256':hashlib.sha256(notice.read_bytes()).hexdigest() if notice.is_file() else None})
python=[{'name':d.metadata['Name'],'version':d.version,'declared_license':d.metadata.get('License-Expression') or None} for d in m.distributions(path=[sysconfig.get_paths()['purelib']])]
ffmpeg=subprocess.check_output(['ffmpeg','-version'],text=True,stderr=subprocess.DEVNULL,timeout=10).splitlines()
print(json.dumps({'os':os_release,'python_version':platform.python_version(),'os_packages':packages,
    'python_packages':sorted(python,key=lambda x:x['name'].lower()),'ffmpeg_version':ffmpeg[0],
    'ffmpeg_configuration':next((line for line in ffmpeg if line.startswith('configuration:')),''),
    'scope':'Installed packages and copyright hashes; not full embedded/native SBOM, vulnerability scan, source offer or legal approval'}))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='nextphase-shorts-worker')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:@-]{0,255}',args.image):parser.error('Use an existing local image name or ID')
    env=os.environ.copy()
    for key in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH'):env.pop(key,None)
    docker=['docker','--context','default'] if os.name=='nt' else ['docker','--host=unix:///var/run/docker.sock']
    try:
        # Inspect first and run the immutable local ID, with no pull or service env/mounts.
        identity=subprocess.check_output(docker+['image','inspect','--format','{{.Id}}',args.image],env=env,text=True,stderr=subprocess.DEVNULL,timeout=15).strip()
        if not re.fullmatch(r'sha256:[0-9a-f]{64}',identity):raise ValueError()
        result=subprocess.run(docker+['run','--rm','--pull','never','-i','--network','none','--read-only','--cap-drop','ALL',
            '--security-opt','no-new-privileges:true','--pids-limit','128','--memory','256m','--cpus','1',
            '--entrypoint','python',identity,'-I','-S','-'],input=PROGRAM,env=env,text=True,capture_output=True,check=True,timeout=90)
        if len(result.stdout)>2**20:raise ValueError()
        inventory=json.loads(result.stdout)
        payload={'schema_version':1,'image_id':identity,'inventory':inventory,'vulnerability_scan_completed':False,'license_review_completed':False}
        descriptor=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'w',encoding='utf-8') as handle:json.dump(payload,handle,indent=2);handle.write('\n')
        print(json.dumps({'inventory_written':True,'os_packages':len(inventory['os_packages']),
            'python_packages':len(inventory['python_packages']),'scope':'inventory only; no approval or vulnerability scan inferred'}))
    except (OSError,ValueError,subprocess.SubprocessError,KeyError):
        print('Image inventory unavailable; use a local image and a new private output file.',file=sys.stderr);raise SystemExit(1)

if __name__=='__main__':main()
