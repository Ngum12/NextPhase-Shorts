"""Model Windows' open-file cleanup refusal in an isolated real smoke process."""
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('fail_after_database_use',[False,True])
def test_worker_smoke_releases_database_before_temp_cleanup(fail_after_database_use):
    root=Path(__file__).resolve().parents[3]
    code=r'''
import runpy,sys,tempfile,subprocess
from pathlib import Path
original=tempfile.TemporaryDirectory
checked=[]
class WindowsLikeDirectory(original):
    def cleanup(self):
        if Path(self.name).name.startswith('nextphase-worker-smoke-'):
            db=sys.modules.get('app.db')
            assert db is not None
            # Linux can unlink a live SQLite DB; Windows cannot. Require that
            # no checked-out or pooled idle connection survives this boundary.
            assert db.engine.pool.checkedout()==0,'SQLite connection still checked out'
            assert db.engine.pool.checkedin()==0,'SQLite pool still holds file handles'
            checked.append(self.name)
        return super().cleanup()
tempfile.TemporaryDirectory=WindowsLikeDirectory
actual_run=subprocess.run
fail=sys.argv[2]=='True'
def run(command,*args,**kwargs):
    if fail and command[0]=='ffmpeg' and 'null' in command:
        raise RuntimeError('synthetic failure after DB use')
    return actual_run(command,*args,**kwargs)
subprocess.run=run
try:
    runpy.run_path(sys.argv[1],run_name='__main__')
except RuntimeError as error:
    assert fail and str(error)=='synthetic failure after DB use'
else:
    assert not fail
assert checked and all(not Path(name).exists() for name in checked)
print('SQLite handles released before temporary cleanup')
'''
    result=subprocess.run([sys.executable,'-c',code,str(root/'scripts/smoke_worker_recovery.py'),str(fail_after_database_use)],
        cwd=root,capture_output=True,text=True,timeout=90)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'SQLite handles released before temporary cleanup' in result.stdout
