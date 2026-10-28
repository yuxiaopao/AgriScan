import io
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.main import create_app
from app.seed import initialize_data


@pytest.fixture()
def client(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        upload_dir=tmp_path / "uploads", redis_url="", demo_mode=True,
        admin_username="admin", admin_password="admin12345",
        registration_enabled=True, email_verification_enabled=False, llm_enabled=False, model_manifest="",
    )
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


def auth(client):
    result = client.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
    assert result.status_code == 200
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def picture():
    data = io.BytesIO()
    Image.new("RGB", (32, 32), (52, 121, 69)).save(data, format="PNG")
    return data.getvalue()


def test_demo_is_explicit_and_model_is_not_faked(client):
    health = client.get("/api/health").json()
    assert health["database"] == "connected"
    assert health["redis"] == "disabled"
    assert health["mode"] == "demo"
    model = client.get("/api/models").json()
    assert model["active"] is None and model["status"] == "awaiting_weights"
    rows = client.get("/api/detections").json()
    assert len(rows) == 12
    assert all(row["is_demo"] for row in rows)
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["stats"] == {"total": 12, "healthy": 8, "attention": 4, "pending": 0}
    assert len(dashboard["trend"]) == 7
    assert len(client.get("/api/dashboard?days=30").json()["trend"]) == 30
    assert client.get("/api/dashboard?days=4").status_code == 422


def test_dashboard_handles_more_crops_than_palette_entries(client, monkeypatch):
    monkeypatch.setattr("app.main.SUPPORTED_CROPS", ["番茄", "水稻", "玉米", "小麦", "黄瓜", "苹果", "葡萄"])
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    assert all(item["color"].startswith("#") for item in response.json()["distribution"])


def test_mutations_require_login_and_logout_revokes_token(client):
    assert client.post("/api/plots", json={"name": "test", "crop": "番茄", "area": 1}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin", "password": "bad"}).status_code == 401
    headers = auth(client)
    assert client.get("/api/auth/me", headers=headers).json()["role"] == "admin"
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.post("/api/plots", headers=headers, json={"name": "test", "crop": "番茄", "area": 1}).status_code == 401


def test_upload_persists_real_image_without_diagnosis_then_deletes(client):
    headers = auth(client)
    response = client.post(
        "/api/detections", headers=headers,
        data={"crop": "番茄", "plot_id": "plot-tomato", "note": "现场采样"},
        files={"file": ("../../sample.png", picture(), "image/png")},
    )
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["is_demo"] is False
    assert row["name"] == "sample.png"
    assert row["plot_name"] == "01 号番茄温室"
    assert row["status"] == "awaiting_model"
    assert row["confidence"] is None and row["result"] is None
    stored = client.get(row["image_url"])
    assert stored.status_code == 200 and stored.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(stored.content)).size == (32, 32)
    assert client.get("/api/dashboard").json()["stats"]["pending"] == 1
    assert client.get(f"/api/detections/{row['id']}").json()["note"] == "现场采样"
    assert client.get("/api/detections?status=awaiting_model").json()[0]["id"] == row["id"]
    assert client.delete(f"/api/detections/{row['id']}", headers=headers).status_code == 200
    assert client.get(row["image_url"]).status_code == 404
    assert client.get("/api/dashboard").json()["stats"]["pending"] == 0


def test_uploaded_jpeg_applies_exif_orientation_before_stripping_metadata(client):
    image = Image.new('RGB', (80, 40), (220, 20, 20))
    image.paste((20, 180, 30), (40, 0, 80, 40))
    exif = Image.Exif()
    exif[274] = 6  # Camera orientation: display the sensor pixels rotated 90 degrees clockwise.
    data = io.BytesIO()
    image.save(data, format='JPEG', quality=95, exif=exif)
    response = client.post('/api/detections', headers=auth(client), data={'crop': '番茄'},
                           files={'file': ('rotated.jpg', data.getvalue(), 'image/jpeg')})
    assert response.status_code == 201, response.text
    stored = client.get(response.json()['image_url'])
    with Image.open(io.BytesIO(stored.content)) as saved:
        assert saved.size == (40, 80) and not saved.getexif()
        upper, lower = saved.getpixel((20, 10)), saved.getpixel((20, 70))
        assert upper[0] > 180 and upper[1] < 60
        assert lower[1] > 140 and lower[0] < 60


@pytest.mark.parametrize(
    "crop,plot_id,data,status",
    [
        ("番茄", "", b"this is not an image", 422),
        ("香蕉", "", b"irrelevant", 422),
        ("番茄", "nonexistent", b"irrelevant", 404),
        ("番茄", "plot-rice", b"irrelevant", 422),
        ("番茄", "", b"x" * (10 * 1024 * 1024 + 1), 413),
    ],
    ids=["invalid-image", "unsupported-crop", "missing-plot", "crop-mismatch", "oversized"],
)
def test_invalid_uploads_are_rejected(client, crop, plot_id, data, status):
    response = client.post(
        "/api/detections", headers=auth(client), data={"crop": crop, "plot_id": plot_id},
        files={"file": ("bad.jpg", data, "image/jpeg")},
    )
    assert response.status_code == status
    assert client.get("/api/dashboard").json()["stats"]["total"] == 12
    assert list(client.app.state.settings.upload_dir.iterdir()) == []


def test_plot_crud_and_history_integrity(client):
    headers = auth(client)
    created = client.post(
        "/api/plots", headers=headers,
        json={"name": "新试验田", "crop": "小麦", "area": 5.5, "location": "东区", "manager": "赵明"},
    )
    assert created.status_code == 201
    plot = created.json()
    assert plot["health_score"] is None and plot["detections"] == 0
    changed = client.patch(f"/api/plots/{plot['id']}", headers=headers, json={"name": "小麦示范田", "area": 7})
    assert changed.status_code == 200 and changed.json()["area"] == 7
    assert client.patch(f"/api/plots/{plot['id']}", headers=headers, json={"name": None}).status_code == 422
    assert client.patch(f"/api/plots/{plot['id']}", headers=headers, json={"area": -1}).status_code == 422
    assert client.delete(f"/api/plots/{plot['id']}", headers=headers).status_code == 200
    assert client.patch("/api/plots/plot-tomato", headers=headers, json={"crop": "小麦"}).status_code == 409
    assert client.delete("/api/plots/plot-tomato", headers=headers).status_code == 200
    record = client.get("/api/detections/demo-001").json()
    assert record["plot_id"] is None and record["result"] == "番茄早疫病"
    assert client.get("/api/dashboard").json()["stats"]["total"] == 12


def test_search_and_status_filter_are_actual_database_queries(client):
    attention = client.get("/api/detections?crop=番茄&status=attention").json()
    assert len(attention) == 2
    search = client.get("/api/detections", params={"search": "早疫病"}).json()
    assert len(search) == 2
    assert client.get("/api/detections?search=%").json() == []
    assert client.get("/api/detections?status=unknown").status_code == 422


def test_seed_runs_only_once_even_after_records_deleted(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'seed.db'}", upload_dir=tmp_path / "uploads", redis_url="", model_manifest="")
    app = create_app(settings)
    with TestClient(app) as client:
        headers = auth(client)
        for row in client.get("/api/detections").json():
            assert client.delete(f"/api/detections/{row['id']}", headers=headers).status_code == 200
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/detections").json() == []


def test_production_rejects_insecure_configuration():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        create_app(Settings(demo_mode=False))


def test_production_admin_rotation_replaces_password_and_revokes_existing_tokens(client):
    previous_token = auth(client)
    production_settings = replace(
        client.app.state.settings.base, demo_mode=False, admin_password="new-production-password-2026",
    )
    # Run the same production startup initializer on a persisted SQLite test DB.
    # SQLAlchemy initialization is identical on MySQL; no model/DB service is mocked.
    with client.app.state.session() as db:
        initialize_data(db, production_settings)
    assert client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin12345"},
    ).status_code == 401
    assert client.get("/api/auth/me", headers=previous_token).status_code == 401
    new_session = client.post(
        "/api/auth/login", json={"username": "admin", "password": production_settings.admin_password},
    )
    assert new_session.status_code == 200
    new_token = {"Authorization": f"Bearer {new_session.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=new_token).status_code == 200


def test_managed_admin_can_be_renamed_without_leaving_old_login(client):
    settings = replace(client.app.state.settings.base, admin_username="farm-owner", admin_password="new-password-2026")
    with client.app.state.session() as db:
        initialize_data(db, settings)
    assert client.post(
        "/api/auth/login", json={"username": "admin", "password": "admin12345"},
    ).status_code == 401
    assert client.post(
        "/api/auth/login", json={"username": "farm-owner", "password": settings.admin_password},
    ).status_code == 200


def test_production_rejects_compose_example_secret():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(
            demo_mode=False, jwt_secret="local-demo-change-this-secret-before-production-2026",
            admin_password="a-new-production-password", database_url="mysql+pymysql://example/db",
            redis_url="redis://localhost:6379/0",
        ).validate()
