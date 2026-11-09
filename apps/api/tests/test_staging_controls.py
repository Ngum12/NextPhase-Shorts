from datetime import datetime,timedelta,timezone
import json
import uuid
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.budget_control import COMPONENTS,reconcile,write_state,require_open
from app.config import get_settings
from app.operator_receiver import app as receiver,validate_traces
from app.operator_agent import deliver
from app.observability import otlp
from app.staging_setup import provision


def fixture_usage(total='0'):
    now=datetime.now(timezone.utc)
    policy={'version':1,'currency':'USD','budget_usd':'10','approved':True,'mode':'local_fixture'}
    usage={'version':1,'currency':'USD','mode':'local_fixture','window_start':(now-timedelta(days=1)).isoformat(),'window_end':(now+timedelta(days=1)).isoformat(),
           'updated_at':now.isoformat(),'components':{name:total if name=='worker' else '0' for name in COMPONENTS}}
    return policy,usage


def test_budget_breach_missing_stale_fixture_production_and_manual_resume_fail_closed(tmp_path,monkeypatch):
    policy,usage=fixture_usage();path=tmp_path/'budget.json';monkeypatch.setattr(get_settings(),'budget_state_file',str(path))
    with pytest.raises(HTTPException):require_open()
    write_state(path,reconcile(policy,usage));require_open()
    usage['components']['worker']='10';write_state(path,reconcile(policy,usage))
    with pytest.raises(HTTPException):require_open()
    usage['components']['worker']='0';write_state(path,reconcile(policy,usage))
    with pytest.raises(HTTPException):require_open()  # No automatic reopening after a spend pause.
    write_state(path,reconcile(policy,usage),allow_resume=True);require_open()
    monkeypatch.setattr(get_settings(),'env','staging')
    with pytest.raises(HTTPException):require_open()
    monkeypatch.setattr(get_settings(),'env','test')
    state=json.loads(path.read_text());state['valid_until']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat();path.write_text(json.dumps(state))
    with pytest.raises(HTTPException):require_open()


def test_incomplete_or_unapproved_provider_costs_never_show_budget_green():
    policy,usage=fixture_usage();policy['approved']=False
    assert reconcile(policy,usage)['reason']=='input_incomplete'
    policy['approved']=True;usage['components'].pop('egress')
    assert reconcile(policy,usage)['paused']
    for bad in ('NaN','-1','Infinity'):
        policy['budget_usd']=bad
        with pytest.raises(Exception):reconcile(policy,usage)


def test_real_admission_pauses_but_login_reads_and_logout_remain_available(client,tmp_path,monkeypatch):
    pair=client.post('/api/v1/auth/register',json={'email':uuid.uuid4().hex+'@example.com','password':'staging-budget-test-password'}).json()
    headers={'Authorization':'Bearer '+pair['access_token']}
    monkeypatch.setattr(get_settings(),'budget_state_file',str(tmp_path/'missing-state'))
    result=client.post('/api/v1/upload-sessions',headers={**headers,'Idempotency-Key':str(uuid.uuid4())},json={
        'file_name':'video.mp4','total_bytes':20,'title':'fixture','style':'vlog','desired_seconds':5,'rights_confirmed':True,'consent_version':'upload-rights-v1'})
    assert result.status_code==503
    assert client.get('/api/v1/me',headers=headers).status_code==200
    assert client.post('/api/v1/auth/logout',headers=headers).status_code==204


def test_receiver_authenticated_idempotent_delivery_redaction_and_private_routes(tmp_path,monkeypatch):
    monkeypatch.setenv('OPERATOR_RECEIVER_TOKEN','synthetic-private-operator-receiver-token')
    monkeypatch.setenv('OPERATOR_RECEIVER_TOKEN_FILE','')
    monkeypatch.setenv('OPERATOR_SINK_DIR',str(tmp_path/'sink'))
    payload=otlp([]);token='synthetic-private-operator-receiver-token'
    with TestClient(receiver) as client:
        assert client.post('/v1/traces',json=payload).status_code==401
        deliver('https://localhost/v1/traces',payload,token,None,client=client)
        deliver('https://localhost/v1/traces',payload,token,None,client=client)
        assert client.get('/docs').status_code==404
        bad={'version':1,'status':'attention_required','issues':['password-secret-value']}
        with pytest.raises(ValueError):deliver('https://localhost/v1/alerts',bad,token,None,client=client)
        import sqlite3
        with sqlite3.connect(tmp_path/'sink/received.sqlite3') as db:
            assert db.execute('SELECT count(*) FROM events').fetchone()[0]==1
            assert token.encode() not in db.execute('SELECT body FROM events').fetchone()[0]
    with pytest.raises(ValueError):deliver('http://localhost/v1/traces',payload,token,None)
    with pytest.raises(ValueError):deliver('https://unapproved.example/v1/traces',payload,token,None)


def test_private_pki_offline_keys_and_existing_directory_preserved(tmp_path):
    roots={role:tmp_path/role for role in ('edge','agent','receiver','offline')}
    for path in roots.values():path.mkdir()
    result=provision(roots);assert not result['publicly_trusted'] and not result['runtime_ca_signing_key']
    assert (roots['offline']/'backup.key').exists() and (roots['offline']/'ca.key').exists()
    assert not (roots['agent']/'ca.key').exists()
    assert (roots['agent']/'receiver.token').read_bytes()==(roots['receiver']/'receiver.token').read_bytes()
    with pytest.raises(ValueError):provision(roots)


def test_final_review_cannot_confuse_local_software_with_external_approval():
    from app.release_review import review,CHECKS,GATES
    report=review({name:True for name in CHECKS},{name:None for name in GATES})
    assert all(report['software_checks'].values()) and not report['release_ready']
    assert set(report['missing_external_gates'])==GATES
    fake={name:{'approved':True,'evidence_sha256':'0'*64,'reviewed_at':'claimed'} for name in GATES}
    assert not review({name:True for name in CHECKS},fake)['release_ready']


def test_real_staging_cannot_omit_budget_gate(monkeypatch):
    monkeypatch.setattr(get_settings(),'env','staging')
    monkeypatch.setattr(get_settings(),'budget_state_file','')
    with pytest.raises(HTTPException):require_open()
