"""Account registration, inert model artifacts, and configurable LLM knowledge Q&A."""
import hashlib
import hmac
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, User, utcnow
from .inference import SUPPORTED_CROPS
from .security import current_user, hash_password, readable
from .assistant import install_assistant
from .detection_assistant import install_detection_assistant


class UserEmail(Base):
    __tablename__ = "user_emails"
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True)


class EmailChallenge(Base):
    __tablename__ = "email_challenges"
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    sent_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(default=0)


class ModelArtifact(Base):
    __tablename__ = "model_artifacts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    filename: Mapped[str] = mapped_column(String(200))
    stored_name: Mapped[str] = mapped_column(String(80))
    framework: Mapped[str] = mapped_column(String(80))
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class EmailBody(BaseModel):
    email: str = Field(max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=128)
    email: str = Field(default="", max_length=254)
    code: str = Field(default="", max_length=6)


class AskBody(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


def admin_user(user=Depends(current_user)):
    if user.role != "admin":
        raise HTTPException(403, "此操作需要管理员权限。")
    return user


def send_code(settings, email, code):
    message = EmailMessage()
    message["Subject"] = "禾观 · 注册邮箱验证码"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(f"你的注册验证码是 {code}，10 分钟内有效。如非本人操作，请忽略此邮件。")
    connection = smtplib.SMTP_SSL if settings.smtp_security == "ssl" else smtplib.SMTP
    options = {"context": ssl.create_default_context()} if settings.smtp_security == "ssl" else {}
    with connection(settings.smtp_host, settings.smtp_port, timeout=15, **options) as smtp:
        if settings.smtp_security == "starttls":
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def install_extensions(app, settings, get_db):
    limits = {}

    def limit(key, maximum=8):
        now = utcnow()
        # Bound memory while retaining active per-IP limits.
        for stale in [k for k, v in limits.items() if (now - v[0]).total_seconds() > 3600]:
            del limits[stale]
        if key not in limits:
            if len(limits) >= 10000:
                raise HTTPException(429, "请求过多，请稍后重试。")
            limits[key] = [now, 0]
        limits[key][1] += 1
        if limits[key][1] > maximum:
            raise HTTPException(429, "请求过于频繁，请一小时后重试。")

    def digest(email, code):
        return hmac.new(settings.jwt_secret.encode(), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()

    @app.get("/api/auth/config")
    def auth_config():
        return {"registration_enabled": settings.registration_enabled,
                "email_verification_enabled": settings.email_verification_enabled}

    @app.post("/api/auth/email-code")
    def email_code(body: EmailBody, request: Request, db=Depends(get_db)):
        if not settings.registration_enabled or not settings.email_verification_enabled:
            raise HTTPException(403, "当前未开启邮件验证注册。")
        limit(("mail", request.client.host))
        email = body.email.lower().strip()
        old = db.get(EmailChallenge, email)
        now = utcnow()
        if old and (now - old.sent_at).total_seconds() < 60:
            raise HTTPException(429, "请等待 60 秒后再发送。")
        code = f"{secrets.randbelow(1000000):06d}"
        try:
            send_code(settings, email, code)
        except Exception:
            raise HTTPException(503, "邮件发送失败，请管理员检查 SMTP 配置。")
        db.merge(EmailChallenge(email=email, digest=digest(email, code), sent_at=now,
                                expires_at=now + timedelta(minutes=10), attempts=0))
        db.commit()
        return {"message": "验证码已发送，10 分钟内有效。"}

    @app.post("/api/auth/register", status_code=201)
    def register(body: RegisterBody, request: Request, db=Depends(get_db)):
        if not settings.registration_enabled:
            raise HTTPException(403, "管理员已关闭注册。")
        limit(("register", request.client.host), 20)
        email = body.email.strip().lower()
        if email:
            try:
                EmailBody(email=email)
            except ValueError:
                raise HTTPException(422, "请输入有效邮箱。")
        challenge = None
        if settings.email_verification_enabled:
            challenge = db.get(EmailChallenge, email)
            if not challenge or challenge.expires_at < utcnow() or challenge.attempts >= 5:
                raise HTTPException(400, "验证码失效，请重新获取。")
            challenge.attempts += 1
            db.commit()
            if not hmac.compare_digest(challenge.digest, digest(email, body.code)):
                raise HTTPException(400, "验证码不正确。")
        user = User(username=body.username, name=body.name.strip(), role="member",
                    password_hash=hash_password(body.password))
        if not user.name:
            raise HTTPException(422, "昵称不能为空。")
        try:
            db.add(user)
            db.flush()
            if email:
                db.add(UserEmail(email=email, user_id=user.id))
            if challenge:
                db.delete(challenge)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "用户名或邮箱已注册。")
        return {"message": "注册成功，请使用新账户登录。"}

    @app.get("/api/settings/integrations", dependencies=[Depends(admin_user)])
    def integrations():
        return {**auth_config(), "smtp_host": settings.smtp_host, "smtp_port": settings.smtp_port,
                "smtp_from": settings.smtp_from, "smtp_security": settings.smtp_security,
                "smtp_password_configured": bool(settings.smtp_password),
                "llm_enabled": settings.llm_enabled, "llm_base_url": settings.llm_base_url,
                "llm_model": settings.llm_model, "llm_key_configured": bool(settings.llm_api_key),
                "model_max_upload_mb": settings.model_max_mb}

    @app.get("/api/models", dependencies=[Depends(readable)])
    def models(db=Depends(get_db)):
        rows = db.scalars(select(ModelArtifact).order_by(ModelArtifact.created_at.desc())).all()
        provider = app.state.inference
        return {"active": provider.active, "status": provider.status,
                "supported_crops": provider.supported_crops, "available_crops": SUPPORTED_CROPS,
                "message": "已启用单叶病害分类；不输出位置框，低置信度结果需人工复核。" if provider.active else "训练模型尚未启用，当前仅保存样本。",
                "items": [{"id": r.id, "name": r.name, "filename": r.filename, "framework": r.framework,
                           "size": r.size, "sha256": r.sha256, "status": "pending_validation",
                           "created_at": r.created_at.isoformat()} for r in rows],
                "max_upload_mb": settings.model_max_mb}

    @app.post("/api/models", status_code=201, dependencies=[Depends(admin_user)])
    async def upload_model(file: UploadFile = File(...), name: str = Form(...),
                           framework: str = Form("PyTorch / YOLO"), db=Depends(get_db)):
        if not name.strip() or len(name) > 100 or len(framework) > 80:
            raise HTTPException(422, "请填写有效模型名称及训练框架。")
        filename = (file.filename or "").replace("\\", "/").split("/")[-1]
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pt", ".pth", ".onnx", ".safetensors", ".h5", ".keras"} or len(filename) > 200:
            raise HTTPException(422, "支持 .pt、.pth、.onnx、.safetensors、.h5、.keras 权重。")
        folder = settings.upload_dir / "models"
        folder.mkdir(parents=True, exist_ok=True)
        model_id = uuid4().hex
        target = folder / (model_id + suffix)
        size, sha = 0, hashlib.sha256()
        try:
            with target.open("xb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.model_max_mb * 1024 * 1024:
                        raise HTTPException(413, "权重文件超过配置的上传上限。")
                    sha.update(chunk)
                    output.write(chunk)
            if size == 0:
                raise HTTPException(422, "权重文件不能为空。")
            db.add(ModelArtifact(id=model_id, name=name.strip(), filename=filename,
                                 stored_name=target.name, framework=framework, size=size, sha256=sha.hexdigest()))
            db.commit()
        except BaseException:
            db.rollback()
            target.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        return {"id": model_id, "status": "pending_validation", "message": "权重已保存，等待推理适配与验证。"}

    @app.delete("/api/models/{model_id}", dependencies=[Depends(admin_user)])
    def delete_model(model_id: str, db=Depends(get_db)):
        row = db.get(ModelArtifact, model_id)
        if not row:
            raise HTTPException(404, "模型不存在。")
        target = settings.upload_dir / "models" / row.stored_name
        db.delete(row)
        db.commit()
        target.unlink(missing_ok=True)
        return {"message": "权重已删除。"}

    def answer_for(user, messages):
        if not settings.llm_enabled:
            raise HTTPException(503, "小禾问答暂未启用，请联系管理员。")
        limit(("llm", user.id), 30)
        try:
            response = httpx.post(settings.llm_base_url.rstrip("/") + "/chat/completions",
                headers={"Authorization": "Bearer " + settings.llm_api_key},
                json={"model": settings.llm_model, "messages": [
                    {"role": "system", "content": "你是农业知识助手小禾，对外使用小禾这一名称，不主动介绍底层模型名称、服务商或接口配置。用中文解释作物观察与养护。仅在请求实际附带图片时描述图片中可见的情况，照片解读属于辅助评估，不能当作确诊；没有图片时不得声称看过照片。区分病害和虫害，证据不足时明确无法确认。具体用药遵循当地登记标签和现场农技指导。"},
                    *messages], "max_tokens": 1200},
                timeout=settings.llm_timeout, trust_env=False)
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip() or len(answer) > 12000:
                raise ValueError("Empty answer")
        except Exception:
            raise HTTPException(502, "小禾暂时无法回答，请稍后重试或联系管理员。")
        return answer

    @app.post("/api/knowledge/ask")
    def ask(body: AskBody, user=Depends(current_user)):
        return {"answer": answer_for(user, [{"role": "user", "content": body.question}])}

    install_assistant(app, get_db, answer_for)
    install_detection_assistant(app, get_db, answer_for)
