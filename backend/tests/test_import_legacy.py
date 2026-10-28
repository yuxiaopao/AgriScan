"""Offline migration fixtures never open the user's live database or upload files."""
import hashlib
import json
import sqlite3

import pytest
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import OperationalError

from app.admin_models import AuditLog, KnowledgeArticle
from app.assistant import ChatMessage, Conversation
from app.config import Settings
from app.db import AppMeta, Base, Detection, DetectionPrediction, Plot, PlotDetails, RevokedToken, User, make_database
from app.detection_assistant import DetectionDiscussion
from app.extensions import EmailChallenge, ModelArtifact, UserEmail
from app.import_legacy import LegacyImportError, file_sha256, import_legacy
from app.migrations import SCHEMA_REVISION, migrate_database


@pytest.fixture
def legacy(tmp_path):
    source = tmp_path / "legacy.db"
    uploads = tmp_path / "legacy-uploads"
    uploads.mkdir()
    (uploads / "models").mkdir()
    files = {"leaf.jpg": b"original image bytes", "cover.jpg": b"original cover bytes",
             "models/saved.pt": b"inert uploaded weight; never deserialize"}
    for relative, value in files.items():
        (uploads / relative).write_bytes(value)
    engine, _ = make_database(f"sqlite:///{source}")
    migrate_database(engine)
    from datetime import datetime
    instant = datetime(2026, 10, 28, 3, 4, 5, 123456)
    with engine.begin() as connection:
        connection.execute(insert(User), [{"id": "u1", "username": "existing_owner", "name": "原管理员",
            "role": "admin", "password_hash": "a-secret-original-hash", "is_active": True,
            "token_version": 7, "created_at": None, "updated_at": instant}])
        connection.execute(insert(AppMeta), [
            {"key": "managed_admin_id", "value": "u1"}, {"key": "knowledge_seed_v1", "value": "initialized"},
            {"key": "demo_seed_v1", "value": "initialized"},
        ])
        connection.execute(insert(Plot), [{"id": "p1", "name": "原地块", "crop": "番茄", "area": 2.5,
            "location": "原位置", "manager": "原农技员"}])
        connection.execute(insert(PlotDetails), [{"plot_id": "p1", "cover_filename": "cover.jpg",
            "latitude": 30.123456789, "longitude": 120.123456789}])
        connection.execute(insert(Detection), [
            {"id": "d1", "name": "原检测", "crop": "番茄", "plot_id": "p1", "status": "attention",
             "result": "番茄早疫病", "confidence": 0.875, "created_at": instant,
             "image_url": "/api/uploads/leaf.jpg", "is_demo": False, "note": "原备注"},
            {"id": "demo", "name": "无图演示", "crop": "番茄", "plot_id": None, "status": "healthy",
             "result": "健康", "confidence": 0.9, "created_at": instant,
             "image_url": None, "is_demo": True, "note": "明确的演示记录"},
        ])
        connection.execute(insert(DetectionPrediction), [{"detection_id": "d1",
            "candidates": [{"label": "番茄早疫病", "confidence": 0.875}],
            "model": {"name": "original", "task": "classify", "onnx_sha256": "original-model-sha"}}])
        connection.execute(insert(UserEmail), [{"email": "owner@example.com", "user_id": "u1"}])
        connection.execute(insert(EmailChallenge), [{"email": "pending@example.com", "digest": "hidden-code-digest",
            "expires_at": instant, "sent_at": instant, "attempts": 2}])
        connection.execute(insert(RevokedToken), [{"jti": "original-revoked-token", "expires_at": instant}])
        connection.execute(insert(Conversation), [{"id": "c1", "user_id": "u1", "title": "原对话",
            "updated_at": instant, "busy_until": instant}])
        connection.execute(insert(ChatMessage), [{"id": 41, "conversation_id": "c1", "role": "assistant",
            "content": "原有回答", "created_at": instant}])
        connection.execute(insert(DetectionDiscussion), [{"user_id": "u1", "detection_id": "d1", "conversation_id": "c1"}])
        connection.execute(insert(KnowledgeArticle), [{"id": "a1", "title": "原知识", "crop": "番茄",
            "category": "原分类", "summary": "原摘要", "content": "原正文", "status": "published",
            "sources": [{"title": "原来源", "url": "https://example.com/original"}], "created_by": "u1",
            "updated_by": "u1", "created_at": instant, "updated_at": instant, "published_at": instant}])
        connection.execute(insert(AuditLog), [{"id": "audit1", "actor_id": "u1", "actor_name": "原管理员",
            "action": "knowledge.create", "resource_type": "knowledge", "resource_id": "a1",
            "summary": "原审计", "created_at": instant}])
        connection.execute(insert(ModelArtifact), [{"id": "model1", "name": "原权重", "filename": "original.pt",
            "stored_name": "saved.pt", "framework": "PyTorch", "size": len(files["models/saved.pt"]),
            "sha256": hashlib.sha256(files["models/saved.pt"]).hexdigest(), "created_at": instant}])
    engine.dispose()
    return source, uploads, files


def target_settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'target.db'}", upload_dir=tmp_path / "target-uploads",
                    model_manifest="", redis_url="")


def table_rows(database):
    engine, _ = make_database(f"sqlite:///{database}")
    try:
        with engine.connect() as connection:
            return {table.name: [dict(row) for row in connection.execute(select(table).order_by(*table.primary_key.columns)).mappings()]
                    for table in Base.metadata.sorted_tables}
    finally:
        engine.dispose()


def test_import_preserves_every_table_timestamps_json_ids_credentials_and_files(legacy, tmp_path):
    source, uploads, files = legacy
    before, source_hash = table_rows(source), file_sha256(source)
    settings = target_settings(tmp_path)
    report = import_legacy(source, uploads, settings)
    assert report["tables"] == {name: len(rows) for name, rows in before.items()}
    assert table_rows(tmp_path / "target.db") == before
    assert report["source_sha256"] == source_hash == file_sha256(source)
    assert report["file_count"] == 3
    assert {item["path"] for item in report["files"]} == set(files)
    for item in report["files"]:
        copied = settings.upload_dir / item["path"]
        assert copied.read_bytes() == files[item["path"]]
        assert item["sha256"] == file_sha256(copied)
    assert not list(settings.upload_dir.glob(".agriscan-import-*"))
    assert settings.demo_mode is True and settings.admin_password == "admin12345"
    with pytest.raises(LegacyImportError, match="非空"):
        import_legacy(source, uploads, settings)
    assert table_rows(tmp_path / "target.db") == before


@pytest.mark.parametrize("version", ["20261028_02", "20261028_03", "20261028_04", "20261028_05"])
def test_supported_snapshot_imports_without_source_upgrade(legacy, tmp_path, version):
    source, uploads, _ = legacy
    with sqlite3.connect(source) as connection:
        connection.execute("UPDATE alembic_version SET version_num=?", (version,))
        if version != '20261028_05':
            connection.execute('DROP TABLE workspace_configuration')
    checksum = file_sha256(source)
    settings = target_settings(tmp_path)
    import_legacy(source, uploads, settings)
    assert file_sha256(source) == checksum
    with sqlite3.connect(source) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == version
    with sqlite3.connect(tmp_path / "target.db") as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == SCHEMA_REVISION
        assert connection.execute('SELECT count(*) FROM workspace_configuration').fetchone()[0] == 0


def test_05_snapshot_preserves_encrypted_configuration_without_exporting_its_key(legacy, tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from app.runtime_config import Configuration
    source, uploads, _ = legacy
    secret = 'runtime-key-retained-only-as-ciphertext'
    key = Fernet.generate_key()
    encrypted = Fernet(key).encrypt(json.dumps({'llm_api_key': secret}).encode()).decode()
    data = Configuration().model_dump()
    with sqlite3.connect(source) as connection:
        connection.execute('INSERT INTO workspace_configuration VALUES (?, ?, ?, ?, ?, ?)',
                           ('workspace', 3, json.dumps(data), encrypted, 'u1', '2026-10-28 12:00:00.123456'))
    checksum = file_sha256(source)
    monkeypatch.delenv('CONFIG_ENCRYPTION_KEY', raising=False)
    report = import_legacy(source, uploads, target_settings(tmp_path))
    assert report['tables']['workspace_configuration'] == 1
    assert file_sha256(source) == checksum
    with sqlite3.connect(tmp_path / 'target.db') as connection:
        row = connection.execute('SELECT version, encrypted_secrets, data FROM workspace_configuration').fetchone()
    assert row[0] == 3 and row[1] == encrypted
    assert secret not in row[1] + row[2]
    assert json.loads(Fernet(key).decrypt(row[1].encode()))['llm_api_key'] == secret


def test_05_snapshot_missing_configuration_table_is_not_treated_as_an_older_schema(legacy, tmp_path):
    source, uploads, _ = legacy
    with sqlite3.connect(source) as connection:
        connection.execute('DROP TABLE workspace_configuration')
    checksum = file_sha256(source)
    with pytest.raises(LegacyImportError, match='workspace_configuration'):
        import_legacy(source, uploads, target_settings(tmp_path))
    assert file_sha256(source) == checksum


def test_source_connection_rejects_writes_even_without_query_only_guard(legacy, tmp_path, monkeypatch):
    source, uploads, _ = legacy
    checksum = file_sha256(source)
    import app.import_legacy as module
    original = module.validate_source
    def assert_read_only(connection):
        connection.exec_driver_sql("PRAGMA query_only=OFF")
        with pytest.raises(OperationalError, match="readonly"):
            connection.execute(text("UPDATE users SET name='should never be written'"))
        connection.exec_driver_sql("PRAGMA query_only=ON")
        original(connection)
    monkeypatch.setattr(module, "validate_source", assert_read_only)
    import_legacy(source, uploads, target_settings(tmp_path))
    assert file_sha256(source) == checksum


@pytest.mark.parametrize("table", [AppMeta.__table__, KnowledgeArticle.__table__])
def test_any_nonempty_target_business_table_prevents_import(legacy, tmp_path, table):
    source, uploads, _ = legacy
    settings = target_settings(tmp_path)
    engine, _ = make_database(settings.database_url)
    migrate_database(engine)
    with engine.begin() as connection:
        if table.name == "app_meta":
            connection.execute(table.insert(), {"key": "existing", "value": "keep"})
        else:
            connection.execute(table.insert(), {"id": "keep", "title": "已有文章", "crop": "", "category": "通用",
                "summary": "", "content": "保留", "sources": [], "status": "draft"})
    engine.dispose()
    before = table_rows(tmp_path / "target.db")
    with pytest.raises(LegacyImportError, match="非空"):
        import_legacy(source, uploads, settings)
    assert table_rows(tmp_path / "target.db") == before
    assert not settings.upload_dir.exists()


def test_missing_reference_file_and_changed_model_digest_are_rejected(legacy, tmp_path):
    source, uploads, _ = legacy
    settings = target_settings(tmp_path)
    original = (uploads / "leaf.jpg").read_bytes()
    (uploads / "leaf.jpg").unlink()
    with pytest.raises(LegacyImportError, match="不存在"):
        import_legacy(source, uploads, settings)
    (uploads / "leaf.jpg").write_bytes(original)
    (uploads / "models" / "saved.pt").write_bytes(b"wrong weights")
    with pytest.raises(LegacyImportError, match="摘要或大小不一致"):
        import_legacy(source, uploads, settings)
    assert not list(settings.upload_dir.rglob("*"))


def test_unsafe_database_file_reference_cannot_escape_uploads(legacy, tmp_path):
    source, uploads, _ = legacy
    with sqlite3.connect(source) as connection:
        connection.execute("UPDATE detections SET image_url='/api/uploads/../escape.jpg' WHERE id='d1'")
    checksum = file_sha256(source)
    with pytest.raises(LegacyImportError, match="不安全路径"):
        import_legacy(source, uploads, target_settings(tmp_path))
    assert file_sha256(source) == checksum


def test_source_symbolic_link_and_target_filename_collision_are_rejected(legacy, tmp_path):
    source, uploads, _ = legacy
    settings = target_settings(tmp_path)
    settings.upload_dir.mkdir()
    existing = settings.upload_dir / "leaf.jpg"
    existing.write_bytes(b"do not overwrite")
    with pytest.raises(LegacyImportError, match="同名但内容不同"):
        import_legacy(source, uploads, settings)
    assert existing.read_bytes() == b"do not overwrite"
    existing.unlink()
    origin = uploads / "leaf.jpg"
    origin.unlink()
    external = tmp_path / "external.jpg"
    external.write_bytes(b"external content")
    try:
        origin.symlink_to(external)
    except OSError:
        pytest.skip("This Windows account cannot create symbolic links.")
    with pytest.raises(LegacyImportError, match="符号链接"):
        import_legacy(source, uploads, settings)
    assert not list(settings.upload_dir.iterdir())


def test_failed_import_rolls_back_rows_and_only_removes_newly_published_files(legacy, tmp_path, monkeypatch):
    source, uploads, files = legacy
    settings = target_settings(tmp_path)
    settings.upload_dir.mkdir()
    (settings.upload_dir / "cover.jpg").write_bytes(files["cover.jpg"])
    import app.import_legacy as module
    original = module.publish_files
    def fail_after_files(*args):
        original(*args)
        raise LegacyImportError("forced import failure")
    monkeypatch.setattr(module, "publish_files", fail_after_files)
    with pytest.raises(LegacyImportError, match="forced"):
        import_legacy(source, uploads, settings)
    assert all(not rows for rows in table_rows(tmp_path / "target.db").values())
    assert {path.name for path in settings.upload_dir.iterdir()} == {"cover.jpg"}
    assert (settings.upload_dir / "cover.jpg").read_bytes() == files["cover.jpg"]


def test_source_missing_columns_is_rejected_without_mutation(legacy, tmp_path):
    source, uploads, _ = legacy
    with sqlite3.connect(source) as connection:
        connection.execute("ALTER TABLE users DROP COLUMN token_version")
    checksum = file_sha256(source)
    with pytest.raises(LegacyImportError, match="列与当前版本不一致"):
        import_legacy(source, uploads, target_settings(tmp_path))
    assert file_sha256(source) == checksum


def test_cli_outputs_counts_without_sensitive_rows(legacy, tmp_path, monkeypatch, capsys):
    source, uploads, _ = legacy
    import app.import_legacy as module
    monkeypatch.setattr(module, "Settings", lambda: target_settings(tmp_path))
    assert module.main(["--source", str(source), "--uploads", str(uploads)]) == 0
    output = capsys.readouterr()
    result = json.loads(output.out)
    assert set(result) == {"tables", "file_count"} and result["tables"]["users"] == 1
    assert "a-secret-original-hash" not in output.out + output.err
    assert "hidden-code-digest" not in output.out + output.err
