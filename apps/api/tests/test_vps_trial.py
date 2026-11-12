"""Deployment selection and failure gates; no running Docker engine required."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('vps_trial', ROOT / 'scripts/vps_trial.py')
trial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trial)


def setup(root):
    for name in trial.FILES:
        shutil.copyfile(ROOT / name, root / name)
    trial.prepare(root)


@pytest.mark.skipif(os.name != 'posix', reason='Linux VPS preparation only')
def test_prepare_create_only_and_private_credentials(tmp_path):
    previous = os.umask(0o077)
    try:
        setup(tmp_path)
    finally:
        os.umask(previous)
    directory = tmp_path / '.data/vps-trial'
    original = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    assert directory.stat().st_mode & 0o077 == 0
    assert (directory / 'asr').stat().st_mode & 0o777 == 0o755
    assert (directory / 'valkey.conf').stat().st_mode & 0o777 == 0o644
    for name in ('compose.env', 'server.env'):
        assert (directory / name).stat().st_mode & 0o077 == 0
    assert 'localdev' not in (directory / 'compose.env').read_text()
    assert 'GLOBAL_PROCESSING_LIMIT=1\n' in (directory / 'server.env').read_text()
    with pytest.raises(FileExistsError):
        trial.prepare(tmp_path)
    assert original == {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    (directory / 'server.env').chmod(0o644)
    with pytest.raises(ValueError):
        trial.compose_command(tmp_path)


@pytest.mark.skipif(os.name != 'posix', reason='Linux VPS preparation only')
def test_prepare_rejects_linked_directory_and_configuration(tmp_path):
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (tmp_path / '.data').symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError):
        trial.prepare(tmp_path)
    (tmp_path / '.data').unlink()
    setup(tmp_path)
    source = tmp_path / '.data/vps-trial/server.env'
    os.link(source, tmp_path / 'copy')
    with pytest.raises(ValueError):
        trial.compose_command(tmp_path)


@pytest.mark.skipif(os.name != 'posix' or not shutil.which('docker'), reason='Compose CLI needed')
def test_real_compose_resolution_ignores_pc_secrets_and_projects(tmp_path, monkeypatch):
    setup(tmp_path)
    (tmp_path / '.env').write_text('JWT_SECRET=pc-secret-must-not-be-used\nAUTH_MAIL_SEND_ENABLED=true\n')
    monkeypatch.setenv('COMPOSE_PROJECT_NAME', 'owners-live-project')
    monkeypatch.setenv('COMPOSE_PROFILES', 'email')
    monkeypatch.setenv('VPS_DB_PASSWORD', 'wrong-inherited-value')
    monkeypatch.setenv('DOCKER_CONTEXT', 'not-the-local-host')
    monkeypatch.setenv('DOCKER_HOST', 'tcp://unintended.example:2375')
    config = json.loads(trial.run(trial.compose_command(tmp_path) + ['config', '--format', 'json'], tmp_path))
    assert trial.validate_config(config)['private_configuration']
    assert 'pc-secret-must-not-be-used' not in json.dumps(config)
    assert config['services']['db']['environment']['POSTGRES_PASSWORD'] != 'wrong-inherited-value'
    assert not config['services']['queue'].get('ports')
    assert int(config['services']['worker']['mem_limit']) == 2 * 1024**3
    assert float(config['services']['worker']['cpus']) == 2.0
    assert 'default_transaction_read_only' in config['services']['operator-agent']['environment']['DATABASE_URL']
    for mutate in ('public-port', 'limits-off', 'shared-volume', 'mail-enabled', 'host-network'):
        broken = json.loads(json.dumps(config))
        if mutate == 'public-port':
            broken['services']['api']['ports'][0]['host_ip'] = '0.0.0.0'
        elif mutate == 'limits-off':
            broken['services']['worker']['environment']['WORKER_REQUIRE_LIMITS'] = 'false'
        elif mutate == 'shared-volume':
            next(iter(broken['volumes'].values()))['external'] = True
        elif mutate == 'mail-enabled':
            broken['services']['api']['environment']['AUTH_MAIL_SEND_ENABLED'] = 'true'
        else:
            broken['services']['api']['network_mode'] = 'host'
        with pytest.raises(ValueError):
            trial.validate_config(broken)


@pytest.mark.skipif(os.name != 'posix', reason='Linux VPS preparation only')
def test_failed_host_check_stops_before_synthetic_and_diagnostics_are_private(tmp_path, monkeypatch):
    setup(tmp_path)
    calls = []
    def fail(command, root, **kwargs):
        calls.append(command)
        raise ValueError('synthetic-secret-from-subprocess')
    monkeypatch.setattr(trial, 'run', fail)
    result = trial.accept(tmp_path, exercise=True)
    assert result['failure'] == 'trial_check_failed'
    assert not result['public_release_ready']
    assert len(calls) == 1 and 'smoke_e2e.py' not in str(calls)
    report = next((tmp_path / '.data/vps-trial').glob('acceptance-*.json'))
    assert 'synthetic-secret-from-subprocess' not in report.read_text()
    assert report.stat().st_mode & 0o077 == 0


@pytest.mark.skipif(os.name != 'posix', reason='Linux VPS preparation only')
def test_accept_only_runs_synthetic_when_requested(tmp_path, monkeypatch):
    setup(tmp_path)
    monkeypatch.setattr(trial, 'validate_config', lambda config: {})
    calls = []
    def run(command, root, **kwargs):
        calls.append(command)
        if command[-3:] == ['python', '-m', 'app.worker_hostcheck']:
            return '{"ready":true}'
        return '{}'
    monkeypatch.setattr(trial, 'run', run)
    report = trial.accept(tmp_path)
    assert report['trial_checks_passed'] and not report['public_release_ready']
    assert 'synthetic_upload_render_download' not in report['checks']
    report = trial.accept(tmp_path, exercise=True)
    assert report['checks']['synthetic_upload_render_download']
    assert calls[-1][-2:] == ['--base-url', 'http://127.0.0.1:18000']
