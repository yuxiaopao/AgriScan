"""Administrator-only user, editorial, operations and audit APIs."""
from datetime import date, datetime, time, timedelta, timezone
import csv
import io
import re
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import lazyload, selectinload

from .admin_models import AuditLog, KnowledgeArticle, add_audit, article_data, audit_data, iso_time
from .db import AppMeta, Detection, Plot, User, utcnow
from .extensions import ModelArtifact, UserEmail
from .inference import SUPPORTED_CROPS
from .security import bearer, current_user, hash_password

Role = Literal["admin", "member"]
ArticleStatus = Literal["draft", "published", "archived"]
AccountStatus = Literal["active", "disabled"]
DETECTION_STATUSES = {"healthy", "attention", "awaiting_model", "queued", "processing", "failed"}
BUSINESS_TIMEZONE = timezone(timedelta(hours=8))
MAX_EXPORT_ROWS = 10_000


def normalize_email(value):
    value = value.strip().lower()
    if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        raise ValueError("请输入有效邮箱地址，或留空清除邮箱。")
    return value


class AdminBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UserCreate(AdminBody):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=128)
    role: Role = "member"
    is_active: bool = True
    status: AccountStatus | None = None
    email: str = Field(default="", max_length=254)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("显示名称不能为空。")
        return value.strip()

    @field_validator("email")
    @classmethod
    def clean_email(cls, value):
        return normalize_email(value)

    @model_validator(mode="after")
    def matching_status(self):
        if self.status is not None:
            active = self.status == "active"
            if "is_active" in self.model_fields_set and self.is_active != active:
                raise ValueError("status 与 is_active 不一致。")
            self.is_active = active
        return self


class UserPatch(AdminBody):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    role: Role | None = None
    is_active: bool | None = None
    status: AccountStatus | None = None
    email: str | None = Field(default=None, max_length=254)

    @field_validator("name", "role", "is_active", "status", "email")
    @classmethod
    def no_null(cls, value):
        if value is None:
            raise ValueError("此字段不可为空。")
        return value

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("显示名称不能为空。")
        return value.strip()

    @field_validator("email")
    @classmethod
    def clean_email(cls, value):
        return normalize_email(value)

    @model_validator(mode="after")
    def matching_status(self):
        if self.status is not None and self.is_active is not None:
            if self.is_active != (self.status == "active"):
                raise ValueError("status 与 is_active 不一致。")
        return self


class PasswordBody(AdminBody):
    password: str = Field(min_length=10, max_length=128)


class ArticleSource(AdminBody):
    title: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if not value.strip():
            raise ValueError("来源标题不能为空。")
        return value.strip()

    @field_validator("url")
    @classmethod
    def safe_url(cls, value):
        value = value.strip()
        try:
            parsed = urlsplit(value)
            valid = parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username and not parsed.password
        except ValueError:
            valid = False
        if not valid:
            raise ValueError("来源链接必须是有效的 HTTP 或 HTTPS 地址。")
        return value


class ArticleCreate(AdminBody):
    title: str = Field(min_length=1, max_length=200)
    crop: str = Field(default="", max_length=40)
    category: str = Field(min_length=1, max_length=80)
    summary: str = Field(default="", max_length=1000)
    content: str = Field(default="", max_length=50000)
    sources: list[ArticleSource] = Field(default_factory=list, max_length=20)
    status: ArticleStatus = "draft"

    @field_validator("title", "category")
    @classmethod
    def nonempty_text(cls, value):
        if not value.strip():
            raise ValueError("标题和分类不能为空。")
        return value.strip()

    @field_validator("crop")
    @classmethod
    def crop_supported(cls, value):
        value = value.strip()
        if value and value not in SUPPORTED_CROPS:
            raise ValueError("请选择支持的作物，通用内容可留空。")
        return value


class ArticlePatch(AdminBody):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    crop: str | None = Field(default=None, max_length=40)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    summary: str | None = Field(default=None, max_length=1000)
    content: str | None = Field(default=None, max_length=50000)
    sources: list[ArticleSource] | None = Field(default=None, max_length=20)
    status: ArticleStatus | None = None

    @field_validator("title", "crop", "category", "summary", "content", "sources", "status")
    @classmethod
    def no_null(cls, value):
        if value is None:
            raise ValueError("此字段不可为空。")
        return value

    @field_validator("title", "category")
    @classmethod
    def nonempty_text(cls, value):
        return ArticleCreate.nonempty_text(value)

    @field_validator("crop")
    @classmethod
    def crop_supported(cls, value):
        return ArticleCreate.crop_supported(value)


class DetectionPatch(AdminBody):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    note: str | None = Field(default=None, max_length=2000)
    plot_id: str | None = Field(default=None, max_length=32)

    @field_validator("name", "note")
    @classmethod
    def no_null(cls, value):
        if value is None:
            raise ValueError("此字段不可为空。")
        return value

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value):
        if not value.strip():
            raise ValueError("样本名称不能为空。")
        return value.strip()


def administrator(request: Request, credentials=Depends(bearer)):
    if credentials is None:
        raise HTTPException(403, "此页面需要管理员登录。")
    user = current_user(request, credentials)
    if user.role != "admin":
        raise HTTPException(403, "此操作需要管理员权限。")
    return user


def managed_admin_id(db):
    marker = db.get(AppMeta, "managed_admin_id")
    return marker.value if marker else None


def user_data(row, email, managed_id, actor_id):
    managed = row.id == managed_id
    return {
        "id": row.id, "username": row.username, "name": row.name, "role": row.role,
        "is_active": row.is_active, "status": "active" if row.is_active else "disabled",
        "email": email, "managed": managed, "is_managed": managed, "is_self": row.id == actor_id,
        "created_at": iso_time(row.created_at), "updated_at": iso_time(row.updated_at),
    }


def commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "用户名或邮箱已被使用，或数据已变化，请刷新后重试。")


def paginated(db, statement, page, page_size, serializer):
    total = db.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    rows = db.scalars(statement.offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [serializer(row) for row in rows], "total": total, "page": page, "page_size": page_size}


def set_email(db, user_id, email):
    previous = db.scalar(select(UserEmail).where(UserEmail.user_id == user_id))
    if previous and previous.email == email:
        return
    existing = db.get(UserEmail, email) if email else None
    if existing and existing.user_id != user_id:
        raise HTTPException(409, "此邮箱已被使用。")
    if previous:
        db.delete(previous)
        db.flush()
    if email:
        db.add(UserEmail(email=email, user_id=user_id))


def ensure_publishable(row):
    if row.status == "published" and not row.content.strip():
        raise HTTPException(422, "发布前请填写文章正文。")


def local_boundary(day, end=False):
    """Dates in the UI are Chinese calendar days; stored timestamps remain UTC."""
    try:
        value = datetime.combine(day, time.max if end else time.min, BUSINESS_TIMEZONE)
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    except (OverflowError, ValueError):
        raise HTTPException(422, "日期超出可查询范围。")


def filtered_detections(search, crop, status, plot_id, source, date_from, date_to):
    """Use identical filters for administrative pagination and full-result export."""
    if crop and crop not in SUPPORTED_CROPS:
        raise HTTPException(422, "暂不支持该作物。")
    if status and status not in DETECTION_STATUSES:
        raise HTTPException(422, "无效的检测状态。")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "起始日期不能晚于结束日期。")
    query = select(Detection).options(selectinload(Detection.plot))
    if crop:
        query = query.where(Detection.crop == crop)
    if status:
        query = query.where(Detection.status == status)
    if plot_id:
        query = query.where(Detection.plot_id == plot_id)
    if source != "all":
        query = query.where(Detection.is_demo == (source == "demo"))
    if date_from:
        query = query.where(Detection.created_at >= local_boundary(date_from))
    if date_to:
        query = query.where(Detection.created_at <= local_boundary(date_to, end=True))
    if search.strip():
        query = query.where(or_(*[column.contains(search.strip(), autoescape=True) for column in (
            Detection.id, Detection.name, Detection.crop, Detection.result, Detection.note)]))
    return query.order_by(Detection.created_at.desc(), Detection.id.desc())


def csv_cell(value):
    value = "" if value is None else str(value)
    # Quoting CSV fields alone does not stop spreadsheet formula execution.
    if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) or value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def install_admin(app, get_db, detection_data, plot_data):
    router = APIRouter(prefix="/api/admin", tags=["admin"])

    def serialize_user(db, row, actor):
        email = db.scalar(select(UserEmail.email).where(UserEmail.user_id == row.id)) or ""
        return user_data(row, email, managed_admin_id(db), actor.id)

    def changed():
        app.state.cache.invalidate()

    @router.get("/overview")
    def overview(days: int = Query(7, ge=1, le=30), actor=Depends(administrator), db=Depends(get_db)):
        if days not in {7, 30}:
            raise HTTPException(422, "days 仅支持 7 或 30。")
        today = utcnow().replace(tzinfo=timezone.utc).astimezone(BUSINESS_TIMEZONE).date()
        first = today - timedelta(days=days - 1)
        day_column = (func.date(Detection.created_at, "+8 hours") if db.bind.dialect.name == "sqlite"
                      else func.date(Detection.created_at + text("INTERVAL 8 HOUR")))
        daily = db.execute(select(
            day_column, func.count(Detection.id),
            func.sum(case((Detection.status == "attention", 1), else_=0)),
        ).where(Detection.created_at >= local_boundary(first),
                Detection.created_at <= local_boundary(today, end=True))
          .group_by(day_column)).all()
        grouped = {str(day): (total, attention) for day, total, attention in daily}
        trend = []
        for offset in range(days):
            day = (first + timedelta(days=offset)).isoformat()
            total, attention = grouped.get(day, (0, 0))
            trend.append({"date": day, "total": total, "attention": int(attention)})
        def count(model, *conditions):
            return db.scalar(select(func.count()).select_from(model).where(*conditions))
        activity = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(8)).all()
        return {
            "counts": {"users": count(User), "active_users": count(User, User.is_active.is_(True)),
                       "plots": count(Plot), "detections": count(Detection),
                       "published_articles": count(KnowledgeArticle, KnowledgeArticle.status == "published"),
                       "model_artifacts": count(ModelArtifact)},
            "services": {"database": "connected", "redis": app.state.cache.status(), "model": app.state.inference.status},
            "recent_activity": [audit_data(row) for row in activity], "trend": trend,
        }

    @router.get("/users")
    def users(search: str = Query("", max_length=100), role: Role | None = None,
              status: AccountStatus | None = None, is_active: bool | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
              actor=Depends(administrator), db=Depends(get_db)):
        query = select(User)
        if role:
            query = query.where(User.role == role)
        if status is not None:
            active = status == "active"
            if is_active is not None and is_active != active:
                raise HTTPException(422, "status 与 is_active 不一致。")
            is_active = active
        if is_active is not None:
            query = query.where(User.is_active == is_active)
        if search.strip():
            value = search.strip()
            email_ids = select(UserEmail.user_id).where(UserEmail.email.contains(value, autoescape=True))
            query = query.where(or_(User.username.contains(value, autoescape=True),
                                    User.name.contains(value, autoescape=True), User.id.in_(email_ids)))
        emails = dict(db.execute(select(UserEmail.user_id, UserEmail.email)).all())
        managed = managed_admin_id(db)
        return paginated(db, query.order_by(User.created_at.desc(), User.id.desc()), page, page_size,
                         lambda row: user_data(row, emails.get(row.id, ""), managed, actor.id))

    @router.post("/users", status_code=201)
    def create_user(body: UserCreate, actor=Depends(administrator), db=Depends(get_db)):
        if db.scalar(select(User.id).where(User.username == body.username)):
            raise HTTPException(409, "用户名已被使用。")
        row = User(username=body.username, name=body.name, role=body.role,
                   is_active=body.is_active, password_hash=hash_password(body.password))
        db.add(row)
        try:
            db.flush()
            set_email(db, row.id, body.email)
            add_audit(db, actor, "user.create", "user", row.id, f"创建账号 {row.username}，角色 {row.role}")
            commit(db)
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "用户名或邮箱已被使用。")
        changed()
        return serialize_user(db, row, actor)

    @router.patch("/users/{user_id}")
    def update_user(user_id: str, body: UserPatch, actor=Depends(administrator), db=Depends(get_db)):
        row = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if not row:
            raise HTTPException(404, "用户不存在。")
        values = body.model_dump(exclude_unset=True)
        status = values.pop("status", None)
        if status is not None:
            values["is_active"] = status == "active"
        lowering = values.get("role", row.role) != "admin" or not values.get("is_active", row.is_active)
        if row.id == managed_admin_id(db) and lowering:
            raise HTTPException(409, "环境管理员不可禁用或降权，请通过部署配置管理。")
        if row.id == actor.id and lowering:
            raise HTTPException(409, "不能禁用或降低自己的管理员权限。")
        if row.role == "admin" and row.is_active and lowering:
            active_admins = db.scalars(select(User.id).where(User.role == "admin", User.is_active.is_(True))
                                      .order_by(User.id).with_for_update()).all()
            if len(active_admins) <= 1:
                raise HTTPException(409, "必须保留至少一位启用的管理员。")
        credential_changed = any(key in values and values[key] != getattr(row, key) for key in ("role", "is_active"))
        if "email" in values:
            set_email(db, row.id, values.pop("email"))
        for key, value in values.items():
            setattr(row, key, value)
        if credential_changed:
            row.token_version += 1
        row.updated_at = utcnow()
        add_audit(db, actor, "user.update", "user", row.id, f"更新账号 {row.username} 的资料或权限")
        commit(db)
        changed()
        return serialize_user(db, row, actor)

    @router.post("/users/{user_id}/password")
    def reset_password(user_id: str, body: PasswordBody, actor=Depends(administrator), db=Depends(get_db)):
        row = db.scalar(select(User).where(User.id == user_id).with_for_update())
        if not row:
            raise HTTPException(404, "用户不存在。")
        if row.id == managed_admin_id(db):
            raise HTTPException(409, "环境管理员密码由部署配置管理，不能在界面重置。")
        row.password_hash = hash_password(body.password)
        row.token_version += 1
        row.updated_at = utcnow()
        add_audit(db, actor, "user.password_reset", "user", row.id, f"重置账号 {row.username} 密码并使旧会话失效")
        commit(db)
        changed()
        return {"message": "密码已重置，旧会话已失效。"}

    @router.get("/knowledge")
    def knowledge(search: str = Query("", max_length=100), crop: str = Query("", max_length=40),
                  status: ArticleStatus | None = None, category: str = Query("", max_length=80),
                  page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                  actor=Depends(administrator), db=Depends(get_db)):
        query = select(KnowledgeArticle)
        if crop:
            query = query.where(KnowledgeArticle.crop == crop)
        if status:
            query = query.where(KnowledgeArticle.status == status)
        if category:
            query = query.where(KnowledgeArticle.category == category)
        if search.strip():
            query = query.where(or_(*[column.contains(search.strip(), autoescape=True) for column in (
                KnowledgeArticle.title, KnowledgeArticle.summary, KnowledgeArticle.category, KnowledgeArticle.content)]))
        return paginated(db, query.order_by(KnowledgeArticle.updated_at.desc(), KnowledgeArticle.id.desc()),
                         page, page_size, article_data)

    @router.post("/knowledge", status_code=201)
    def create_article(body: ArticleCreate, actor=Depends(administrator), db=Depends(get_db)):
        now = utcnow()
        row = KnowledgeArticle(**body.model_dump(), created_by=actor.id, updated_by=actor.id,
                               published_at=now if body.status == "published" else None)
        ensure_publishable(row)
        db.add(row)
        db.flush()
        add_audit(db, actor, "knowledge.create", "knowledge", row.id, f"创建知识文章：{row.title}")
        commit(db)
        changed()
        return article_data(row)

    @router.patch("/knowledge/{article_id}")
    def update_article(article_id: str, body: ArticlePatch, actor=Depends(administrator), db=Depends(get_db)):
        row = db.scalar(select(KnowledgeArticle).where(KnowledgeArticle.id == article_id).with_for_update())
        if not row:
            raise HTTPException(404, "文章不存在。")
        old_status = row.status
        for key, value in body.model_dump(exclude_unset=True).items():
            setattr(row, key, value)
        ensure_publishable(row)
        row.updated_by, row.updated_at = actor.id, utcnow()
        if row.status == "published" and old_status != "published":
            row.published_at = row.updated_at
        add_audit(db, actor, "knowledge.update", "knowledge", row.id, f"更新知识文章：{row.title}（{row.status}）")
        commit(db)
        changed()
        return article_data(row)

    @router.delete("/knowledge/{article_id}")
    def archive_article(article_id: str, actor=Depends(administrator), db=Depends(get_db)):
        row = db.scalar(select(KnowledgeArticle).where(KnowledgeArticle.id == article_id).with_for_update())
        if not row:
            raise HTTPException(404, "文章不存在。")
        row.status, row.updated_by, row.updated_at = "archived", actor.id, utcnow()
        add_audit(db, actor, "knowledge.archive", "knowledge", row.id, f"归档知识文章：{row.title}")
        commit(db)
        changed()
        return article_data(row)

    @router.get("/detections")
    def detections(search: str = Query("", max_length=100), crop: str = "", status: str = "",
                   plot_id: str = "", source: Literal["all", "demo", "real", "upload"] = "all",
                   date_from: date | None = None, date_to: date | None = None,
                   page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   actor=Depends(administrator), db=Depends(get_db)):
        query = filtered_detections(search, crop, status, plot_id, source, date_from, date_to)
        return paginated(db, query, page, page_size, detection_data)

    @router.get("/detections/export.csv")
    def export_detections(search: str = Query("", max_length=100), crop: str = "", status: str = "",
                          plot_id: str = "", source: Literal["all", "demo", "real", "upload"] = "all",
                          date_from: date | None = None, date_to: date | None = None,
                          actor=Depends(administrator), db=Depends(get_db)):
        query = filtered_detections(search, crop, status, plot_id, source, date_from, date_to)
        total = db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        if total > MAX_EXPORT_ROWS:
            raise HTTPException(422, "匹配记录超过 10000 条，请缩小日期、作物或地块筛选范围后重试导出。")
        rows = db.scalars(query.options(lazyload(Detection.prediction)).limit(MAX_EXPORT_ROWS + 1)).all()
        if len(rows) > MAX_EXPORT_ROWS:
            raise HTTPException(422, "匹配记录超过 10000 条，请缩小筛选范围后重试导出。")
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["id", "name", "crop", "plot_name", "status", "result", "confidence", "created_at", "is_demo", "note"])
        for row in rows:
            writer.writerow([csv_cell(value) for value in (
                row.id, row.name, row.crop, row.plot.name if row.plot else "未关联地块",
                row.status, row.result, row.confidence, iso_time(row.created_at),
                "true" if row.is_demo else "false", row.note,
            )])
        return Response(
            content=("\ufeff" + output.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="agriscan-detections.csv"', "Cache-Control": "no-store"},
        )

    @router.patch("/detections/{detection_id}")
    def update_detection(detection_id: str, body: DetectionPatch, actor=Depends(administrator), db=Depends(get_db)):
        row = db.scalar(select(Detection).options(selectinload(Detection.plot))
                        .where(Detection.id == detection_id).with_for_update())
        if not row:
            raise HTTPException(404, "检测记录不存在。")
        values = body.model_dump(exclude_unset=True)
        if "plot_id" in values:
            plot_id = values.pop("plot_id") or None
            plot = db.get(Plot, plot_id) if plot_id else None
            if plot_id and not plot:
                raise HTTPException(404, "关联地块不存在。")
            detected_crops = {row.crop}
            if row.prediction:
                detected_crops.update(box['crop'] for box in row.prediction.model.get('boxes', []) if box.get('crop'))
            if plot and any(crop != plot.crop for crop in detected_crops):
                crop_summary = '、'.join(sorted(detected_crops))
                raise HTTPException(422, f"检测目标包含{crop_summary}，与所选{plot.crop}地块不一致，请更换地块或取消关联后重试。")
            row.plot = plot
        for key, value in values.items():
            setattr(row, key, value.strip() if key == "note" else value)
        add_audit(db, actor, "detection.update", "detection", row.id, f"更新样本 {row.name} 的名称、备注或地块关联")
        commit(db)
        changed()
        return detection_data(row)

    @router.get("/plots")
    def plots(search: str = Query("", max_length=100), crop: str = "",
              page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
              actor=Depends(administrator), db=Depends(get_db)):
        if crop and crop not in SUPPORTED_CROPS:
            raise HTTPException(422, "暂不支持该作物。")
        query = select(Plot).options(selectinload(Plot.detections), selectinload(Plot.details))
        if crop:
            query = query.where(Plot.crop == crop)
        if search.strip():
            query = query.where(or_(*[column.contains(search.strip(), autoescape=True) for column in (
                Plot.name, Plot.location, Plot.manager)]))
        return paginated(db, query.order_by(Plot.name, Plot.id), page, page_size, plot_data)

    @router.get("/audit")
    def audit(action: str = Query("", max_length=80), resource_type: str = Query("", max_length=40),
              search: str = Query("", max_length=100),
              page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
              actor=Depends(administrator), db=Depends(get_db)):
        query = select(AuditLog)
        if action:
            query = query.where(AuditLog.action == action)
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)
        if search.strip():
            query = query.where(or_(*[column.contains(search.strip(), autoescape=True) for column in (
                AuditLog.actor_name, AuditLog.summary, AuditLog.resource_id)]))
        return paginated(db, query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()),
                         page, page_size, audit_data)

    app.include_router(router)
