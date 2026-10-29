"""Import an offline, current-schema SQLite snapshot into an empty deployment.

No application startup or seeding runs here. Uploaded weights are copied as inert
bytes; source files and source SQLite are always opened read-only.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import sys
import tempfile

from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import make_url

from . import admin_models, assistant, detection_assistant, extensions, runtime_config  # Register every business table.
from .config import Settings
from .db import Base, Detection, PlotDetails, make_database
from .extensions import ModelArtifact
from .migrations import SCHEMA_REVISION, migrate_database


class LegacyImportError(RuntimeError):
    """A safe, operator-facing error without database rows or credentials."""


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def reject_links(path):
    for node in (path, *path.parents):
        if node.is_symlink() or (hasattr(node, "is_junction") and node.is_junction()):
            raise LegacyImportError("导入路径包含符号链接或目录联接，已拒绝。")


def secure_path(root, relative):
    parts = PurePosixPath(relative).parts
    if (not parts or PurePosixPath(relative).is_absolute() or "\\" in relative
            or any(part in {".", ".."} or ":" in part or "\x00" in part for part in relative.split("/"))):
        raise LegacyImportError("上传文件引用包含不安全路径，已拒绝。")
    candidate = root.joinpath(*parts)
    reject_links(candidate)
    if not candidate.resolve().is_relative_to(root):
        raise LegacyImportError("上传文件路径越界，已拒绝。")
    return candidate


def assert_empty(connection):
    for name in inspect(connection).get_table_names():
        if name == "alembic_version" or name.startswith("sqlite_"):
            continue
        quoted = connection.dialect.identifier_preparer.quote(name)
        if connection.execute(text(f"SELECT 1 FROM {quoted} LIMIT 1")).first() is not None:
            raise LegacyImportError(f"目标业务表 {name} 非空，禁止覆盖；请使用独立的空数据库。")


def validate_source(connection):
    inspector = inspect(connection)
    names = set(inspector.get_table_names())
    expected = set(Base.metadata.tables)
    if "alembic_version" not in names:
        raise LegacyImportError("源数据库缺少迁移版本，不支持；请先在原系统完成升级后重新备份。")
    revisions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
    previous_revisions = {"20261028_02", "20261028_03", "20261028_04", "20261028_05"}
    if len(revisions) != 1 or revisions[0] not in previous_revisions | {SCHEMA_REVISION}:
        raise LegacyImportError("仅支持版本 20261028_02 至 20261029_06 的源数据库；不会修改或升级原库。")
    if names - expected - {"alembic_version", "sqlite_sequence"}:
        raise LegacyImportError("源数据库含当前程序不认识的业务表，不支持自动导入。")
    for table in Base.metadata.sorted_tables:
        if table.name not in names:
            if table.name == 'workspace_configuration' and revisions[0] in previous_revisions - {'20261028_05'}:
                continue
            raise LegacyImportError(f"源数据库缺少表 {table.name}，不支持自动导入。")
        actual = {column["name"] for column in inspector.get_columns(table.name)}
        expected_columns = set(table.columns.keys())
        old_ownership_columns = (table.name in {'plots', 'detections'} and revisions[0] in previous_revisions
                                 and actual == expected_columns - {'owner_id'})
        if actual != expected_columns and not old_ownership_columns:
            raise LegacyImportError(f"源表 {table.name} 的列与当前版本不一致，不支持自动导入。")
    if connection.exec_driver_sql("PRAGMA quick_check").scalar() != "ok":
        raise LegacyImportError("源数据库完整性检查失败。")
    if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise LegacyImportError("源数据库存在失效外键，请先修复后重新备份。")


def referenced_files(connection, source_root, target_root):
    references = {}
    for url in connection.execute(select(Detection.image_url).where(Detection.image_url.is_not(None))).scalars():
        if not url:
            continue
        prefix = next((value for value in ("/api/uploads/", "/uploads/") if url.startswith(value)), None)
        if prefix is None:
            raise LegacyImportError("检测图片引用不是当前系统的本地上传路径。")
        name = url[len(prefix):]
        if "/" in name or "?" in name or "#" in name:
            raise LegacyImportError("检测图片引用包含不安全路径。")
        references[name] = None
    for name in connection.execute(select(PlotDetails.cover_filename).where(PlotDetails.cover_filename.is_not(None))).scalars():
        if name:
            if "/" in name:
                raise LegacyImportError("地块封面引用包含不安全路径。")
            references[name] = None
    for name, checksum, size in connection.execute(select(ModelArtifact.stored_name, ModelArtifact.sha256, ModelArtifact.size)):
        if not name or "/" in name:
            raise LegacyImportError("模型文件引用包含不安全路径。")
        references["models/" + name] = (checksum, size)
    plan = []
    for relative, expected in sorted(references.items()):
        origin = secure_path(source_root, relative)
        destination = secure_path(target_root, relative)
        if not origin.is_file() or not stat.S_ISREG(origin.stat().st_mode):
            raise LegacyImportError(f"数据库引用的上传文件不存在或不是普通文件：{relative}")
        checksum, size = file_sha256(origin), origin.stat().st_size
        if expected and (checksum != expected[0] or size != expected[1]):
            raise LegacyImportError(f"源模型文件与数据库摘要或大小不一致：{relative}")
        exists = destination.exists()
        if exists and (not destination.is_file() or file_sha256(destination) != checksum):
            raise LegacyImportError(f"目标已有同名但内容不同的文件，禁止覆盖：{relative}")
        plan.append({"path": relative, "sha256": checksum, "size": size, "existing": exists})
    return plan


def stage_files(plan, source_root, stage_root):
    for item in plan:
        if item["existing"]:
            continue
        origin = secure_path(source_root, item["path"])
        staged = secure_path(stage_root, item["path"])
        staged.parent.mkdir(parents=True, exist_ok=True)
        with origin.open("rb") as source, staged.open("xb") as target:
            shutil.copyfileobj(source, target)
        if staged.stat().st_size != item["size"] or file_sha256(staged) != item["sha256"]:
            raise LegacyImportError("上传文件在复制过程中发生变化，已中止。")


def publish_files(plan, stage_root, target_root, created_files, created_dirs):
    for item in plan:
        destination = secure_path(target_root, item["path"])
        if item["existing"]:
            if not destination.is_file() or file_sha256(destination) != item["sha256"]:
                raise LegacyImportError("目标文件在导入期间发生变化，已中止。")
            continue
        if not destination.parent.exists():
            destination.parent.mkdir()
            created_dirs.append(destination.parent)
        try:
            # Staging lives on this same volume: link atomically without overwriting.
            os.link(secure_path(stage_root, item["path"]), destination)
            created_files.append(destination)
        except FileExistsError:
            if not destination.is_file() or file_sha256(destination) != item["sha256"]:
                raise LegacyImportError("目标出现同名不同内容文件，禁止覆盖。")


def import_legacy(source, uploads, settings=None):
    settings = settings or Settings()
    source, source_root = Path(source).absolute(), Path(uploads).absolute()
    target_root = Path(settings.upload_dir).absolute()
    for path in (source, source_root, target_root):
        reject_links(path)
    if not source.is_file() or not source_root.is_dir():
        raise LegacyImportError("源数据库或上传目录不存在。")
    source, source_root, target_root = source.resolve(), source_root.resolve(), target_root.resolve()
    if source_root.is_relative_to(target_root) or target_root.is_relative_to(source_root):
        raise LegacyImportError("源上传目录和目标上传目录必须相互独立。")
    url = make_url(settings.database_url)
    if url.get_backend_name() == "sqlite" and url.database and Path(url.database).resolve() == source:
        raise LegacyImportError("目标数据库不能与源数据库相同。")
    if url.get_backend_name() not in {"mysql", "sqlite"}:
        raise LegacyImportError("目标仅支持当前系统的 MySQL 或 SQLite 数据库。")
    source_engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(source.as_uri() + "?mode=ro", uri=True))
    target_engine, _ = make_database(settings.database_url)
    created_files, created_dirs = [], []
    committed = False
    try:
        with source_engine.connect() as original:
            original.exec_driver_sql("PRAGMA query_only=ON")
            original.exec_driver_sql("BEGIN")
            validate_source(original)
            source_tables = set(inspect(original).get_table_names())
            source_columns = {name: {column['name'] for column in inspect(original).get_columns(name)}
                              for name in source_tables}
            with target_engine.connect() as target:
                assert_empty(target)
            target_root.mkdir(parents=True, exist_ok=True)
            plan = referenced_files(original, source_root, target_root)
            source_checksum = file_sha256(source)
            with tempfile.TemporaryDirectory(prefix=".agriscan-import-", dir=target_root, ignore_cleanup_errors=True) as temporary:
                staging = Path(temporary).resolve()
                stage_files(plan, source_root, staging)
                migrate_database(target_engine)
                counts = {}
                with target_engine.begin() as target:
                    if target.dialect.name == "sqlite":
                        target.exec_driver_sql("BEGIN IMMEDIATE")
                    assert_empty(target)
                    for table in Base.metadata.sorted_tables:
                        if table.name not in source_tables:
                            counts[table.name] = 0
                            continue
                        # Old snapshots have no ownership column. Import only
                        # columns physically present; nullable owner_id stays
                        # unknown rather than being guessed from an admin name.
                        projection = [column for column in table.columns if column.name in source_columns[table.name]]
                        rows = original.execute(select(*projection)).mappings()
                        count = 0
                        while batch := rows.fetchmany(500):
                            target.execute(table.insert(), [dict(row) for row in batch])
                            count += len(batch)
                        if target.scalar(select(func.count()).select_from(table)) != count:
                            raise LegacyImportError(f"导入后表 {table.name} 行数不一致，已回滚。")
                        counts[table.name] = count
                    publish_files(plan, staging, target_root, created_files, created_dirs)
                committed = True
            return {"tables": counts, "file_count": len(plan), "source_sha256": source_checksum,
                    "files": [{key: item[key] for key in ("path", "sha256", "size")} for item in plan]}
    except BaseException:
        if not committed:
            for path in reversed(created_files):
                path.unlink(missing_ok=True)
            for path in reversed(created_dirs):
                try:
                    path.rmdir()
                except OSError:
                    pass
        raise
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main(argv=None):
    parser = argparse.ArgumentParser(description="将只读SQLite备份导入空数据库，并校验复制引用文件。")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--uploads", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = import_legacy(args.source, args.uploads)
    except LegacyImportError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, SQLAlchemyError, ValueError, sqlite3.Error):
        print("导入失败；未覆盖已有数据，请检查备份、文件权限和数据库连接。", file=sys.stderr)
        return 1
    print(json.dumps({"tables": report["tables"], "file_count": report["file_count"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
