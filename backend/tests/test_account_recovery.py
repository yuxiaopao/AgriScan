"""Real account/OTP/worker integration with controlled SMTP, never external mail."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from time import monotonic, sleep
import hashlib
import hmac
import ssl

import pytest
from sqlalchemy import select

from app.account_recovery import INVALID_CODE, RESET_MESSAGE, verified_key
from app.db import AppMeta, User, utcnow
from app.extensions import EmailChallenge, UserEmail, send_code
from test_api import auth, client
from test_extensions import account
from test_detection_tasks import Probe, reserve, submit, wait_task


def mail_setup(client, monkeypatch, verification=False):
    settings = client.app.state.settings
    settings.smtp_host = 'smtp.synthetic.invalid';settings.smtp_port = 465
    settings.smtp_from = 'service@synthetic.invalid';settings.smtp_username = 'service@synthetic.invalid'
    settings.smtp_password = 'SYNTHETIC-SMTP-ONLY';settings.smtp_security = 'ssl'
    settings.email_verification_enabled = verification
    sent = []
    monkeypatch.setattr('app.extensions.send_code', lambda settings,email,code,purpose='register':sent.append((email,code,purpose)))
    return sent


def drain(client):
    client.app.state.email_mailer.executor.submit(lambda: None).result(timeout=4)


def add_account(client, email='field@example.com', username='field_member', verified=True):
    response = client.post('/api/auth/register', json=account(username=username,email=email))
    assert response.status_code == 201, response.text
    with client.app.state.session() as db:
        user=db.scalar(select(User).where(User.username==username));user_id=user.id
        if verified:db.merge(AppMeta(key=verified_key(email),value=user.id));db.commit()
    token=client.post('/api/auth/login',json=account(username=username)).json()['access_token']
    return user_id,{'Authorization':'Bearer '+token}


def reset_request(client,email='field@example.com'):
    return client.post('/api/auth/password-reset-code',json={'email':email})


def reset(client,code,email='field@example.com',new_password='replacement-password-2026'):
    return client.post('/api/auth/password-reset',json={'email':email,'code':code,'new_password':new_password})


def bind_request(client,headers,email='new@example.com'):
    return client.post('/api/auth/email/verification-code',headers=headers,json={'email':email})


def bind(client,headers,code,email='new@example.com',current_password='strong-test-password'):
    return client.post('/api/auth/email/verify',headers=headers,json={'email':email,'code':code,'current_password':current_password})


def challenge_key(client,purpose,email,user_id=''):
    value=hmac.new(client.app.state.settings.jwt_secret.encode(),(user_id+':'+email).encode(),hashlib.sha256).hexdigest()
    return ('reset:' if purpose=='reset' else 'bind:')+value


def test_reset_availability_is_smtp_complete_and_independent_of_registration(client,monkeypatch):
    assert not client.get('/api/auth/config').json()['password_reset_enabled']
    sent=mail_setup(client,monkeypatch)
    client.app.state.settings.registration_enabled=False
    config=client.get('/api/auth/config').json()
    assert config['password_reset_enabled'] and not config['registration_enabled']
    assert 'SYNTHETIC' not in str(config) and 'smtp_' not in str(config)
    assert reset_request(client,'unknown@example.com').json()=={'message':RESET_MESSAGE}
    drain(client);assert sent==[]


def test_unknown_legacy_unverified_and_inactive_emails_share_response_without_mail(client,monkeypatch):
    sent=mail_setup(client,monkeypatch)
    add_account(client,verified=False)
    inactive,_=add_account(client,email='inactive@example.com',username='inactive_member')
    with client.app.state.session() as db:db.get(User,inactive).is_active=False;db.commit()
    for email in ['missing@example.com','field@example.com','inactive@example.com']:
        response=reset_request(client,email)
        assert response.status_code==200 and response.json()=={'message':RESET_MESSAGE}
        assert reset(client,'123456',email=email).status_code==400
        assert reset(client,'123456',email=email).json()=={'detail':INVALID_CODE}
    drain(client);assert sent==[]


def test_verified_registration_marks_only_proven_email_and_code_is_not_reset_proof(client,monkeypatch):
    sent=mail_setup(client,monkeypatch,verification=True)
    email='proven@example.com'
    assert client.post('/api/auth/email-code',json={'email':email}).status_code==200
    code=sent[-1][1]
    assert client.post('/api/auth/register',json=account(email=email,code=code)).status_code==201
    headers={'Authorization':'Bearer '+client.post('/api/auth/login',json=account()).json()['access_token']}
    assert client.get('/api/auth/email',headers=headers).json()=={'email':email,'verified':True}
    with client.app.state.session() as db:
        binding=db.get(UserEmail,email);assert db.get(AppMeta,verified_key(email)).value==binding.user_id
        assert len(verified_key(email))==79
    assert reset(client,code,email=email).status_code==400


def test_password_reset_consumes_otp_revokes_all_tokens_and_does_not_login(client,monkeypatch):
    sent=mail_setup(client,monkeypatch)
    user_id,headers=add_account(client)
    second={'Authorization':'Bearer '+client.post('/api/auth/login',json=account()).json()['access_token']}
    assert reset_request(client).status_code==200;drain(client)
    assert sent[-1][2]=='password_reset'
    code=sent[-1][1]
    with client.app.state.session() as db:
        row=db.get(EmailChallenge,challenge_key(client,'reset','field@example.com'))
        assert row.digest!=code and 'field@example.com' not in row.email
    result=reset(client,code)
    assert result.status_code==200 and set(result.json())=={'message'} and 'access_token' not in result.text
    assert client.get('/api/auth/me',headers=headers).status_code==401
    assert client.get('/api/auth/me',headers=second).status_code==401
    assert reset(client,code).status_code==400
    assert client.post('/api/auth/login',json=account()).status_code==401
    assert client.post('/api/auth/login',json=account(password='replacement-password-2026')).status_code==200
    with client.app.state.session() as db:assert db.get(User,user_id).token_version==1


def test_resend_invalidates_previous_code_and_60second_cooldown_is_generic(client,monkeypatch):
    sent=mail_setup(client,monkeypatch);add_account(client)
    values=iter([123456,654321])
    monkeypatch.setattr('app.account_recovery.secrets.randbelow',lambda maximum:next(values))
    reset_request(client);drain(client);first=sent[-1][1]
    assert reset_request(client).json()=={'message':RESET_MESSAGE};drain(client);assert len(sent)==1
    with client.app.state.session() as db:
        db.get(EmailChallenge,challenge_key(client,'reset','field@example.com')).sent_at-=timedelta(seconds=61);db.commit()
    reset_request(client);drain(client);second=sent[-1][1]
    assert reset(client,first).status_code==400
    assert reset(client,second).status_code==200


def test_expiry_and_five_attempts_enforced_even_with_correct_code(client,monkeypatch):
    sent=mail_setup(client,monkeypatch);add_account(client)
    reset_request(client);drain(client);code=sent[-1][1];wrong='111111' if code!='111111' else '222222'
    for _ in range(5):assert reset(client,wrong).status_code==400
    assert reset(client,code).status_code==400
    with client.app.state.session() as db:
        row=db.get(EmailChallenge,challenge_key(client,'reset','field@example.com'));row.sent_at-=timedelta(seconds=61);db.commit()
    reset_request(client);drain(client);code=sent[-1][1]
    with client.app.state.session() as db:
        db.get(EmailChallenge,challenge_key(client,'reset','field@example.com')).expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert reset(client,code).status_code==400


def test_reset_code_ip_limit_applies_equally_to_unknown_accounts(client,monkeypatch):
    sent=mail_setup(client,monkeypatch)
    for index in range(8):assert reset_request(client,f'unknown{index}@example.com').status_code==200
    assert reset_request(client,'ninth@example.com').status_code==429
    drain(client);assert not sent


def test_two_simultaneous_reset_replays_have_one_success(client,monkeypatch):
    sent=mail_setup(client,monkeypatch);add_account(client)
    reset_request(client);drain(client);code=sent[-1][1]
    with ThreadPoolExecutor(2) as pool:
        replies=list(pool.map(lambda _:reset(client,code).status_code,range(2)))
    assert sorted(replies)==[200,400]


def test_binding_legacy_email_proves_current_password_preserves_token_and_enables_reset(client,monkeypatch):
    sent=mail_setup(client,monkeypatch)
    _,headers=add_account(client,verified=False)
    assert client.get('/api/auth/email',headers=headers).json()=={'email':'field@example.com','verified':False}
    assert bind_request(client,headers,'field@example.com').status_code==200;drain(client);code=sent[-1][1]
    assert sent[-1][2]=='email_bind'
    assert bind(client,headers,code,email='field@example.com',current_password='wrong-password').status_code==400
    response=bind(client,headers,code,email='field@example.com')
    assert response.status_code==200 and response.json()['verified']
    assert client.get('/api/auth/me',headers=headers).status_code==200
    assert client.get('/api/auth/email',headers=headers).json()['verified']
    reset_request(client);drain(client);assert sent[-1][2]=='password_reset'


def test_binding_code_is_bound_to_user_and_purpose_and_cannot_steal_email(client,monkeypatch):
    sent=mail_setup(client,monkeypatch)
    _,one=add_account(client)
    _,two=add_account(client,email='second@example.com',username='second_member',verified=False)
    bind_request(client,one);drain(client);code=sent[-1][1]
    assert bind(client,two,code).status_code==400
    assert reset(client,code,email='new@example.com').status_code==400
    assert bind(client,one,code).status_code==200
    before=len(sent);bind_request(client,two);drain(client)
    assert len(sent)==before
    assert bind(client,two,code).status_code==400
    assert client.get('/api/auth/email',headers=one).json()['email']=='new@example.com'


def test_rebind_clears_old_marker_and_pending_reset_code(client,monkeypatch):
    sent=mail_setup(client,monkeypatch)
    user_id,headers=add_account(client)
    reset_request(client);drain(client);old_reset=sent[-1][1]
    bind_request(client,headers);drain(client);code=sent[-1][1]
    assert bind(client,headers,code).status_code==200
    with client.app.state.session() as db:
        assert db.get(UserEmail,'field@example.com') is None
        assert db.get(AppMeta,verified_key('field@example.com')) is None
        assert db.get(AppMeta,verified_key('new@example.com')).value==user_id
    assert reset(client,old_reset).status_code==400
    assert client.get('/api/auth/email',headers=headers).json()=={'email':'new@example.com','verified':True}


def test_smtp_failure_is_generic_and_invalidates_only_matching_challenge(client,monkeypatch):
    sent=mail_setup(client,monkeypatch);add_account(client)
    def fail(*args):raise RuntimeError('SYNTHETIC-provider-password-and-address-must-not-escape')
    monkeypatch.setattr('app.extensions.send_code',fail)
    response=reset_request(client);drain(client)
    assert response.status_code==200 and response.json()=={'message':RESET_MESSAGE}
    assert 'SYNTHETIC' not in response.text
    with client.app.state.session() as db:
        row=db.get(EmailChallenge,challenge_key(client,'reset','field@example.com'));assert row.expires_at<=utcnow()


def test_smtp_latency_is_off_request_path_and_queue_is_bounded(client,monkeypatch):
    sent=mail_setup(client,monkeypatch);add_account(client)
    entered,release=Event(),Event()
    def delayed(*args):entered.set();assert release.wait(4)
    monkeypatch.setattr('app.extensions.send_code',delayed)
    try:
        started=monotonic();response=reset_request(client)
        assert response.status_code==200 and monotonic()-started<1
        assert entered.wait(1)
        assert client.get('/api/health').status_code==200
        queue=client.app.state.email_mailer
        occupied=sum(queue.submit(lambda:release.wait(4)) for _ in range(12))
        assert occupied==7
    finally:release.set();drain(client)


def test_validation_never_echoes_password_or_otp_input(client,monkeypatch):
    mail_setup(client,monkeypatch)
    body={'email':'bad-email','code':'OTP-SHOULD-NOT-ECHO','new_password':'PASSWORD-SHOULD-NOT-ECHO'}
    response=client.post('/api/auth/password-reset',json=body)
    assert response.status_code==422 and 'OTP-SHOULD-NOT-ECHO' not in response.text and 'PASSWORD-SHOULD-NOT-ECHO' not in response.text
    response=client.post('/api/auth/email/verify',headers=auth(client),json={'email':'bad','code':'OTP-SECRET','current_password':'CURRENT-PASSWORD-SECRET'})
    assert response.status_code==422 and 'OTP-SECRET' not in response.text and 'CURRENT-PASSWORD-SECRET' not in response.text
    response=client.post('/api/auth/register',json=account(username='!',password='REGISTER-SECRET',code='OTP-SECRET'))
    assert response.status_code==422 and 'REGISTER-SECRET' not in response.text and 'OTP-SECRET' not in response.text


def test_reset_cancels_all_sessions_tasks_without_saving_running_inference(client,monkeypatch):
    sent=mail_setup(client,monkeypatch);user_id,headers=add_account(client)
    probe=Probe();probe.release.clear();client.app.state.inference=probe
    first=submit(client,headers);assert probe.entered.wait(2)
    second={'Authorization':'Bearer '+client.post('/api/auth/login',json=account()).json()['access_token']}
    pending=reserve(client,second)[0].json()['id']
    try:
        reset_request(client);drain(client);response=reset(client,sent[-1][1]);assert response.status_code==200
        assert client.app.state.detection_tasks.tasks[pending].status=='cancelled'
        assert client.get('/api/auth/me',headers=headers).status_code==401
    finally:probe.release.set()
    deadline=monotonic()+3
    while client.app.state.detection_tasks.tasks[first].status=='cancelling' and monotonic()<deadline:sleep(.02)
    assert client.app.state.detection_tasks.tasks[first].status=='cancelled'
    fresh={'Authorization':'Bearer '+client.post('/api/auth/login',json=account(password='replacement-password-2026')).json()['access_token']}
    assert client.get('/api/detections',headers=fresh).json()==[]


def test_binding_requires_auth_and_rechecks_invalidated_identity(client,monkeypatch):
    sent=mail_setup(client,monkeypatch)
    assert client.get('/api/auth/email').status_code==401
    assert bind_request(client,{}).status_code==401
    user_id,headers=add_account(client)
    bind_request(client,headers);drain(client);code=sent[-1][1]
    with client.app.state.session() as db:db.get(User,user_id).token_version+=1;db.commit()
    assert bind(client,headers,code).status_code==401


def test_send_code_uses_tls_login_and_purpose_specific_subject_without_external_mail(client,monkeypatch):
    mail_setup(client,monkeypatch)
    client.app.state.runtime_config.refresh()
    calls=[]
    class SMTP:
        def __init__(self,host,port,**kwargs):calls.append(('connect',host,port,kwargs))
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def login(self,*args):calls.append(('login',args))
        def send_message(self,message):calls.append(('message',message))
    monkeypatch.setattr('app.extensions.smtplib.SMTP_SSL',SMTP)
    monkeypatch.setattr('app.extensions.smtplib.SMTP',SMTP)
    send_code(client.app.state.settings,'owned@example.com','123456','password_reset')
    context=calls[0][3]['context'];assert context.verify_mode==ssl.CERT_REQUIRED and context.check_hostname
    assert calls[1][0]=='login' and calls[2][0]=='message'
    assert '重置密码' in calls[2][1]['Subject'] and '注册' not in calls[2][1]['Subject']


def test_binding_expiry_attempt_limit_and_resend_invalidate_old_code(client,monkeypatch):
    sent=mail_setup(client,monkeypatch);_,headers=add_account(client)
    values=iter([123456,654321,112233])
    monkeypatch.setattr('app.account_recovery.secrets.randbelow',lambda maximum:next(values))
    bind_request(client,headers);drain(client);first=sent[-1][1]
    assert bind_request(client,headers).status_code==429
    with client.app.state.session() as db:
        row=db.scalar(select(EmailChallenge).where(EmailChallenge.email.like('bind:%')))
        row.sent_at-=timedelta(seconds=61);db.commit()
    bind_request(client,headers);drain(client);second=sent[-1][1]
    assert bind(client,headers,first).status_code==400
    for _ in range(4):assert bind(client,headers,'000000').status_code==400
    assert bind(client,headers,second).status_code==400
    with client.app.state.session() as db:
        row=db.scalar(select(EmailChallenge).where(EmailChallenge.email.like('bind:%')))
        row.sent_at-=timedelta(seconds=61);db.commit()
    bind_request(client,headers);drain(client);third=sent[-1][1]
    with client.app.state.session() as db:
        row=db.scalar(select(EmailChallenge).where(EmailChallenge.email.like('bind:%')))
        row.expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert bind(client,headers,third).status_code==400
    assert client.get('/api/auth/email',headers=headers).json()['email']=='field@example.com'


def test_concurrent_verified_registration_consumes_one_proof(client,monkeypatch):
    sent=mail_setup(client,monkeypatch,verification=True)
    email='oneproof@example.com'
    client.post('/api/auth/email-code',json={'email':email});code=sent[-1][1]
    with ThreadPoolExecutor(2) as pool:
        responses=list(pool.map(lambda index:client.post('/api/auth/register',json=account(username=f'parallel_{index}',email=email,code=code)),range(2)))
    assert sorted(response.status_code for response in responses)==[201,400]
    with client.app.state.session() as db:
        binding=db.get(UserEmail,email)
        assert binding and db.get(AppMeta,verified_key(email)).value==binding.user_id
        assert db.get(EmailChallenge,email) is None


def test_admin_email_roundtrip_cannot_revive_proof_or_clear_another_users_proof(client,monkeypatch):
    sent=mail_setup(client,monkeypatch)
    user_id,headers=add_account(client)
    other_id,other=add_account(client,email='protected@example.com',username='protected_member')
    admin=auth(client)
    reset_request(client);drain(client);old_code=sent[-1][1]
    reset_request(client,'protected@example.com');drain(client)
    protected_key=challenge_key(client,'reset','protected@example.com')
    with client.app.state.session() as db:
        protected_digest=db.get(EmailChallenge,protected_key).digest
        # An earlier proof for the now-free target must not become trusted again.
        db.merge(AppMeta(key=verified_key('roundtrip@example.com'),value=user_id));db.commit()
    denied=client.patch('/api/admin/users/'+user_id,headers=admin,json={'email':'protected@example.com'})
    assert denied.status_code==409
    with client.app.state.session() as db:
        assert db.get(AppMeta,verified_key('protected@example.com')).value==other_id
        assert db.get(EmailChallenge,protected_key).digest==protected_digest
    changed=client.patch('/api/admin/users/'+user_id,headers=admin,json={'email':'roundtrip@example.com'})
    assert changed.status_code==200
    assert client.get('/api/auth/email',headers=headers).json()=={'email':'roundtrip@example.com','verified':False}
    with client.app.state.session() as db:
        assert db.get(AppMeta,verified_key('field@example.com')) is None
        assert db.get(AppMeta,verified_key('roundtrip@example.com')) is None
        assert db.get(EmailChallenge,challenge_key(client,'reset','field@example.com')) is None
    assert client.patch('/api/admin/users/'+user_id,headers=admin,json={'email':'field@example.com'}).status_code==200
    assert client.get('/api/auth/email',headers=headers).json()=={'email':'field@example.com','verified':False}
    assert reset(client,old_code).status_code==400
    assert client.get('/api/auth/email',headers=other).json()['verified'] is True


def test_reset_digest_follows_issued_account_not_a_later_email_owner(client,monkeypatch):
    sent=mail_setup(client,monkeypatch)
    owner_a,headers_a=add_account(client)
    owner_b,headers_b=add_account(client,email='second@example.com',username='second_member')
    admin=auth(client)
    values=iter([111111,222222,333333])
    monkeypatch.setattr('app.account_recovery.secrets.randbelow',lambda maximum:next(values))
    reset_request(client);drain(client);old_code=sent[-1][1]
    key=challenge_key(client,'reset','field@example.com')
    with client.app.state.session() as db:
        row=db.get(EmailChallenge,key)
        old_snapshot={name:getattr(row,name) for name in ('email','digest','sent_at','expires_at','attempts')}
        expected=hmac.new(client.app.state.settings.jwt_secret.encode(),
                          f'password_reset:{owner_a}:field@example.com:{old_code}'.encode(),hashlib.sha256).hexdigest()
        assert row.digest==expected
    assert client.patch('/api/admin/users/'+owner_a,headers=admin,json={'email':''}).status_code==200
    assert client.patch('/api/admin/users/'+owner_b,headers=admin,json={'email':'field@example.com'}).status_code==200
    assert client.get('/api/auth/email',headers=headers_b).json()['verified'] is False
    bind_request(client,headers_b,'field@example.com');drain(client)
    assert bind(client,headers_b,sent[-1][1],email='field@example.com').status_code==200
    # Fault injection retains an old in-flight/legacy proof, independent of the
    # admin invalidator. Its digest must still be unusable for the new account.
    with client.app.state.session() as db:db.merge(EmailChallenge(**old_snapshot));db.commit()
    assert reset(client,old_code).status_code==400
    assert client.post('/api/auth/login',json=account(username='second_member')).status_code==200
    with client.app.state.session() as db:
        assert db.get(User,owner_b).token_version==0
        db.get(EmailChallenge,key).sent_at-=timedelta(seconds=61);db.commit()
    reset_request(client);drain(client);new_code=sent[-1][1]
    assert new_code!=old_code and reset(client,new_code).status_code==200
    assert client.post('/api/auth/login',json=account()).status_code==200
    assert client.post('/api/auth/login',json=account(username='second_member',password='replacement-password-2026')).status_code==200


def test_queued_mail_captures_only_six_immutable_smtp_fields_across_config_changes(client,monkeypatch,caplog):
    from dataclasses import FrozenInstanceError, fields
    mail_setup(client,monkeypatch)
    add_account(client)
    add_account(client,email='second@example.com',username='second_member')
    settings=client.app.state.settings
    first={'smtp_host':'smtp-a.synthetic.invalid','smtp_port':465,'smtp_security':'ssl',
           'smtp_username':'sender-a@synthetic.invalid','smtp_from':'sender-a@synthetic.invalid',
           'smtp_password':'SYNTHETIC-SMTP-A-PRIVATE'}
    second={'smtp_host':'smtp-b.synthetic.invalid','smtp_port':587,'smtp_security':'starttls',
            'smtp_username':'sender-b@synthetic.invalid','smtp_from':'sender-b@synthetic.invalid',
            'smtp_password':'SYNTHETIC-SMTP-B-PRIVATE'}
    for key,value in first.items():setattr(settings,key,value)
    calls=[]
    def observe(snapshot,email,code,purpose):
        assert {field.name for field in fields(snapshot)}==set(first)
        assert not hasattr(snapshot,'llm_api_key') and not hasattr(snapshot,'jwt_secret')
        assert not hasattr(snapshot,'__dict__')
        with pytest.raises(FrozenInstanceError):snapshot.smtp_host='changed'
        assert 'SYNTHETIC-SMTP-' not in repr(snapshot)
        captured={key:getattr(snapshot,key) for key in first}
        calls.append(captured)
        if len(calls)==2:raise RuntimeError('SYNTHETIC-SMTP-B-PRIVATE must never escape the mail worker')
    monkeypatch.setattr('app.extensions.send_code',observe)
    entered,release=Event(),Event()
    def block_sender():entered.set();assert release.wait(5)
    blocker=client.app.state.email_mailer.executor.submit(block_sender)
    try:
        assert entered.wait(1)
        response=reset_request(client)
        assert response.status_code==200 and not calls
        for key,value in second.items():setattr(settings,key,value)
        client.app.state.runtime_config.refresh()
        release.set();blocker.result(timeout=2);drain(client)
    finally:release.set()
    assert calls==[first]
    response=reset_request(client,'second@example.com');drain(client)
    assert response.json()=={'message':RESET_MESSAGE} and calls==[first,second]
    assert 'SYNTHETIC-SMTP-' not in response.text and 'SYNTHETIC-SMTP-' not in caplog.text
    with client.app.state.session() as db:
        row=db.get(EmailChallenge,challenge_key(client,'reset','second@example.com'))
        assert row.expires_at<=utcnow()
