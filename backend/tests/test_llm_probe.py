"""Draft connection checks must never store or disclose provider credentials."""
import base64
from contextlib import asynccontextmanager
import io
from time import monotonic
from unittest.mock import Mock

import anyio
import httpx
from PIL import Image
import pytest
from sqlalchemy import func, select

from app.admin_models import AuditLog
from app.runtime_config import WorkspaceConfiguration
from test_api import auth
from test_extensions import member_auth
from test_runtime_config import config_settings, configured_client, current, patch


ENDPOINT = '/api/admin/config/llm/test'
BODY = {'llm_base_url': 'https://provider.example/v1', 'llm_model': 'vision-model',
        'llm_timeout': 120, 'llm_api_key': 'test-only-draft-key'}


def reply(content='AGRISCAN_OK', status=200):
    return httpx.Response(status, json={'choices': [{'message': {'content': content}}]})


def stub_provider(monkeypatch, provider):
    class ProviderClient:
        def __init__(self, **options):
            self.options = options

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        @asynccontextmanager
        async def stream(self, method, url, **kwargs):
            assert method == 'POST'
            response = provider(url, **{**self.options, **kwargs})
            try:
                yield response
            finally:
                await response.aclose()
    monkeypatch.setattr('app.llm_probe.httpx.AsyncClient', ProviderClient)


def successful_provider(calls):
    def post(url, **kwargs):
        calls.append((url, kwargs))
        content = kwargs['json']['messages'][-1]['content']
        if isinstance(content, str):
            return reply()
        data = base64.b64decode(content[1]['image_url']['url'].split(',', 1)[1])
        image = Image.open(io.BytesIO(data)).convert('RGB')
        colors = {(230, 20, 20): 'red', (20, 180, 20): 'green',
                  (20, 20, 230): 'blue', (240, 220, 20): 'yellow'}
        return reply(colors[image.getpixel((64, 64))])
    return post


def test_probe_requires_admin_and_does_not_dispatch_for_anonymous_or_member(config_settings, monkeypatch):
    provider = Mock()
    stub_provider(monkeypatch, provider)
    with configured_client(config_settings) as client:
        assert client.post(ENDPOINT, json=BODY).status_code == 401
        assert client.post(ENDPOINT, headers=member_auth(client), json=BODY).status_code == 403
    provider.assert_not_called()


def test_draft_probe_checks_real_image_color_without_saving_or_auditing(config_settings, monkeypatch):
    calls = []
    stub_provider(monkeypatch, successful_provider(calls))
    with configured_client(config_settings) as client:
        headers = auth(client)
        with client.app.state.session() as db:
            audit_before = db.scalar(select(func.count()).select_from(AuditLog))
        response = client.post(ENDPOINT, headers=headers, json=BODY)
        assert response.status_code == 200
        data = response.json()
        assert data['ok'] and data['text']['ok'] and data['vision']['ok']
        assert data['model'] == BODY['llm_model'] and data['elapsed_ms'] >= 0
        assert data['configuration_saved'] is False
        assert BODY['llm_api_key'] not in response.text
        assert current(client, headers)['version'] == 0
        with client.app.state.session() as db:
            assert db.get(WorkspaceConfiguration, 'workspace') is None
            assert db.scalar(select(func.count()).select_from(AuditLog)) == audit_before
        assert len(calls) == 2
        for url, options in calls:
            assert url == BODY['llm_base_url'] + '/chat/completions'
            assert options['headers']['Authorization'] == 'Bearer ' + BODY['llm_api_key']
            assert options['trust_env'] is False and options['follow_redirects'] is False and options['verify'] is True
            assert options['timeout'].read <= 20 and options['timeout'].connect <= 5
            assert options['json']['model'] == BODY['llm_model']
        assert 'Return only AGRISCAN_OK.' == calls[0][1]['json']['messages'][-1]['content']


def test_saved_key_only_reused_at_same_normalized_endpoint_and_revision_is_unchanged(config_settings, monkeypatch):
    calls = []
    stub_provider(monkeypatch, successful_provider(calls))
    with configured_client(config_settings) as client:
        headers = auth(client)
        saved = patch(client, headers, integrations={
            'llm_api_key': 'test-only-saved-key', 'llm_base_url': 'https://Provider.Example:443/v1/',
            'llm_model': 'saved-model', 'llm_enabled': False,
        }).json()
        draft = {key: value for key, value in BODY.items() if key != 'llm_api_key'}
        response = client.post(ENDPOINT, headers=headers, json=draft)
        assert response.status_code == 200 and response.json()['ok']
        assert all(options['headers']['Authorization'] == 'Bearer test-only-saved-key' for _, options in calls)
        assert current(client, headers)['version'] == saved['version']
        calls.clear()
        for changed in ['https://other.example/v1', 'https://provider.example/v2']:
            denied = client.post(ENDPOINT, headers=headers, json={**draft, 'llm_base_url': changed})
            assert denied.status_code == 422 and '已更改' in denied.json()['detail']
        assert not calls
        replacement = client.post(ENDPOINT, headers=headers,
                                  json={**BODY, 'llm_base_url': 'https://other.example/v1'})
        assert replacement.json()['ok']
        assert all(options['headers']['Authorization'] == 'Bearer ' + BODY['llm_api_key'] for _, options in calls)
        assert client.app.state.settings.llm_api_key == 'test-only-saved-key'
        assert current(client, headers)['version'] == saved['version']


@pytest.mark.parametrize('status', [400, 401, 402, 403, 404, 422, 429, 500, 302])
def test_provider_failures_are_safe_and_skip_image_when_text_fails(config_settings, monkeypatch, status):
    secret = BODY['llm_api_key']
    provider = Mock(return_value=httpx.Response(status, json={'error': {'message': secret}}))
    stub_provider(monkeypatch, provider)
    with configured_client(config_settings) as client:
        response = client.post(ENDPOINT, headers=auth(client), json=BODY)
        assert response.status_code == 200
        data = response.json()
        assert not data['ok'] and not data['text']['ok'] and not data['vision']['ok']
        assert not data['configuration_saved'] and secret not in response.text
        assert provider.call_count == 1


@pytest.mark.parametrize('problem', ['timeout', 'transport', 'json', 'missing', 'empty', 'too_long', 'wrong_text'])
def test_timeout_transport_and_malformed_responses_never_expose_provider_content(config_settings, monkeypatch, problem):
    secret = BODY['llm_api_key']
    if problem == 'timeout':
        provider = Mock(side_effect=httpx.ReadTimeout(secret))
    elif problem == 'transport':
        provider = Mock(side_effect=httpx.ConnectError(secret))
    else:
        responses = {'json': httpx.Response(200, text=secret),
                     'missing': httpx.Response(200, json={'error': secret}),
                     'empty': reply(None), 'too_long': reply(secret * 500),
                     'wrong_text': reply(secret)}
        provider = Mock(return_value=responses[problem])
    stub_provider(monkeypatch, provider)
    with configured_client(config_settings) as client:
        response = client.post(ENDPOINT, headers=auth(client), json=BODY)
        assert response.status_code == 200 and not response.json()['ok']
        assert not response.json()['text']['ok']
        assert secret not in response.text and provider.call_count == 1


@pytest.mark.parametrize('image_reply', ['wrong_color', 'unsupported'])
def test_image_acceptance_alone_does_not_claim_vision_support(config_settings, monkeypatch, image_reply):
    monkeypatch.setattr('app.llm_probe.choice', lambda colors: colors[0])
    provider = Mock(side_effect=[reply(), reply('blue') if image_reply == 'wrong_color'
                                else httpx.Response(400, text=BODY['llm_api_key'])])
    stub_provider(monkeypatch, provider)
    with configured_client(config_settings) as client:
        response = client.post(ENDPOINT, headers=auth(client), json=BODY)
        assert response.status_code == 200
        data = response.json()
        assert data['text']['ok'] and not data['vision']['ok'] and not data['ok']
        assert provider.call_count == 2 and BODY['llm_api_key'] not in response.text


@pytest.mark.parametrize('changes', [
    {'llm_base_url': 'http://public.example/v1'},
    {'llm_base_url': 'https://user:test-only-draft-key@provider.example/v1'},
    {'llm_base_url': 'https://provider.example/v1?key=test-only-draft-key'},
    {'llm_base_url': 'https://provider.example/v1#test-only-draft-key'},
    {'llm_base_url': 'https://provider.example:invalid/v1'},
    {'llm_model': ' '}, {'llm_api_key': ''}, {'llm_api_key': None},
    {'llm_api_key': 'test-only-draft-key' * 500}, {'llm_api_key': 'test-only-draft-key\r\nX: fail'},
    {'llm_timeout': 121}, {'llm_timeout': True}, {'llm_timeout': '30'},
])
def test_invalid_draft_is_redacted_and_not_sent(config_settings, monkeypatch, changes):
    provider = Mock()
    stub_provider(monkeypatch, provider)
    with configured_client(config_settings) as client:
        response = client.post(ENDPOINT, headers=auth(client), json={**BODY, **changes})
        assert response.status_code == 422
        assert BODY['llm_api_key'] not in response.text
        if isinstance(response.json()['detail'], list):
            assert all('input' not in error for error in response.json()['detail'])
    provider.assert_not_called()


def test_missing_saved_key_cannot_test(config_settings, monkeypatch):
    provider = Mock()
    stub_provider(monkeypatch, provider)
    with configured_client(config_settings) as client:
        response = client.post(ENDPOINT, headers=auth(client), json={
            'llm_base_url': config_settings.llm_base_url, 'llm_model': 'model'})
        assert response.status_code == 422
    provider.assert_not_called()


@pytest.mark.parametrize('saved_key', ['non-ascii-密钥', 'header\r\ninjection'])
def test_invalid_legacy_saved_key_fails_safely_before_headers_are_created(config_settings, monkeypatch, saved_key):
    provider = Mock()
    stub_provider(monkeypatch, provider)
    with configured_client(config_settings) as client:
        headers = auth(client)
        assert patch(client, headers, integrations={'llm_api_key': saved_key}).status_code == 200
        response = client.post(ENDPOINT, headers=headers, json={
            'llm_base_url': config_settings.llm_base_url, 'llm_model': 'model'})
        assert response.status_code == 422 and saved_key not in response.text
    provider.assert_not_called()


def test_oversized_stream_is_closed_before_reading_the_full_provider_body(config_settings, monkeypatch):
    class OversizedStream(httpx.AsyncByteStream):
        reads = 0
        closed = False

        async def __aiter__(self):
            for _ in range(1000):
                self.reads += 1
                yield (BODY['llm_api_key'].encode() + b'x' * 4096)[:4096]

        async def aclose(self):
            self.closed = True

    stream = OversizedStream()
    provider = Mock(return_value=httpx.Response(200, stream=stream))
    stub_provider(monkeypatch, provider)
    with configured_client(config_settings) as client:
        response = client.post(ENDPOINT, headers=auth(client), json=BODY)
        assert response.status_code == 200 and not response.json()['ok']
        assert BODY['llm_api_key'] not in response.text
        assert stream.reads == 17 and stream.closed
        assert provider.call_count == 1


def test_slow_drip_stream_hits_total_deadline_and_is_closed(config_settings, monkeypatch):
    class SlowStream(httpx.AsyncByteStream):
        reads = 0
        closed = False

        async def __aiter__(self):
            for _ in range(1000):
                await anyio.sleep(0.005)
                self.reads += 1
                yield b' '

        async def aclose(self):
            self.closed = True

    stream = SlowStream()
    provider = Mock(return_value=httpx.Response(200, stream=stream))
    stub_provider(monkeypatch, provider)
    monkeypatch.setattr('app.llm_probe.MAX_PROBE_SECONDS', 0.05)
    with configured_client(config_settings) as client:
        headers = auth(client)
        started = monotonic()
        response = client.post(ENDPOINT, headers=headers, json=BODY)
        elapsed = monotonic() - started
        assert response.status_code == 200 and not response.json()['ok']
        assert '超时' in response.json()['text']['message']
        assert BODY['llm_api_key'] not in response.text
        assert 0 < stream.reads < 100 and stream.closed
        assert elapsed < 1 and provider.call_count == 1
