"""Preserve model confidence and plot area as double precision on MySQL."""
from alembic import op
import sqlalchemy as sa

revision = "20261028_04"
down_revision = "20261028_03"
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != "mysql":
        return
    # Widen in place: this preserves stored values but cannot recover precision
    # already lost to FLOAT. Restoring original values requires a trusted backup.
    op.alter_column("plots", "area", existing_type=sa.Float(), type_=sa.Double(), existing_nullable=False)
    op.alter_column("detections", "confidence", existing_type=sa.Float(), type_=sa.Double(), existing_nullable=True)


def downgrade():
    raise RuntimeError("Downgrading DOUBLE to FLOAT loses stored precision; restore a matching backup instead.")
