"""Disposable local MySQL integration check; never reads the project's .env database."""
from pathlib import Path
import sys
import time

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))

from sqlalchemy import create_engine, text
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.security import hash_password

url = "mysql+pymysql://admin_check:REDACTED_PASSWORD@127.0.0.1:13309/agriscan_admin_check?charset=utf8mb4"
engine = create_engine(url, connect_args={"connect_timeout": 2})
for attempt in range(25):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        break
    except Exception:
        time.sleep(1)
else:
    raise RuntimeError("Disposable MySQL did not become ready")

with engine.begin() as connection:
    connection.execute(text("""CREATE TABLE users (
        id VARCHAR(32) PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE,
        password_hash VARCHAR(256) NOT NULL, name VARCHAR(80) NOT NULL,
        role VARCHAR(30) NOT NULL) ENGINE=InnoDB"""))
    connection.execute(text("INSERT INTO users VALUES (:id,:username,:password,:name,'member')"), {
        "id": "legacy-mysql-member", "username": "legacy_member",
        "password": hash_password("legacy-password-2026"), "name": "历史成员",
    })

settings = Settings(database_url=url, upload_dir=root / ".runtime/admin-preview/mysql-uploads",
                    redis_url="", model_manifest="", demo_mode=True,
                    llm_enabled=False, registration_enabled=True, email_verification_enabled=False,
                    admin_username="admin", admin_password="REDACTED_SECRET")
with TestClient(create_app(settings)) as client:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "REDACTED_SECRET"})
    assert response.status_code == 200, response.text
    headers = {"Authorization": "Bearer " + response.json()["access_token"]}
    users = client.get("/api/admin/users", headers=headers)
    assert users.status_code == 200, users.text
    legacy = next(row for row in users.json()["items"] if row["username"] == "legacy_member")
    assert legacy["is_active"] and legacy["created_at"] is None
    assert client.post("/api/auth/login", json={"username": "legacy_member", "password": "REDACTED_SECRET"}).status_code == 200
    overview = client.get("/api/admin/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    assert len(overview.json()["trend"]) == 7
    content = "叶片观察记录。" * 4000
    article = client.post("/api/admin/knowledge", headers=headers, json={
        "title": "MySQL中文长正文验证", "crop": "番茄", "category": "巡检", "summary": "临时集成测试",
        "content": content, "sources": [], "status": "published",
    })
    assert article.status_code == 201, article.text
    assert article.json()["content"] == content
    assert any(row["id"] == article.json()["id"] for row in client.get("/api/knowledge").json())
    result = client.get("/api/admin/detections/export.csv", headers=headers)
    assert result.status_code == 200 and result.content.startswith(b"\xef\xbb\xbf"), result.text
    assert client.get("/api/admin/audit", headers=headers).json()["total"] >= 1
    print("MySQL passed: legacy upgrade, preserved login, UTC+8 trend, long Chinese content, published knowledge, CSV and audit.")
engine.dispose()
