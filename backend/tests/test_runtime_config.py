"""Persisted settings are isolated per request and secrets never become API data."""
from contextlib import contextmanager
from dataclasses import replace
import json
from threading import Event
from concurrent.futures import ThreadPoolExecutor

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.admin_models import AuditLog
from app.config import Settings
from app.main import create_app
from app.runtime_config import RuntimeSettings, WorkspaceConfiguration, install_runtime_config
from test_api import auth, picture
from test_extensions import member_auth


@pytest.fixture()
def config_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('CONFIG_ENCRYPTION_KEY', Fernet.generate_key().decode())
    return Settings(database_url=f"sqlite:///{tmp_path / 'config.db'}", upload_dir=tmp_path / 'uploads',
                    redis_url='', demo_mode=True, model_manifest='', llm_enabled=False, llm_api_key='',
                    smtp_password='', registration_enabled=True, email_verification_enabled=False)


@contextmanager
def configured_client(settings, extra_route=None):
    proxy = RuntimeSettings(settings)
    app = create_app(proxy)
    if not hasattr(app.state, 'runtime_config'):
        def get_db():
            with app.state.session() as db:
                yield db
        install_runtime_config(app, proxy, get_db)
    if extra_route:
        extra_route(app)
    with TestClient(app) as client:
        app.state.runtime_config.refresh()
        yield client


def current(client, headers):
    response = client.get('/api/admin/config', headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def patch(client, headers, **changes):
    return client.patch('/api/admin/config', headers=headers,
                        json={'version': current(client, headers)['version'], **changes})


def test_configuration_permissions_and_public_shape(config_settings):
    with configured_client(config_settings) as client:
        public = client.get('/api/client/config').json()
        assert set(public) == {'brand', 'features', 'limits', 'registration_enabled', 'email_verification_enabled', 'version'}
        assert public['version'] == 0 and public['limits']['video_max_frames'] == 8
        assert client.get('/api/admin/config').status_code == 401
        member = member_auth(client)
        assert client.get('/api/admin/config', headers=member).status_code == 403
        assert client.patch('/api/admin/config', headers=member, json={'version': 0}).status_code == 403


def test_encrypted_keys_are_write_only_and_audit_contains_only_field_names(config_settings):
    secret, password = 'test-provider-key-never-return', 'test-mail-password-never-return'
    with configured_client(config_settings) as client:
        headers = auth(client)
        response = patch(client, headers, integrations={
            'llm_enabled': True, 'llm_api_key': secret, 'llm_base_url': 'https://example.com/v1',
            'llm_model': 'configured-model', 'smtp_password': password,
        })
        assert response.status_code == 200, response.text
        data = response.json()
        assert data['integrations']['llm_key_configured'] and data['integrations']['smtp_password_configured']
        assert 'llm_api_key' not in data['integrations'] and 'smtp_password' not in data['integrations']
        assert secret not in response.text and password not in response.text
        assert 'integrations' not in client.get('/api/client/config').json()
        with client.app.state.session() as db:
            stored = db.get(WorkspaceConfiguration, 'workspace')
            assert secret not in json.dumps(stored.data) and password not in stored.encrypted_secrets
            assert stored.encrypted_secrets and secret not in stored.encrypted_secrets
            audit = db.scalars(select(AuditLog).where(AuditLog.resource_type == 'runtime_config')).one()
            assert 'integrations.llm_api_key' in audit.summary
            assert secret not in audit.summary and password not in audit.summary and 'example.com' not in audit.summary
        assert client.app.state.settings.llm_api_key == secret
        disabled = patch(client, headers, integrations={'llm_enabled': False})
        assert disabled.status_code == 200 and disabled.json()['integrations']['llm_key_configured']
        assert client.app.state.settings.llm_api_key == secret
        cleared = patch(client, headers, integrations={'llm_api_key': None})
        assert cleared.status_code == 200 and not cleared.json()['integrations']['llm_key_configured']


def test_configuration_survives_restart_and_stale_editor_is_rejected(config_settings):
    with configured_client(config_settings) as client:
        headers = auth(client)
        response = patch(client, headers, brand={'app_name': '田间检测APP', 'announcement': '明日巡田'},
                         limits={'video_max_frames': 3}, integrations={'registration_enabled': False})
        assert response.status_code == 200
        assert client.get('/api/auth/config').json()['registration_enabled'] is False
        stale = client.patch('/api/admin/config', headers=headers, json={'version': 0, 'brand': {'app_name': '过期修改'}})
        assert stale.status_code == 409
        expected = client.get('/api/client/config').json()
    with configured_client(replace(config_settings)) as client:
        assert client.get('/api/client/config').json() == expected
        assert expected['brand']['app_name'] == '田间检测APP' and expected['limits']['video_max_frames'] == 3


def test_missing_key_rejects_secret_changes_without_losing_existing_configuration(config_settings, monkeypatch):
    monkeypatch.delenv('CONFIG_ENCRYPTION_KEY')
    with configured_client(config_settings) as client:
        headers = auth(client)
        assert patch(client, headers, brand={'app_name': '已经保存的名称'}).status_code == 200
        version = current(client, headers)['version']
        denied = patch(client, headers, brand={'app_name': '不得部分保存'}, integrations={'smtp_password': 'secret'})
        assert denied.status_code == 503
        saved = current(client, headers)
        assert saved['version'] == version and saved['brand']['app_name'] == '已经保存的名称'


def test_wrong_encryption_key_has_diagnostic_startup_error(config_settings, monkeypatch):
    with configured_client(config_settings) as client:
        assert patch(client, auth(client), integrations={'smtp_password': 'keep-this-encrypted'}).status_code == 200
    monkeypatch.setenv('CONFIG_ENCRYPTION_KEY', Fernet.generate_key().decode())
    with pytest.raises(RuntimeError, match='CONFIG_ENCRYPTION_KEY.*解密'):
        with configured_client(replace(config_settings)):
            pass


@pytest.mark.parametrize('changes', [
    {'limits': {'image_max_mb': 11}}, {'limits': {'video_max_seconds': 61}},
    {'limits': {'video_max_frames': 9}}, {'limits': {'frame_interval_ms': 1}},
    {'features': {'assistant': 'false'}}, {'brand': {'app_name': ' '}},
    {'integrations': {'smtp_port': 0}}, {'integrations': {'email_verification_enabled': True}},
    {'integrations': {'llm_enabled': True}}, {'integrations': {'llm_base_url': None}},
])
def test_invalid_configuration_never_changes_saved_version(config_settings, changes):
    with configured_client(config_settings) as client:
        headers = auth(client)
        response = patch(client, headers, **changes)
        assert response.status_code == 422, response.text
        assert current(client, headers)['version'] == 0


def test_invalid_secret_validation_does_not_echo_request_body(config_settings):
    secret = 'must-never-echo-' * 400
    with configured_client(config_settings) as client:
        response = patch(client, auth(client), integrations={'llm_api_key': secret})
        assert response.status_code == 422 and secret not in response.text
        assert 'input' not in response.json()['detail'][0]


def test_feature_gates_block_new_work_and_preserve_readable_history(config_settings):
    with configured_client(config_settings) as client:
        headers = auth(client)
        response = patch(client, headers, features={
            'image_detection': False, 'video_detection': False, 'live_detection': False,
            'assistant': False, 'knowledge': False, 'plots': False,
        })
        assert response.status_code == 200
        for route in ['/api/detections', '/api/media/frame', '/api/media/video']:
            response = client.post(route, headers=headers, files={'file': ('leaf.png', picture(), 'image/png')})
            assert response.status_code == 403
        assert client.post('/api/assistant/conversations', headers=headers).status_code == 403
        assert client.post('/api/knowledge/ask', headers=headers, json={'question': '如何巡田'}).status_code == 403
        assert client.get('/api/detections').status_code == 200
        assert client.get('/api/plots').status_code == 200
        assert client.get('/api/knowledge').status_code == 200
        assert client.get('/api/assistant/conversations', headers=headers).status_code == 200
        assert client.get('/api/admin/plots', headers=headers).status_code == 200


def test_runtime_proxy_keeps_inflight_request_on_one_consistent_snapshot(config_settings):
    entered, release = Event(), Event()

    def extra(app):
        @app.get('/api/test/config-snapshot')
        def snapshot():
            before = app.state.settings.smtp_host
            entered.set()
            assert release.wait(timeout=10)
            return [before, app.state.settings.smtp_host]

    with configured_client(config_settings, extra) as client:
        headers = auth(client)
        assert patch(client, headers, integrations={'smtp_host': 'before.example'}).status_code == 200
        with ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(client.get, '/api/test/config-snapshot')
            try:
                assert entered.wait(timeout=10)
                assert patch(client, headers, integrations={'smtp_host': 'after.example'}).status_code == 200
            finally:
                release.set()
            assert request.result().json() == ['before.example', 'before.example']
        assert client.app.state.settings.smtp_host == 'after.example'


def test_separate_worker_refreshes_committed_configuration(config_settings):
    with configured_client(config_settings) as first, configured_client(replace(config_settings)) as second:
        headers = auth(first)
        assert second.get('/api/client/config').json()['version'] == 0
        assert patch(first, headers, brand={'app_name': '跨进程共享配置'}).status_code == 200
        assert second.get('/api/client/config').json()['brand']['app_name'] == '跨进程共享配置'


def test_disabled_feature_and_configuration_validation_keep_cors_headers(config_settings):
    origin = config_settings.cors_origins[0]
    with configured_client(config_settings) as client:
        headers = {**auth(client), 'Origin': origin}
        invalid = client.patch('/api/admin/config', headers=headers, json={'version': 0, 'limits': {'image_max_mb': 11}})
        assert invalid.status_code == 422 and invalid.headers['access-control-allow-origin'] == origin
        assert patch(client, headers, features={'image_detection': False}).status_code == 200
        disabled = client.post('/api/detections', headers=headers, files={'file': ('leaf.png', picture(), 'image/png')})
        assert disabled.status_code == 403 and disabled.headers['access-control-allow-origin'] == origin


def test_dynamic_media_limits_and_model_upload_limit_are_enforced(config_settings, tmp_path):
    from test_media import Classifier, video
    with configured_client(config_settings) as client:
        headers = auth(client)
        client.app.state.inference = Classifier()
        response = patch(client, headers, limits={'image_max_mb': 1, 'video_max_mb': 1,
            'video_max_seconds': 2, 'video_max_frames': 2, 'frame_interval_ms': 1500},
            integrations={'model_max_mb': 1})
        assert response.status_code == 200, response.text
        caps = client.get('/api/media/capabilities').json()
        assert caps['video_max_mb'] == 1 and caps['video_max_seconds'] == 2
        assert caps['video_max_frames'] == 2 and caps['frame_min_interval_ms'] == 1500
        assert client.app.state.settings.max_upload_bytes == 1024 * 1024
        assert client.app.state.settings.model_max_mb == 1
        payload = video(tmp_path, frames=8, fps=4)
        result = client.post('/api/media/video', headers=headers,
                             files={'file': ('video.avi', payload, 'video/x-msvideo')})
        assert result.status_code == 200 and result.json()['sampled_frames'] == 2
        too_large = client.post('/api/media/frame', headers=headers,
                                files={'file': ('camera.png', b'x' * (1024 * 1024 + 1), 'image/png')})
        assert too_large.status_code == 413 and '1 MB' in too_large.json()['detail']
        image = client.post('/api/detections', headers=headers,
                            files={'file': ('leaf.png', b'x' * (1024 * 1024 + 1), 'image/png')})
        assert image.status_code == 413
        weights = client.post('/api/models', headers=headers, data={'name': '超过动态限额的权重'},
                              files={'file': ('weights.pt', b'x' * (1024 * 1024 + 1), 'application/octet-stream')})
        assert weights.status_code == 413
        oversized_video = client.post('/api/media/video', headers=headers,
                                       files={'file': ('video.avi', b'x' * (1024 * 1024 + 1), 'video/x-msvideo')})
        assert oversized_video.status_code == 413
        long_video = client.post('/api/media/video', headers=headers,
                                 files={'file': ('video.avi', video(tmp_path, frames=12, fps=4), 'video/x-msvideo')})
        assert long_video.status_code == 422 and '2 秒' in long_video.json()['detail']
