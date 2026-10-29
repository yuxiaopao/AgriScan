"""Registration/login identifiers use the same contract for public and admin creation."""
import pytest

from test_api import auth, client
from test_extensions import account, enable_mail


def test_verified_email_username_can_register_and_log_in(client, monkeypatch):
    sent = enable_mail(client, monkeypatch)
    username = 'field.member+2026@example.com'
    missing = client.post('/api/auth/register', json=account(username=username, email=username))
    assert missing.status_code == 400
    assert client.post('/api/auth/email-code', json={'email': username}).status_code == 200
    wrong = '000000' if sent[0][1] != '000000' else '999999'
    assert client.post('/api/auth/register', json=account(
        username=username, email=username, code=wrong)).status_code == 400
    response = client.post('/api/auth/register', json=account(
        username=username, email=username, code=sent[0][1]))
    assert response.status_code == 201, response.text
    login = client.post('/api/auth/login', json=account(username=username))
    assert login.status_code == 200, login.text
    assert login.json()['user']['username'] == username
    # A fresh valid challenge does not bypass either unique account constraint.
    assert client.post('/api/auth/email-code', json={'email': username}).status_code == 200
    duplicate = client.post('/api/auth/register', json=account(
        username=username, email=username, code=sent[-1][1]))
    assert duplicate.status_code == 409


@pytest.mark.parametrize('username', [
    'field_member-2026', 'Field.Member+Tag@Example.COM', 'x' * 80,
    'a' * 64 + '@' + 'b' * 11 + '.com',
])
def test_registration_accepts_legacy_and_email_identifiers_within_login_bound(client, username):
    created = client.post('/api/auth/register', json=account(username=username))
    assert created.status_code == 201, created.text
    logged_in = client.post('/api/auth/login', json=account(username=username))
    assert logged_in.status_code == 200
    assert logged_in.json()['user']['username'] == username
    assert client.post('/api/auth/register', json=account(username=username)).status_code == 409


@pytest.mark.parametrize('username', [
    'ab', 'x' * 81, 'field member', ' field_member', 'field_member ', '田间成员',
    'field.member', 'field@localhost', 'a@@example.com', '.a@example.com',
    'a.@example.com', 'a..b@example.com', 'a@-example.com', 'a@example-.com',
    'a@example..com', 'a@exam_ple.com', 'a\n@example.com',
    'a' * 65 + '@example.com', 'a@' + 'b' * 64 + '.com',
])
def test_registration_rejects_invalid_identifiers_in_chinese_without_echoing_input(client, username):
    response = client.post('/api/auth/register', json=account(username=username))
    assert response.status_code == 422, response.text
    detail = response.json()['detail'][0]
    assert detail['loc'] == ['body', 'username']
    assert '用户名需为 3–80 位' in detail['msg']
    assert 'input' not in detail and 'ctx' not in detail


def test_admin_creation_uses_same_identifier_contract_without_email_login_alias(client):
    headers = auth(client)
    username = 'managed.member+2026@example.com'
    body = account(username=username, email='verified-contact@example.com')
    response = client.post('/api/admin/users', headers=headers, json=body)
    assert response.status_code == 201, response.text
    assert client.post('/api/auth/login', json=account(username=username)).status_code == 200
    assert client.post('/api/auth/login', json=account(username=body['email'])).status_code == 401
    assert client.post('/api/admin/users', headers=headers, json=body).status_code == 409
    invalid = client.post('/api/admin/users', headers=headers, json=account(username='invalid@'))
    assert invalid.status_code == 422
    assert '用户名需为 3–80 位' in invalid.json()['detail'][0]['msg']
