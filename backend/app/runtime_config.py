"""Versioned workspace configuration, encrypted credentials and request snapshots."""
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime
import json
import os
from threading import RLock
from typing import Literal

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool, ValidationError, field_validator
from sqlalchemy import ForeignKey, Integer, JSON, String, Text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column
from starlette.concurrency import run_in_threadpool

from .admin_models import add_audit
from .db import Base, Timestamp, utcnow
from .extensions import admin_user

SECRETS = {'smtp_password', 'llm_api_key'}
_request_config = ContextVar('agriscan_runtime_configuration', default=None)


class WorkspaceConfiguration(Base):
    __tablename__ = 'workspace_configuration'
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default='workspace')
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    encrypted_secrets: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(Timestamp, default=utcnow)


class ConfigBody(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Brand(ConfigBody):
    app_name: str = Field(default='禾观 AgriScan', min_length=1, max_length=60)
    tagline: str = Field(default='看见生长的力量', max_length=140)
    announcement: str = Field(default='', max_length=1000)

    @field_validator('app_name', 'tagline', 'announcement')
    @classmethod
    def clean_text(cls, value):
        value = value.strip()
        return value

    @field_validator('app_name')
    @classmethod
    def name_required(cls, value):
        if not value:
            raise ValueError('应用名称不能为空。')
        return value


class Features(ConfigBody):
    image_detection: StrictBool = True
    video_detection: StrictBool = True
    live_detection: StrictBool = True
    assistant: StrictBool = True
    knowledge: StrictBool = True
    plots: StrictBool = True


class Limits(ConfigBody):
    image_max_mb: int = Field(default=10, ge=1, le=10, strict=True)
    video_max_mb: int = Field(default=50, ge=1, le=50, strict=True)
    video_max_seconds: int = Field(default=60, ge=1, le=60, strict=True)
    video_max_frames: int = Field(default=8, ge=1, le=8, strict=True)
    frame_interval_ms: int = Field(default=750, ge=750, le=10000, strict=True)


class Integrations(ConfigBody):
    registration_enabled: StrictBool = True
    email_verification_enabled: StrictBool = False
    smtp_host: str = Field(default='', max_length=253)
    smtp_port: int = Field(default=587, ge=1, le=65535, strict=True)
    smtp_username: str = Field(default='', max_length=254)
    smtp_from: str = Field(default='', max_length=254)
    smtp_security: Literal['starttls', 'ssl'] = 'starttls'
    llm_enabled: StrictBool = False
    llm_base_url: str = Field(default='https://api.openai.com/v1', max_length=2000)
    llm_model: str = Field(default='', max_length=200)
    llm_timeout: int = Field(default=30, ge=1, le=120, strict=True)
    model_max_mb: int = Field(default=200, ge=1, le=2048, strict=True)


class IntegrationPatch(ConfigBody):
    registration_enabled: StrictBool | None = None
    email_verification_enabled: StrictBool | None = None
    smtp_host: str | None = Field(default=None, max_length=253)
    smtp_port: int | None = Field(default=None, ge=1, le=65535, strict=True)
    smtp_username: str | None = Field(default=None, max_length=254)
    smtp_from: str | None = Field(default=None, max_length=254)
    smtp_security: Literal['starttls', 'ssl'] | None = None
    smtp_password: SecretStr | None = Field(default=None, max_length=4096)
    llm_enabled: StrictBool | None = None
    llm_base_url: str | None = Field(default=None, max_length=2000)
    llm_model: str | None = Field(default=None, max_length=200)
    llm_timeout: int | None = Field(default=None, ge=1, le=120, strict=True)
    llm_api_key: SecretStr | None = Field(default=None, max_length=4096)
    model_max_mb: int | None = Field(default=None, ge=1, le=2048, strict=True)

    @field_validator('smtp_password', 'llm_api_key')
    @classmethod
    def nonempty_secret(cls, value):
        if value is not None and not value.get_secret_value():
            raise ValueError('留空时请省略密钥字段，清除密钥请显式提交 null。')
        return value


class Configuration(ConfigBody):
    brand: Brand = Field(default_factory=Brand)
    features: Features = Field(default_factory=Features)
    limits: Limits = Field(default_factory=Limits)
    integrations: Integrations = Field(default_factory=Integrations)


class ConfigurationPatch(ConfigBody):
    version: int = Field(ge=0, strict=True)
    brand: Brand | None = None
    features: Features | None = None
    limits: Limits | None = None
    integrations: IntegrationPatch | None = None

    @field_validator('brand', 'features', 'limits', 'integrations')
    @classmethod
    def no_null_group(cls, value):
        if value is None:
            raise ValueError('配置分组不可为 null。')
        return value


@dataclass(frozen=True)
class Snapshot:
    version: int
    data: dict
    secrets: dict


class RuntimeSettings:
    """Pass this same proxy to every pre-existing Settings closure."""
    def __init__(self, base):
        while isinstance(base, RuntimeSettings):
            base = base.base
        object.__setattr__(self, 'base', base)
        object.__setattr__(self, 'manager', None)

    def __getattr__(self, name):
        manager = self.manager
        if manager is not None:
            bound = _request_config.get()
            snapshot = bound[1] if bound and bound[0] is manager else manager.snapshot
            if snapshot is not None:
                if name == 'max_upload_bytes':
                    return snapshot.data['limits']['image_max_mb'] * 1024 * 1024
                if name in snapshot.data['integrations']:
                    return snapshot.data['integrations'][name]
                if name in snapshot.secrets:
                    return snapshot.secrets[name] or ''
        return getattr(self.base, name)

    def __setattr__(self, name, value):
        # Preserve test/tool callers that edit the original environment defaults.
        setattr(self.base, name, value)


def _defaults(base):
    integrations = {name: getattr(base, name) for name in Integrations.model_fields}
    return Configuration(integrations=Integrations(**integrations)).model_dump()


class ConfigurationManager:
    def __init__(self, app, settings):
        self.app = app
        self.settings = settings
        self.base = settings.base if isinstance(settings, RuntimeSettings) else settings
        self.lock = RLock()
        self.snapshot = None

    def cipher(self, required=False):
        key = os.getenv('CONFIG_ENCRYPTION_KEY', '').strip()
        if not key:
            if required:
                raise RuntimeError('CONFIG_ENCRYPTION_KEY 未配置，无法读写已加密的接入密钥。')
            return None
        try:
            return Fernet(key.encode('ascii'))
        except (ValueError, UnicodeError):
            raise RuntimeError('CONFIG_ENCRYPTION_KEY 格式无效，应为 Fernet 密钥。') from None

    def decode(self, row):
        if row is None:
            return Snapshot(0, _defaults(self.base), {})
        try:
            data = Configuration.model_validate(row.data).model_dump()
            secrets = json.loads(self.cipher(required=True).decrypt(row.encrypted_secrets.encode()).decode()) if row.encrypted_secrets else {}
            if (not isinstance(secrets, dict) or set(secrets) - SECRETS
                    or any(value is not None and not isinstance(value, str) for value in secrets.values())):
                raise ValueError('Invalid credential payload')
        except InvalidToken:
            raise RuntimeError('CONFIG_ENCRYPTION_KEY 无法解密运行配置，请恢复原密钥；已有配置未被修改。') from None
        except (ValidationError, ValueError, TypeError, UnicodeError):
            raise RuntimeError('数据库中的运行配置无效，请检查配置备份。') from None
        return Snapshot(row.version, data, secrets)

    def apply(self, snapshot):
        self.snapshot = snapshot
        self.app.state.client_config = self.public(snapshot)

    def refresh(self):
        # Each request reads the committed row, so separate workers never retain
        # an indefinitely stale config or use a partially changed credential set.
        with self.lock, self.app.state.session() as db:
            snapshot = self.decode(db.get(WorkspaceConfiguration, 'workspace'))
            self.apply(snapshot)
            return snapshot

    def public(self, snapshot):
        data = snapshot.data
        return {**{name: deepcopy(data[name]) for name in ('brand', 'features', 'limits')},
                'registration_enabled': data['integrations']['registration_enabled'],
                'email_verification_enabled': data['integrations']['email_verification_enabled'],
                'version': snapshot.version}

    def admin(self, snapshot):
        data = deepcopy(snapshot.data)
        for name in SECRETS:
            value = snapshot.secrets.get(name, getattr(self.base, name))
            flag = 'smtp_password_configured' if name == 'smtp_password' else 'llm_key_configured'
            data['integrations'][flag] = bool(value)
        return {**data, 'version': snapshot.version}

    def save(self, db, user, body):
        with self.lock:
            row = db.get(WorkspaceConfiguration, 'workspace')
            current = self.decode(row)
            if body.version != current.version:
                raise HTTPException(409, '配置已被其他管理员修改，请刷新后重试。')
            data, secrets = deepcopy(current.data), dict(current.secrets)
            changed = []
            patch = body.model_dump(exclude_unset=True, exclude={'version'})
            for group, changes in patch.items():
                for name, value in changes.items():
                    if name in SECRETS:
                        secrets[name] = value.get_secret_value() if value is not None else None
                    else:
                        if value is None:
                            raise HTTPException(422, '普通配置字段不可为 null。')
                        data[group][name] = value
                    changed.append(f'{group}.{name}')
            if not changed:
                return self.admin(current)
            try:
                data = Configuration.model_validate(data).model_dump()
                effective = {**data['integrations'], **{name: value or '' for name, value in secrets.items()}}
                candidate = replace(self.base, **effective,
                                    max_upload_bytes=data['limits']['image_max_mb'] * 1024 * 1024)
                candidate.validate()
            except (ValueError, ValidationError):
                raise HTTPException(422, '接入配置无效，请检查 SMTP、邮箱验证及大模型的完整配置。') from None
            encrypted = row.encrypted_secrets if row else None
            if any(name.rsplit('.', 1)[-1] in SECRETS for name in changed):
                try:
                    encrypted = self.cipher(required=True).encrypt(json.dumps(secrets, ensure_ascii=False).encode()).decode()
                except RuntimeError:
                    raise HTTPException(503, '服务器尚未配置有效 CONFIG_ENCRYPTION_KEY，密钥未被保存。') from None
            version = current.version + 1
            values = {'version': version, 'data': data, 'encrypted_secrets': encrypted,
                      'updated_by': user.id, 'updated_at': utcnow()}
            try:
                if row is None:
                    db.add(WorkspaceConfiguration(id='workspace', **values))
                    db.flush()
                else:
                    result = db.execute(update(WorkspaceConfiguration).where(
                        WorkspaceConfiguration.id == 'workspace', WorkspaceConfiguration.version == current.version).values(**values))
                    if result.rowcount != 1:
                        raise HTTPException(409, '配置已被其他管理员修改，请刷新后重试。')
                add_audit(db, user, 'update', 'runtime_config', 'workspace', '修改配置字段：' + ', '.join(sorted(changed)))
                db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(409, '配置已被其他管理员修改，请刷新后重试。') from None
            updated = Snapshot(version, data, secrets)
            self.apply(updated)
            return self.admin(updated)


def client_config_for(app):
    bound = _request_config.get()
    manager = getattr(app.state, 'runtime_config', None)
    if bound and bound[0] is manager:
        return manager.public(bound[1])
    return getattr(app.state, 'client_config', {})


def blocked_feature(path, method, features):
    if method in {'GET', 'HEAD', 'OPTIONS'} or path.startswith('/api/admin/'):
        return None
    checks = [
        (path == '/api/detections' and method == 'POST', 'image_detection'),
        (path == '/api/media/video', 'video_detection'),
        (path == '/api/media/frame', 'live_detection'),
        (path.startswith('/api/assistant/'), 'assistant'),
        (path == '/api/knowledge/ask', 'assistant'),
        (path == '/api/knowledge/ask', 'knowledge'),
    ]
    return next((feature for matches, feature in checks if matches and not features.get(feature, True)), None)


class RuntimeConfigMiddleware:
    def __init__(self, app, manager):
        self.app, self.manager = app, manager

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        snapshot = await run_in_threadpool(self.manager.refresh)
        token = _request_config.set((self.manager, snapshot))
        try:
            if blocked_feature(scope['path'].rstrip('/'), scope['method'], snapshot.data['features']):
                return await JSONResponse({'detail': '管理员暂时关闭了此功能，已有历史记录仍可查看。'}, status_code=403)(scope, receive, send)
            await self.app(scope, receive, send)
        finally:
            _request_config.reset(token)


class ConfigRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                # Never echo request bodies containing write-only credentials.
                detail = [{key: item[key] for key in ('type', 'loc', 'msg')} for item in error.errors()]
                return JSONResponse({'detail': detail}, status_code=422)
        return guarded


def install_runtime_config(app, settings, get_db):
    manager = ConfigurationManager(app, settings)
    app.state.runtime_config = manager
    if isinstance(settings, RuntimeSettings):
        object.__setattr__(settings, 'manager', manager)
    app.add_middleware(RuntimeConfigMiddleware, manager=manager)
    router = APIRouter(prefix='/api', route_class=ConfigRoute)

    @router.get('/client/config')
    def public_configuration():
        bound = _request_config.get()
        snapshot = bound[1] if bound and bound[0] is manager else manager.refresh()
        return manager.public(snapshot)

    @router.get('/admin/config')
    def administrative_configuration(user=Depends(admin_user)):
        bound = _request_config.get()
        snapshot = bound[1] if bound and bound[0] is manager else manager.refresh()
        return manager.admin(snapshot)

    @router.patch('/admin/config')
    def update_configuration(body: ConfigurationPatch, user=Depends(admin_user), db=Depends(get_db)):
        return manager.save(db, user, body)

    app.include_router(router)
    return manager
