import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .db import RevokedToken, User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    return f"pbkdf2_sha256$600000${salt}${digest}"


def verify_password(password: str, encoded: str):
    try:
        _, rounds, salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def credential_signature(user: User, secret: str):
    credential_state = f"{user.username}:{user.password_hash}".encode()
    return hmac.new(secret.encode(), credential_state, hashlib.sha256).hexdigest()


def issue_token(user: User, settings):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": user.id, "jti": uuid4().hex, "iat": now,
            "exp": now + timedelta(hours=settings.token_hours),
            "credential": credential_signature(user, settings.jwt_secret),
        },
        settings.jwt_secret, algorithm="HS256",
    )


def current_user(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    error = HTTPException(401, "请先登录，或重新登录以刷新会话。", headers={"WWW-Authenticate": "Bearer"})
    if not credentials:
        raise error
    try:
        payload = jwt.decode(
            credentials.credentials, request.app.state.settings.jwt_secret,
            algorithms=["HS256"], options={"require": ["exp", "sub", "jti", "iat", "credential"]},
        )
        with request.app.state.session() as db:
            if db.get(RevokedToken, payload["jti"]):
                raise error
            user = db.get(User, payload["sub"])
            if not user:
                raise error
            if not isinstance(payload["credential"], str) or not hmac.compare_digest(
                payload["credential"], credential_signature(user, request.app.state.settings.jwt_secret),
            ):
                raise error
            request.state.token_payload = payload
            return user
    except jwt.InvalidTokenError:
        raise error


def readable(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if request.app.state.settings.demo_mode and credentials is None:
        return None
    return current_user(request, credentials)
