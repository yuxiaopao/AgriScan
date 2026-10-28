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
            assert connection.scalar(text("SELECT sql FROM sqlite_master WHERE name='plots'")) == previous_plot_ddl
        backup = next((tmp_path / "backups").glob("*.sqlite3"))
        with sqlite3.connect(backup) as connection:
            assert connection.execute("SELECT name FROM users").fetchone()[0] == "已有成员"
            assert "is_active" not in {row[1] for row in connection.execute("PRAGMA table_info(users)")}
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
