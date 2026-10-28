"""Add account lifecycle, editable knowledge, and administrator audit history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = "20261028_02"
down_revision = "20261028_01"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("users")}
    additions = [
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("token_version", sa.Integer, nullable=False, server_default="0"),
        # Old accounts did not record registration time; leave it unknown.
        sa.Column("created_at", sa.DateTime, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    ]
    for column in additions:
        if column.name not in columns:
            op.add_column("users", column)
    conversations = {column["name"] for column in sa.inspect(bind).get_columns("assistant_conversations")}
    if "busy_until" not in conversations:
        op.add_column("assistant_conversations", sa.Column(
            "busy_until", sa.DateTime, nullable=False, server_default="2000-01-01 00:00:00"))
    metadata = sa.MetaData()
    sa.Table("users", metadata, sa.Column("id", sa.String(32), primary_key=True))
    articles = sa.Table("knowledge_articles", metadata,
             sa.Column("id", sa.String(32), primary_key=True),
             sa.Column("title", sa.String(200), nullable=False),
             sa.Column("crop", sa.String(40), nullable=False, index=True),
             sa.Column("category", sa.String(80), nullable=False, index=True),
             sa.Column("summary", sa.String(1000), nullable=False),
             sa.Column("content", sa.Text().with_variant(MEDIUMTEXT(), "mysql"), nullable=False),
             sa.Column("sources", sa.JSON, nullable=False),
             sa.Column("status", sa.String(20), nullable=False),
             sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL")),
             sa.Column("updated_by", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL")),
             sa.Column("created_at", sa.DateTime, nullable=False),
             sa.Column("updated_at", sa.DateTime, nullable=False),
             sa.Column("published_at", sa.DateTime),
             sa.Index("ix_knowledge_status_updated", "status", "updated_at"))
    audits = sa.Table("audit_logs", metadata,
             sa.Column("id", sa.String(32), primary_key=True),
             sa.Column("actor_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL")),
             sa.Column("actor_name", sa.String(80), nullable=False),
             sa.Column("action", sa.String(80), nullable=False, index=True),
             sa.Column("resource_type", sa.String(40), nullable=False, index=True),
             sa.Column("resource_id", sa.String(100), nullable=False),
             sa.Column("summary", sa.String(500), nullable=False),
             sa.Column("created_at", sa.DateTime, nullable=False),
             sa.Index("ix_audit_created_id", "created_at", "id"))
    metadata.create_all(bind, tables=[articles, audits], checkfirst=True)
    existing_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("detections")}
    if "ix_detections_created_id" not in existing_indexes:
        op.create_index("ix_detections_created_id", "detections", ["created_at", "id"])


def downgrade():
    raise RuntimeError("Account state and audit history must be retained; restore a matching backup to downgrade.")
