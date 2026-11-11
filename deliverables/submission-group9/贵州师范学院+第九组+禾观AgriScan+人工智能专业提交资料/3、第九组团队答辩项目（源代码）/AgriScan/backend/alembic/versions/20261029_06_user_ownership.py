"""Add explicit personal data ownership without guessing legacy attribution."""
from alembic import op
import sqlalchemy as sa

revision = '20261029_06'
down_revision = '20261028_05'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    for table in ('plots', 'detections'):
        inspector = sa.inspect(connection)
        columns = {column['name'] for column in inspector.get_columns(table)}
        if 'owner_id' not in columns:
            if connection.dialect.name == 'sqlite':
                # SQLite permits a nullable inline REFERENCES column without
                # rebuilding parent tables that already have dependent rows.
                op.execute(sa.text(f'ALTER TABLE {table} ADD COLUMN owner_id VARCHAR(32) REFERENCES users(id) ON DELETE SET NULL'))
            else:
                op.add_column(table, sa.Column('owner_id', sa.String(32), nullable=True))
        inspector = sa.inspect(connection)
        indexes = {item['name'] for item in inspector.get_indexes(table)}
        index = f'ix_{table}_owner_id'
        if index not in indexes:
            # Create the named index before MySQL adds its FK so InnoDB does
            # not need to create an additional implicit supporting index.
            op.create_index(index, table, ['owner_id'])
        foreign_keys = inspector.get_foreign_keys(table)
        owner_keys = [item for item in foreign_keys if item['constrained_columns'] == ['owner_id']]
        if not owner_keys:
            if connection.dialect.name == 'sqlite':
                raise RuntimeError('已有 owner_id 列缺少用户外键，请恢复匹配的备份后迁移；不会重建业务表。')
            op.create_foreign_key(f'fk_{table}_owner_id_users', table, 'users', ['owner_id'], ['id'], ondelete='SET NULL')
            owner_keys = [item for item in sa.inspect(connection).get_foreign_keys(table)
                          if item['constrained_columns'] == ['owner_id']]
        if (len(owner_keys) != 1 or owner_keys[0]['referred_table'] != 'users'
                or owner_keys[0]['referred_columns'] != ['id']):
            raise RuntimeError('已有 owner_id 外键与预期不一致；请核对数据库备份，不会改写已有外键。')
        if connection.dialect.name == 'sqlite':
            # SQLite's inspector omits ON DELETE for inline foreign keys.
            constraints = connection.exec_driver_sql(f'PRAGMA foreign_key_list({table})').mappings()
            valid_delete = any(item['from'] == 'owner_id' and item['on_delete'] == 'SET NULL'
                               for item in constraints)
        else:
            valid_delete = owner_keys[0].get('options', {}).get('ondelete', '').upper() == 'SET NULL'
        if not valid_delete:
            raise RuntimeError('已有 owner_id 外键删除策略不是 SET NULL；请核对备份，不会删除或重建业务表。')


def downgrade():
    raise RuntimeError('Ownership must be retained; restore a verified matching database backup instead of dropping attribution.')
