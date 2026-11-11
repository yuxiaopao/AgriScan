"""Persistent editorial content and append-only administrative audit events."""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from .db import Timestamp, AppMeta, Base, new_id, utcnow


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"
    __table_args__ = (Index("ix_knowledge_status_updated", "status", "updated_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    crop: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    summary: Mapped[str] = mapped_column(String(1000))
    content: Mapped[str] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"))
    sources: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(Timestamp, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(Timestamp, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(Timestamp, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_created_id", "created_at", "id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80), index=True)
    resource_type: Mapped[str] = mapped_column(String(40), index=True)
    resource_id: Mapped[str] = mapped_column(String(100))
    summary: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(Timestamp, default=utcnow)


def iso_time(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value is not None else None


def article_data(row):
    return {
        "id": row.id, "title": row.title, "crop": row.crop, "category": row.category,
        "summary": row.summary, "content": row.content, "sources": row.sources,
        "image": None, "status": row.status, "created_by": row.created_by,
        "updated_by": row.updated_by, "created_at": iso_time(row.created_at),
        "updated_at": iso_time(row.updated_at), "published_at": iso_time(row.published_at),
    }


def audit_data(row):
    return {
        "id": row.id, "actor_id": row.actor_id, "actor_name": row.actor_name,
        "action": row.action, "resource_type": row.resource_type,
        "resource_id": row.resource_id, "summary": row.summary,
        "created_at": iso_time(row.created_at),
    }


def add_audit(db, user, action, resource_type, resource_id, summary):
    """Add to the caller's transaction; never commit a business change separately."""
    row = AuditLog(
        actor_id=user.id if user else None,
        actor_name=(user.username if user else "系统")[:80],
        action=action[:80], resource_type=resource_type[:40],
        resource_id=str(resource_id)[:100], summary=summary[:500],
    )
    db.add(row)
    return row


def initialize_admin_data(db):
    """Seed the original articles once, preserving all subsequent editorial changes."""
    from .seed import KNOWLEDGE

    if db.get(AppMeta, "knowledge_seed_v1"):
        return
    now = utcnow()
    for item in KNOWLEDGE:
        if db.get(KnowledgeArticle, item["id"]) is None:
            db.add(KnowledgeArticle(
                **{key: item[key] for key in ("id", "title", "crop", "category", "summary", "content", "sources")},
                status="published", created_at=now, updated_at=now, published_at=now,
            ))
    db.add(AppMeta(key="knowledge_seed_v1", value="initialized"))
