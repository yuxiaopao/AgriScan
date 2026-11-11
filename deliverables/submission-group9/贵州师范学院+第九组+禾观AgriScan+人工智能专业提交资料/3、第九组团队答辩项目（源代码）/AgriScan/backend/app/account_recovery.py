"""Purpose-separated email proofs and password recovery; no schema migration."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import hmac
import re
import secrets
from threading import BoundedSemaphore
from time import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, SecretStr, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .db import AppMeta, RevokedToken, User, utcnow
from .ownership import _lock_query
from .runtime_config import ConfigRoute
from .security import credential_signature, current_user, hash_password, verify_password

RESET_MESSAGE = '如果该邮箱已完成验证并关联可用账户，重置验证码将发送至该邮箱，请稍后查收。'
INVALID_CODE = '验证码无效或已过期，请重新获取。'
BIND_ERROR = '邮箱验证未完成，请检查当前密码与验证码，或重新获取验证码。'
UNVERIFIED_RESET_OWNER = 'unverified-email-owner'


def verified_key(email):
    return 'verified_email:' + hashlib.sha256(email.encode()).hexdigest()


def mark_verified(db, email, user_id):
    db.merge(AppMeta(key=verified_key(email), value=user_id))


def email_challenge_key(settings, purpose, email, user_id=''):
    digest = hmac.new(settings.jwt_secret.encode(), (user_id + ':' + email).encode(), hashlib.sha256).hexdigest()
    return ('reset:' if purpose == 'password_reset' else 'bind:') + digest


def invalidate_email_proof(db, email, user_id, settings):
    """Caller first authorizes the mapping change; never revoke another user's marker."""
    from .extensions import EmailChallenge
    marker = db.scalar(_lock_query(db, select(AppMeta).where(AppMeta.key == verified_key(email)), True))
    if marker and marker.value == user_id:
        db.delete(marker)
    pending = db.scalar(_lock_query(db, select(EmailChallenge).where(
        EmailChallenge.email == email_challenge_key(settings, 'password_reset', email)), True))
    if pending:
        db.delete(pending)


def smtp_ready(settings):
    return bool(settings.smtp_host and settings.smtp_from and settings.smtp_username and settings.smtp_password
                and settings.smtp_security in {'ssl', 'starttls'} and 1 <= settings.smtp_port <= 65535)


@dataclass(frozen=True, slots=True, repr=False)
class SMTPDeliverySettings:
    """Only the six fields needed by send_code; never a runtime config proxy."""
    smtp_host: str
    smtp_port: int
    smtp_security: str
    smtp_username: str
    smtp_from: str
    smtp_password: str

    @classmethod
    def capture(cls, settings):
        return cls(settings.smtp_host, settings.smtp_port, settings.smtp_security,
                   settings.smtp_username, settings.smtp_from, settings.smtp_password)


class MailQueue:
    """One bounded sender. SMTP latency and provider errors are never HTTP evidence."""
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='agriscan-mail')
        self.slots = BoundedSemaphore(8)

    def submit(self, function):
        if not self.slots.acquire(blocking=False):
            return False
        def run():
            try: function()
            finally: self.slots.release()
        try:
            self.executor.submit(run)
            return True
        except RuntimeError:
            self.slots.release()
            return False

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


def install_account_recovery(app, settings, get_db, EmailBody, limit, send):
    from .extensions import EmailChallenge, UserEmail
    lock = app.state.email_lock
    app.state.email_mailer = MailQueue()
    router = APIRouter(prefix='/api/auth', route_class=ConfigRoute)

    class ResetBody(EmailBody):
        code: SecretStr = Field(min_length=6, max_length=6)
        new_password: SecretStr = Field(min_length=10, max_length=128)

        @field_validator('code')
        @classmethod
        def six_digits(cls, value):
            if not re.fullmatch(r'[0-9]{6}', value.get_secret_value()):
                raise ValueError('请输入六位数字验证码。')
            return value

    class BindBody(EmailBody):
        code: SecretStr = Field(min_length=6, max_length=6)
        current_password: SecretStr = Field(min_length=1, max_length=128)

        @field_validator('code')
        @classmethod
        def six_digits(cls, value):
            if not re.fullmatch(r'[0-9]{6}', value.get_secret_value()):
                raise ValueError('请输入六位数字验证码。')
            return value

    def keyed(value):
        return hmac.new(settings.jwt_secret.encode(), value.encode(), hashlib.sha256).hexdigest()

    def challenge_key(purpose, email, user_id=''):
        return email_challenge_key(settings, purpose, email, user_id)

    def code_digest(purpose, email, code, user_id=''):
        return keyed(purpose + ':' + (user_id + ':' if user_id else '') + email + ':' + code)

    def challenge(db, key):
        return db.scalar(_lock_query(db, select(EmailChallenge).where(EmailChallenge.email == key), True))

    def eligible(db, email, locked=False):
        binding = db.scalar(_lock_query(db, select(UserEmail).where(UserEmail.email == email), locked))
        marker = db.scalar(_lock_query(db, select(AppMeta).where(AppMeta.key == verified_key(email)), locked))
        user = db.scalar(_lock_query(db, select(User).where(User.id == binding.user_id), locked)) if binding else None
        return user if (user and user.is_active and marker and marker.value == user.id) else None

    def fresh_user(db, user_id, payload=None):
        user = db.scalar(_lock_query(db, select(User).where(User.id == user_id), True))
        if not user or not user.is_active:
            raise HTTPException(401, '登录会话已失效，请重新登录。')
        if payload and (time() >= payload['exp'] or db.get(RevokedToken, payload['jti'])
                        or not hmac.compare_digest(payload['credential'], credential_signature(user, settings.jwt_secret))):
            raise HTTPException(401, '登录会话已失效，请重新登录。')
        return user

    def attempt(row, purpose, email, code, user_id=''):
        if not row or row.expires_at <= utcnow() or row.attempts >= 5:
            return False
        row.attempts += 1
        return hmac.compare_digest(row.digest, code_digest(purpose, email, code, user_id))

    def invalidate(key, expected_digest):
        with lock, app.state.session() as db:
            row = challenge(db, key)
            if row and hmac.compare_digest(row.digest, expected_digest):
                row.expires_at = utcnow()
                db.commit()

    def queue_mail(email, code, purpose, key, expected_digest, user_id=''):
        # Capture while the HTTP request still has its immutable config context.
        # A blocked SMTP connection must never use credentials from a later edit.
        delivery_settings = SMTPDeliverySettings.capture(settings)
        def deliver():
            try:
                with lock, app.state.session() as db:
                    row = challenge(db, key)
                    if not row or row.digest != expected_digest or row.expires_at <= utcnow():
                        return
                    user = eligible(db, email) if purpose == 'password_reset' else db.get(User, user_id)
                    binding = db.get(UserEmail, email) if purpose == 'email_bind' else None
                    if binding and binding.user_id != user_id:
                        row.expires_at = utcnow(); db.commit(); return
                    if not user or not user.is_active or user.id != user_id:
                        row.expires_at = utcnow(); db.commit(); return
                send(delivery_settings, email, code, purpose)
            except Exception:
                # Do not log SMTP exceptions, credentials, email addresses or OTPs.
                try: invalidate(key, expected_digest)
                except Exception: pass
        if not app.state.email_mailer.submit(deliver):
            invalidate(key, expected_digest)

    @router.post('/password-reset-code')
    def reset_code(body: EmailBody, request: Request, db=Depends(get_db)):
        if not smtp_ready(settings):
            raise HTTPException(403, '邮箱找回暂未开放，请联系管理员。')
        limit(('reset-mail', request.client.host if request.client else 'unknown'), 8)
        email = body.email.strip().lower()
        key = challenge_key('password_reset', email)
        with lock:
            old = challenge(db, key)
            if old and (utcnow() - old.sent_at).total_seconds() < 60:
                return {'message': RESET_MESSAGE}
            code = f'{secrets.randbelow(1000000):06d}'
            user = eligible(db, email)
            issued_owner = user.id if user else UNVERIFIED_RESET_OWNER
            value = code_digest('password_reset', email, code, issued_owner)
            now = utcnow()
            db.merge(EmailChallenge(email=key, digest=value, sent_at=now,
                                    expires_at=now + timedelta(minutes=10), attempts=0))
            db.commit()
        # The same dispatch path is used for unbound, unverified and inactive emails.
        # It rechecks eligibility off the request path and sends no email to them.
        queue_mail(email, code, 'password_reset', key, value, issued_owner)
        return {'message': RESET_MESSAGE}

    @router.post('/password-reset')
    def reset_password(body: ResetBody, request: Request, db=Depends(get_db)):
        if not smtp_ready(settings):
            raise HTTPException(403, '邮箱找回暂未开放，请联系管理员。')
        limit(('reset-password', request.client.host if request.client else 'unknown'), 40)
        email = body.email.strip().lower()
        tasks = getattr(app.state, 'detection_tasks', None)
        with (tasks.condition if tasks else nullcontext()), lock:
            preliminary = eligible(db, email)
            if preliminary:
                try: fresh_user(db, preliminary.id)
                except HTTPException: pass
                db.expire_all()
            user = eligible(db, email, locked=True)
            row = challenge(db, challenge_key('password_reset', email))
            correct = attempt(row, 'password_reset', email, body.code.get_secret_value(),
                              user.id if user else UNVERIFIED_RESET_OWNER)
            if not user or not correct:
                db.commit()
                raise HTTPException(400, INVALID_CODE)
            user.password_hash = hash_password(body.new_password.get_secret_value())
            user.token_version += 1
            db.delete(row)
            db.commit()
            if tasks:
                tasks.cancel_user(user.id)
        return {'message': '密码已更新，请重新登录。'}

    @router.get('/email')
    def email_status(user=Depends(current_user), db=Depends(get_db)):
        binding = db.scalar(select(UserEmail).where(UserEmail.user_id == user.id))
        marker = db.get(AppMeta, verified_key(binding.email)) if binding else None
        return {'email': binding.email if binding else None, 'verified': bool(marker and marker.value == user.id)}

    @router.post('/email/verification-code')
    def binding_code(body: EmailBody, request: Request, user=Depends(current_user), db=Depends(get_db)):
        if not smtp_ready(settings):
            raise HTTPException(403, '邮箱验证暂未开放，请联系管理员。')
        limit(('bind-mail-ip', request.client.host if request.client else 'unknown'), 12)
        limit(('bind-mail-user', user.id), 8)
        email = body.email.strip().lower()
        key = challenge_key('email_bind', email, user.id)
        with lock:
            fresh_user(db, user.id, request.state.token_payload)
            old = challenge(db, key)
            if old and (utcnow() - old.sent_at).total_seconds() < 60:
                raise HTTPException(429, '请等待 60 秒后再发送。')
            code = f'{secrets.randbelow(1000000):06d}'
            value = code_digest('email_bind', email, code, user.id)
            now = utcnow()
            db.merge(EmailChallenge(email=key, digest=value, sent_at=now,
                                    expires_at=now + timedelta(minutes=10), attempts=0))
            db.commit()
        queue_mail(email, code, 'email_bind', key, value, user.id)
        return {'message': '如果该邮箱可用于绑定，验证码将发送至该邮箱，请稍后查收。'}

    @router.post('/email/verify')
    def bind_email(body: BindBody, request: Request, user=Depends(current_user), db=Depends(get_db)):
        limit(('bind-verify', user.id), 40)
        email = body.email.strip().lower()
        with lock:
            user = fresh_user(db, user.id, request.state.token_payload)
            row = challenge(db, challenge_key('email_bind', email, user.id))
            correct = attempt(row, 'email_bind', email, body.code.get_secret_value(), user.id)
            password_ok = verify_password(body.current_password.get_secret_value(), user.password_hash)
            target = db.get(UserEmail, email)
            if not correct or not password_ok or (target and target.user_id != user.id):
                db.commit()
                raise HTTPException(400, BIND_ERROR)
            old = db.scalar(select(UserEmail).where(UserEmail.user_id == user.id).with_for_update())
            if old and old.email != email:
                invalidate_email_proof(db, old.email, user.id, settings)
                db.delete(old); db.flush()
            if not target:
                db.add(UserEmail(email=email, user_id=user.id))
            invalidate_email_proof(db, email, user.id, settings)
            mark_verified(db, email, user.id)
            db.delete(row)
            try: db.commit()
            except IntegrityError:
                db.rollback()
                raise HTTPException(400, BIND_ERROR) from None
        return {'message': '邮箱已验证并绑定。', 'email': email, 'verified': True}

    app.include_router(router)
