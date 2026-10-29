"""Adopt the existing schema without dropping or rebuilding business tables."""
from alembic import op
import sqlalchemy as sa

revision = "20261028_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # A frozen baseline also fills in tables missing from earlier local versions.
    metadata = sa.MetaData()
    sa.Table("users", metadata,
             sa.Column("id", sa.String(32), primary_key=True),
             sa.Column("username", sa.String(80), nullable=False, unique=True),
             sa.Column("password_hash", sa.String(256), nullable=False),
             sa.Column("name", sa.String(80), nullable=False),
             sa.Column("role", sa.String(30), nullable=False))
    sa.Table("plots", metadata,
             sa.Column("id", sa.String(32), primary_key=True),
             sa.Column("name", sa.String(100), nullable=False),
             sa.Column("crop", sa.String(40), nullable=False),
             sa.Column("area", sa.Float, nullable=False),
             sa.Column("location", sa.String(200), nullable=False),
             sa.Column("manager", sa.String(80), nullable=False))
    sa.Table("plot_details", metadata,
             sa.Column("plot_id", sa.String(32), sa.ForeignKey("plots.id", ondelete="CASCADE"), primary_key=True),
             sa.Column("cover_filename", sa.String(36)),
             sa.Column("latitude", sa.Double), sa.Column("longitude", sa.Double))
    sa.Table("detections", metadata,
             sa.Column("id", sa.String(32), primary_key=True),
             sa.Column("name", sa.String(200), nullable=False),
             sa.Column("crop", sa.String(40), nullable=False, index=True),
             sa.Column("plot_id", sa.String(32), sa.ForeignKey("plots.id", ondelete="SET NULL")),
             sa.Column("status", sa.String(30), nullable=False, index=True),
             sa.Column("result", sa.String(200)), sa.Column("confidence", sa.Float),
             sa.Column("created_at", sa.DateTime, nullable=False, index=True),
             sa.Column("image_url", sa.String(500)),
             sa.Column("is_demo", sa.Boolean, nullable=False),
             sa.Column("note", sa.Text, nullable=False))
    sa.Table("detection_predictions", metadata,
             sa.Column("detection_id", sa.String(32), sa.ForeignKey("detections.id", ondelete="CASCADE"), primary_key=True),
             sa.Column("candidates", sa.JSON, nullable=False), sa.Column("model", sa.JSON, nullable=False))
    sa.Table("app_meta", metadata,
             sa.Column("key", sa.String(80), primary_key=True), sa.Column("value", sa.String(100), nullable=False))
    sa.Table("revoked_tokens", metadata,
             sa.Column("jti", sa.String(32), primary_key=True),
             sa.Column("expires_at", sa.DateTime, nullable=False, index=True))
    sa.Table("user_emails", metadata,
             sa.Column("email", sa.String(254), primary_key=True),
             sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False, unique=True))
    sa.Table("email_challenges", metadata,
             sa.Column("email", sa.String(254), primary_key=True),
             sa.Column("digest", sa.String(64), nullable=False),
             sa.Column("expires_at", sa.DateTime, nullable=False),
             sa.Column("sent_at", sa.DateTime, nullable=False), sa.Column("attempts", sa.Integer, nullable=False))
    sa.Table("model_artifacts", metadata,
             sa.Column("id", sa.String(32), primary_key=True),
             sa.Column("name", sa.String(100), nullable=False),
             sa.Column("filename", sa.String(200), nullable=False),
             sa.Column("stored_name", sa.String(80), nullable=False),
             sa.Column("framework", sa.String(80), nullable=False),
             sa.Column("size", sa.BigInteger, nullable=False),
             sa.Column("sha256", sa.String(64), nullable=False),
             sa.Column("created_at", sa.DateTime, nullable=False))
    sa.Table("assistant_conversations", metadata,
             sa.Column("id", sa.String(32), primary_key=True),
             sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False, index=True),
             sa.Column("title", sa.String(80), nullable=False),
             sa.Column("updated_at", sa.DateTime, nullable=False, index=True),
             sa.Column("busy_until", sa.DateTime, nullable=False))
    sa.Table("assistant_messages", metadata,
             sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
             sa.Column("conversation_id", sa.String(32), sa.ForeignKey("assistant_conversations.id"), nullable=False, index=True),
             sa.Column("role", sa.String(20), nullable=False), sa.Column("content", sa.Text, nullable=False),
             sa.Column("created_at", sa.DateTime, nullable=False))
    sa.Table("assistant_detection_discussions", metadata,
             sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), primary_key=True),
             sa.Column("detection_id", sa.String(32), primary_key=True),
             sa.Column("conversation_id", sa.String(32), sa.ForeignKey("assistant_conversations.id"), nullable=False, unique=True))
    metadata.create_all(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("The adoption baseline preserves existing data; restore a backup instead of dropping business tables.")
