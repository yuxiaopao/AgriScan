"""Persist workspace configuration and independently encrypted integration keys."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME

revision = '20261028_05'
down_revision = '20261028_04'
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table('workspace_configuration'):
        return
    op.create_table('workspace_configuration',
                    sa.Column('id', sa.String(32), primary_key=True),
                    sa.Column('version', sa.Integer, nullable=False),
                    sa.Column('data', sa.JSON, nullable=False),
                    sa.Column('encrypted_secrets', sa.Text, nullable=True),
                    sa.Column('updated_by', sa.String(32), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
                    sa.Column('updated_at', sa.DateTime().with_variant(DATETIME(fsp=6), 'mysql'), nullable=False))


def downgrade():
    raise RuntimeError('Runtime configuration and encrypted credentials must be retained; restore a matching backup.')
