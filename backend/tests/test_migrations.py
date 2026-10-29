"""Upgrade real legacy DDL without losing accounts, samples, or plot metadata."""
import sqlite3
import importlib.util
import io
from datetime import datetime
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.dialects import mysql, sqlite

from app.db import Base, Detection, Plot, make_database
from app.migrations import SCHEMA_REVISION, migrate_database
from app import admin_models, assistant, detection_assistant, extensions
from migration_helpers import upgrade_to_revision


def test_upgrade_legacy_database_preserves_rows_and_creates_restorable_backup(tmp_path):
    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE users (
                id VARCHAR(32) PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE,
                password_hash VARCHAR(256) NOT NULL, name VARCHAR(80) NOT NULL, role VARCHAR(30) NOT NULL
            );
            CREATE TABLE plots (
                id VARCHAR(32) PRIMARY KEY, name VARCHAR(100) NOT NULL,
                crop VARCHAR(40) NOT NULL, area FLOAT NOT NULL,
                location VARCHAR(200) NOT NULL, manager VARCHAR(80) NOT NULL
            );
            INSERT INTO users VALUES ('legacy-user', 'existing', 'original-hash', '已有成员', 'member');
            INSERT INTO plots VALUES ('legacy-plot', '已有地块', '番茄', 3.5, '原位置', '原负责人');
        """)
        previous_plot_ddl = connection.execute("SELECT sql FROM sqlite_master WHERE name='plots'").fetchone()[0]
    engine, _ = make_database(f"sqlite:///{database}")
    try:
        migrate_database(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == SCHEMA_REVISION
            row = connection.execute(text("SELECT * FROM users WHERE id='legacy-user'")).mappings().one()
            assert row["password_hash"] == "original-hash" and row["name"] == "已有成员"
            assert row["is_active"] == 1 and row["token_version"] == 0
            assert row["created_at"] is None  # Registration time was never collected.
            assert connection.scalar(text("SELECT name FROM plots WHERE id='legacy-plot'")) == "已有地块"
            assert connection.scalar(text("SELECT owner_id FROM plots WHERE id='legacy-plot'")) is None
            assert 'owner_id' in {column['name'] for column in inspect(connection).get_columns('plots')}
        backup = next((tmp_path / "backups").glob("*.sqlite3"))
        with sqlite3.connect(backup) as connection:
            assert connection.execute("SELECT name FROM users").fetchone()[0] == "已有成员"
            assert "is_active" not in {row[1] for row in connection.execute("PRAGMA table_info(users)")}
            assert connection.execute("SELECT sql FROM sqlite_master WHERE name='plots'").fetchone()[0] == previous_plot_ddl
        migrate_database(engine)
        assert len(list((tmp_path / "backups").glob("*.sqlite3"))) == 1
    finally:
        engine.dispose()


def test_fresh_database_matches_current_models_and_preserves_foreign_keys(tmp_path):
    engine, _ = make_database(f"sqlite:///{tmp_path / 'new.db'}")
    try:
        migrate_database(engine)
        with engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
            # SQLite enforces an ALTER-added inline REFERENCES clause correctly,
            # while SQLAlchemy reflection omits its ON DELETE option. Verify the
            # real database constraint before excluding only this known diff.
            for table in ('plots','detections'):
                keys=connection.exec_driver_sql(f'PRAGMA foreign_key_list({table})').mappings().all()
                assert any(key['from']=='owner_id' and key['table']=='users' and key['to']=='id'
                           and key['on_delete']=='SET NULL' for key in keys)
            def inline_owner_difference(change):
                if change[0] not in {'add_fk','remove_fk'}:return False
                foreign_key=change[1]
                return (foreign_key.table.name in {'plots','detections'}
                        and list(foreign_key.columns.keys())==['owner_id']
                        and [element.target_fullname for element in foreign_key.elements]==['users.id']
                        and foreign_key.ondelete in {None,'SET NULL'}
                        and foreign_key.onupdate is None and foreign_key.deferrable is None)
            differences=[change for change in differences if not inline_owner_difference(change)]
            assert differences == []
            assert connection.scalar(text("PRAGMA foreign_keys")) == 1
            assert {"knowledge_articles", "audit_logs", "plot_details"} <= set(inspect(connection).get_table_names())
    finally:
        engine.dispose()


def test_mysql_confidence_and_area_use_double_without_changing_sqlite_types():
    for column in (Plot.__table__.c.area, Detection.__table__.c.confidence):
        assert column.type.compile(dialect=mysql.dialect()) == "DOUBLE"
        assert column.type.compile(dialect=sqlite.dialect()) == "FLOAT"


def test_precision_revision_emits_only_in_place_mysql_column_widening():
    filename = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20261028_04_float_precision.py"
    spec = importlib.util.spec_from_file_location("precision_revision", filename)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    output = io.StringIO()
    context = MigrationContext.configure(dialect=mysql.dialect(), opts={"as_sql": True, "output_buffer": output})
    with Operations.context(context):
        revision.upgrade()
    statements = output.getvalue()
    assert "ALTER TABLE plots MODIFY area DOUBLE NOT NULL" in statements
    assert "ALTER TABLE detections MODIFY confidence DOUBLE NULL" in statements
    assert "DROP " not in statements and "UPDATE " not in statements and "DELETE " not in statements


def test_sqlite_03_to_04_keeps_ddl_and_exact_existing_float_values(tmp_path):
    engine, _ = make_database(f"sqlite:///{tmp_path / 'precision.db'}")
    confidence, area = 0.8902057409286499, 123.12345678901234
    try:
        migrate_database(engine)
        with engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='20261028_03'"))
            connection.execute(Plot.__table__.insert(), {"id": "p", "name": "精度测试", "crop": "番茄",
                "area": area, "location": "原位置", "manager": "原负责人"})
            connection.execute(Detection.__table__.insert(), {"id": "d", "name": "原始模型概率", "crop": "番茄",
                "plot_id": "p", "status": "attention", "confidence": confidence,
                "created_at": datetime(2026, 10, 28, 4, 5, 6, 123456), "is_demo": False, "note": "保留"})
            ddl = dict(connection.execute(text("SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN ('plots','detections')")).all())
        migrate_database(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == SCHEMA_REVISION
            assert connection.scalar(text("SELECT area FROM plots WHERE id='p'")) == area
            assert connection.scalar(text("SELECT confidence FROM detections WHERE id='d'")) == confidence
            assert dict(connection.execute(text("SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN ('plots','detections')")).all()) == ddl
    finally:
        engine.dispose()


def test_05_to_06_adds_nullable_ownership_without_attributing_legacy_rows(tmp_path):
    engine,_=make_database(f"sqlite:///{tmp_path/'ownership.db'}")
    try:
        upgrade_to_revision(engine,'20261028_05')
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO users (id,username,password_hash,name,role,is_active,token_version) VALUES ('u','legacy','preserved-hash','已有用户','member',1,0)"))
            connection.execute(text("INSERT INTO plots (id,name,crop,area,location,manager) VALUES ('p','历史地块','番茄',2,'原位置','原负责人')"))
            connection.execute(text("INSERT INTO detections (id,name,crop,plot_id,status,result,confidence,created_at,is_demo,note) VALUES ('d','历史照片','番茄','p','attention','原结果',0.88,'2026-10-28 03:04:05',0,'保留')"))
        migrate_database(engine)
        with engine.connect() as connection:
            for table in ('plots','detections'):
                inspector=inspect(connection)
                column=next(column for column in inspector.get_columns(table) if column['name']=='owner_id')
                assert column['nullable'] is True
                assert any(item['constrained_columns']==['owner_id'] and item['referred_table']=='users'
                           for item in inspector.get_foreign_keys(table))
                assert any(item['from']=='owner_id' and item['on_delete']=='SET NULL'
                           for item in connection.exec_driver_sql(f'PRAGMA foreign_key_list({table})').mappings())
                assert any(item['column_names']==['owner_id'] for item in inspector.get_indexes(table))
                assert connection.scalar(text(f'SELECT owner_id FROM {table}')) is None
            assert connection.execute(text("SELECT name,result,note FROM detections WHERE id='d'")).one()==('历史照片','原结果','保留')
            assert connection.scalar(text('SELECT version_num FROM alembic_version'))==SCHEMA_REVISION
        # A later account deletion preserves attributable records as unassigned.
        with engine.begin() as connection:
            connection.execute(text("UPDATE plots SET owner_id='u'"))
            connection.execute(text("UPDATE detections SET owner_id='u'"))
            connection.execute(text("DELETE FROM users WHERE id='u'"))
        migrate_database(engine)
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT owner_id FROM plots')) is None
            assert connection.scalar(text('SELECT owner_id FROM detections')) is None
            assert connection.scalar(text('SELECT count(*) FROM detections'))==1
    finally:
        engine.dispose()
