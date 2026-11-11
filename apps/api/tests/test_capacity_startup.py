"""Disposable capacity fixture must be ready for host TCP SQL, not just a socket."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import psycopg
import pytest

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('capacity_exercise',ROOT/'scripts/capacity_exercise.py')
capacity=importlib.util.module_from_spec(spec);spec.loader.exec_module(capacity)


class Connection:
    def __init__(self, *, query_error=False, row=(1,)):
        self.query_error=query_error;self.row=row;self.closed=False
    def __enter__(self):return self
    def __exit__(self,*args):self.closed=True
    def execute(self,sql):
        assert sql=='SELECT 1'
        if self.query_error:raise psycopg.OperationalError('fixture restarting')
        return SimpleNamespace(fetchone=lambda:self.row)


def clock(monkeypatch):
    now=[0.0]
    monkeypatch.setattr(capacity.time,'monotonic',lambda:now[0])
    monkeypatch.setattr(capacity.time,'sleep',lambda seconds:now.__setitem__(0,now[0]+seconds))
    return now


def test_waits_through_initialization_restart_for_authenticated_host_query(monkeypatch):
    now=clock(monkeypatch);calls=[];connection=Connection()
    def connect(**kwargs):
        calls.append(kwargs)
        if len(calls)<3:raise psycopg.OperationalError('temporary server gone')
        return connection
    monkeypatch.setattr(capacity.psycopg,'connect',connect)
    capacity.wait_for_postgres('32771')
    assert len(calls)==3 and connection.closed and now[0]>.0
    assert all(c['host']=='127.0.0.1' and c['port']==32771 and c['dbname']=='source_test'
               and c['user']=='postgres' and c['connect_timeout']==2 for c in calls)


def test_query_itself_must_succeed_before_readiness(monkeypatch):
    clock(monkeypatch);failed=Connection(query_error=True);ready=Connection()
    connections=iter([failed,ready])
    monkeypatch.setattr(capacity.psycopg,'connect',lambda **kwargs:next(connections))
    capacity.wait_for_postgres(32771)
    assert failed.closed and ready.closed


def test_timeout_is_bounded_and_does_not_echo_connection_error(monkeypatch):
    now=clock(monkeypatch)
    def fail(**kwargs):raise psycopg.OperationalError('private-diagnostic-fixture')
    monkeypatch.setattr(capacity.psycopg,'connect',fail)
    with pytest.raises(RuntimeError,match='TCP/SQL readiness') as error:
        capacity.wait_for_postgres(32771,timeout=.5)
    assert now[0]==pytest.approx(.5)
    assert 'private-diagnostic-fixture' not in str(error.value)
    assert error.value.__suppress_context__


def test_unexpected_query_result_is_not_retried(monkeypatch):
    clock(monkeypatch)
    monkeypatch.setattr(capacity.psycopg,'connect',lambda **kwargs:Connection(row=(0,)))
    with pytest.raises(RuntimeError,match='Unexpected'):capacity.wait_for_postgres(32771)


def test_postgres_diagnostic_contains_only_selected_state_fields(tmp_path,monkeypatch):
    import json
    state={'Status':'exited','Running':False,'ExitCode':1,'OOMKilled':True,
           'StartedAt':'start','FinishedAt':'end','Error':'private-diagnostic-fixture'}
    monkeypatch.setattr(capacity.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(state)))
    capacity.postgres_diagnostic(['docker'],'fixture',{},tmp_path)
    output=(tmp_path/'postgres-state.json').read_text()
    assert json.loads(output)['oom_killed'] is True
    assert 'private-diagnostic-fixture' not in output
