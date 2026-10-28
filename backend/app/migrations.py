"""Versioned upgrades with a consistent backup before adopting a local database."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import RLock

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text

SCHEMA_REVISION = "20261028_05"
_migration_lock = RLock()


def migrate_database(engine):
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    with _migration_lock, engine.connect() as connection:
        mysql_lock = False
        try:
            if connection.dialect.name == "mysql":
                mysql_lock = connection.scalar(text("SELECT GET_LOCK('agriscan_schema_migration', 30)")) == 1
                if not mysql_lock:
                    raise RuntimeError("数据库正在升级，请稍后重试。")
            current = MigrationContext.configure(connection).get_current_revision()
            if current == SCHEMA_REVISION:
                return
            if connection.dialect.name == "sqlite":
                path = engine.url.database
                if path and path != ":memory:" and inspect(connection).has_table("users"):
                    source = Path(path).resolve()
                    folder = source.parent / "backups"
                    folder.mkdir(parents=True, exist_ok=True)
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                    backup = folder / f"{source.stem}-before-admin-{stamp}.sqlite3"
                    with sqlite3.connect(str(source)) as original, sqlite3.connect(str(backup)) as target:
                        original.backup(target)
                connection.rollback()
                connection.exec_driver_sql("BEGIN IMMEDIATE")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            if mysql_lock:
                connection.execute(text("SELECT RELEASE_LOCK('agriscan_schema_migration')"))
                connection.commit()


if __name__ == "__main__":
    from .config import Settings
    from .db import make_database
    engine, _ = make_database(Settings().database_url)
    try:
        migrate_database(engine)
        print(f"Database schema ready: {SCHEMA_REVISION}")
    finally:
        engine.dispose()
