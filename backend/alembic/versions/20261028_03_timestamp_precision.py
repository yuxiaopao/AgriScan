"""Preserve microseconds when moving local SQLite records into MySQL."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = "20261028_03"
down_revision = "20261028_02"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "mysql":
        return
    columns = {
        "users": {"created_at": True, "updated_at": True},
        "detections": {"created_at": False},
        "revoked_tokens": {"expires_at": False},
        "email_challenges": {"expires_at": False, "sent_at": False},
        "model_artifacts": {"created_at": False},
        "assistant_conversations": {"updated_at": False, "busy_until": False},
        "assistant_messages": {"created_at": False},
        "knowledge_articles": {"created_at": False, "updated_at": False, "published_at": True},
        "audit_logs": {"created_at": False},
    }
    for table, fields in columns.items():
        for name, nullable in fields.items():
            op.alter_column(table, name, existing_type=sa.DateTime(),
                            type_=DATETIME(fsp=6), existing_nullable=nullable)


def downgrade():
    raise RuntimeError("Downgrading would discard timestamp precision; restore a matching backup instead.")
