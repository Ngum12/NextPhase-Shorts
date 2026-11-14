import importlib.util
from pathlib import Path
import stat
import pytest

spec=importlib.util.spec_from_file_location('configure_gemini',Path(__file__).resolve().parents[3]/'scripts/configure_gemini.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_private_configuration_preserves_credentials_and_does_not_print_key(tmp_path,capsys):
    directory=tmp_path/'.data/vps-trial';directory.mkdir(parents=True,mode=0o700)
    target=directory/'server.env';target.write_text('JWT_SECRET=keep-private\nQUEUE_PASSWORD=keep-queue\nGEMINI_API_KEY=old\nGEMINI_API_KEY_FILE=/old\nGEMINI_PLANNING_ENABLED=false\n')
    target.chmod(0o600)
    module.configure(tmp_path,'synthetic-key-12345')
    value=target.read_text()
    assert 'JWT_SECRET=keep-private\nQUEUE_PASSWORD=keep-queue' in value
    assert 'GEMINI_API_KEY_FILE' not in value
    assert value.count('GEMINI_API_KEY=')==1
    assert 'GEMINI_PLANNING_ENABLED=true' in value
    assert 'GEMINI_FREE_TIER_CONFIRMED=true' in value
    assert stat.S_IMODE(target.stat().st_mode)==0o600
    assert not capsys.readouterr().out


@pytest.mark.parametrize('issue',['symlink','public','invalid','hardlink'])
def test_unsafe_targets_and_keys_are_refused(tmp_path,issue):
    directory=tmp_path/'.data/vps-trial';directory.mkdir(parents=True,mode=0o700)
    target=directory/'server.env';target.write_text('JWT_SECRET=keep');target.chmod(0o600)
    if issue=='symlink':target.rename(directory/'original');target.symlink_to(directory/'original')
    if issue=='hardlink':(directory/'second').hardlink_to(target)
    if issue=='public':target.chmod(0o644)
    with pytest.raises(ValueError):module.configure(tmp_path,'invalid\nKEY=value' if issue=='invalid' else 'synthetic-key-12345')
