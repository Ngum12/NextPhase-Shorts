"""CI setup control flow with fake APT; never install host packages in tests."""
import json
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT=Path(__file__).resolve().parents[3]/'.github/scripts/ensure_ffmpeg.sh'


@pytest.fixture
def setup(tmp_path):
    binary=tmp_path/'bin';binary.mkdir()
    def program(name,body):
        path=binary/name;path.write_text('#!/usr/bin/env python3\n'+body);path.chmod(0o700)
    program('sudo', '''import os,sys
args=sys.argv[1:]
while args and args[0] in ('-n','--'):args.pop(0)
with open(os.environ['SETUP_COMMANDS'],'a') as log:log.write('sudo '+repr(args)+'\\n')
os.execvp(args[0],args)
''')
    program('timeout', '''import json,os,subprocess,sys
args=sys.argv[1:]
while args and args[0].startswith('--'):args.pop(0)
duration=args.pop(0)
with open(os.environ['SETUP_TIMEOUTS'],'a') as log:log.write(json.dumps([duration,*args])+'\\n')
raise SystemExit(subprocess.run(args).returncode)
''')
    program('ffmpeg', '''import os,sys
from pathlib import Path
if not Path(os.environ['SETUP_READY']).exists():raise SystemExit(1)
print(' V..... libx264 fixture\\n A..... aac fixture' if '-encoders' in sys.argv else ' T.C drawtext fixture' if '-filters' in sys.argv else 'ffmpeg fixture')
''')
    program('ffprobe', '''import os
from pathlib import Path
if not Path(os.environ['SETUP_READY']).exists():raise SystemExit(1)
print('ffprobe fixture')
''')
    program('apt-get', '''import json,os,sys
from pathlib import Path
args=sys.argv[1:];action='update' if 'update' in args else 'install'
source=next(arg.split('=',1)[1] for arg in args if arg.startswith('Dir::Etc::sourcelist='))
with open(os.environ['SETUP_APT'],'a') as log:log.write(json.dumps({'action':action,'args':args,'source':Path(source).read_text(),'path':source})+'\\n')
if os.environ.get('SETUP_FAIL')==action:raise SystemExit(int(os.environ.get('SETUP_CODE','100')))
if action=='install' and os.environ.get('SETUP_FAIL')!='verify':Path(os.environ['SETUP_READY']).touch()
''')
    env={**os.environ,'PATH':str(binary)+os.pathsep+os.environ['PATH'],
         'SETUP_COMMANDS':str(tmp_path/'commands'),'SETUP_TIMEOUTS':str(tmp_path/'timeouts'),
         'SETUP_READY':str(tmp_path/'ready'),'SETUP_APT':str(tmp_path/'apt')}
    def run(ready=False,fail='',code=100):
        if ready:Path(env['SETUP_READY']).touch()
        # Override only the OS probe: APT and privilege operations remain mocks.
        shell='source "$1"\nubuntu_codename() { printf "noble\\n"; }\nmain\n'
        result=subprocess.run(['bash','-c',shell,'fixture',str(SCRIPT)],
            env={**env,'SETUP_FAIL':fail,'SETUP_CODE':str(code)},capture_output=True,text=True,timeout=10)
        records=[json.loads(line) for line in Path(env['SETUP_APT']).read_text().splitlines()] if Path(env['SETUP_APT']).exists() else []
        return result,records,env
    return run


def test_working_toolchain_never_calls_sudo_or_apt(setup):
    result,records,env=setup(ready=True)
    assert result.returncode==0,result.stderr
    assert not records and not Path(env['SETUP_COMMANDS']).exists()
    assert 'Using available FFmpeg' in result.stdout


def test_signed_sources_isolated_lists_and_global_deadlines(setup):
    result,records,env=setup()
    assert result.returncode==0,result.stderr
    assert [r['action'] for r in records]==['update','install']
    for record in records:
        assert 'azure' not in record['source'] and 'mirror+file' not in record['source']
        assert 'https://archive.ubuntu.com/ubuntu noble ' in record['source']
        assert 'https://security.ubuntu.com/ubuntu noble-security ' in record['source']
        assert 'signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg' in record['source']
        assert 'APT::Update::Error-Mode=any' in record['args']
        assert 'Acquire::Languages=none' in record['args']
        assert 'Acquire::https::Timeout=20' in record['args']
        assert 'Dir::Etc::sourceparts=-' in record['args']
        assert not Path(record['path']).exists()  # Temporary lists are removed on success.
    assert '--no-install-recommends' in records[-1]['args']
    timeouts=[json.loads(line) for line in Path(env['SETUP_TIMEOUTS']).read_text().splitlines()]
    assert any(t[0]=='90s' and t[1]=='apt-get' for t in timeouts)
    assert any(t[0]=='240s' and t[1]=='apt-get' for t in timeouts)


@pytest.mark.parametrize('action,code',[('update',100),('update',124),('install',100),('install',124)])
def test_fetch_failure_or_timeout_fails_setup_and_cleans_own_lists(setup,action,code):
    result,records,_=setup(fail=action,code=code)
    assert result.returncode==code,result.stderr
    assert [r['action'] for r in records]==(['update'] if action=='update' else ['update','install'])
    assert all(not Path(record['path']).exists() for record in records)
    assert 'Using available FFmpeg' not in result.stdout


def test_install_exit_zero_is_not_enough_without_working_encoders(setup):
    result,records,_=setup(fail='verify')
    assert result.returncode==1
    assert len(records)==2 and 'FFmpeg setup failed' in result.stderr
