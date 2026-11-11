import io
import json
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values
from PIL import Image

config = dotenv_values(Path(__file__).with_name("docker-test.env"))
base_url = f"http://127.0.0.1:{config['API_PORT']}"
with httpx.Client(base_url=base_url, timeout=15) as client:
    for attempt in range(60):
        try:
            health = client.get("/api/health").json()
            if health.get("status") == "ok":
                break
        except (httpx.RequestError, ValueError):
            pass
        time.sleep(1)
    else:
        raise AssertionError("API did not become healthy")
    assert health["database"] == "connected", health
    assert health["redis"] == "connected", health
    assert health["model"] == "awaiting_weights", health
    print("PASS: API health, MySQL and Redis connected, model awaiting weights", flush=True)

    before = client.get("/api/dashboard").json()["stats"]
    assert client.post("/api/plots", json={"name": "auth-check", "crop": "小麦", "area": 1}).status_code == 401
    response = client.post("/api/auth/login", json={
        "username": config["ADMIN_USERNAME"], "password": config["ADMIN_PASSWORD"],
    })
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    print("PASS: anonymous write denied; administrator login and authenticated identity", flush=True)

    response = client.post("/api/plots", headers=headers, json={
        "name": "容器验证地块", "crop": "小麦", "area": 3.5,
        "location": "自动验证", "manager": "Smoke test",
    })
    assert response.status_code == 201, response.text
    plot = response.json()
    response = client.patch(f"/api/plots/{plot['id']}", headers=headers, json={"area": 4.25})
    assert response.status_code == 200 and response.json()["area"] == 4.25, response.text

    image = io.BytesIO()
    Image.new("RGB", (40, 30), (50, 135, 85)).save(image, format="PNG")
    response = client.post("/api/detections", headers=headers,
                           data={"crop": "小麦", "plot_id": plot["id"], "note": "容器集成验证"},
                           files={"file": ("smoke.png", image.getvalue(), "image/png")})
    assert response.status_code == 201, response.text
    detection = response.json()
    assert detection["status"] == "awaiting_model"
    assert detection["confidence"] is None and detection["result"] is None
    assert detection["is_demo"] is False and detection["plot_id"] == plot["id"]
    response = client.get(detection["image_url"], headers=headers)
    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    assert Image.open(io.BytesIO(response.content)).size == (40, 30)
    assert client.get(f"/api/detections/{detection['id']}").json()["note"] == "容器集成验证"
    assert len(client.get("/api/detections?crop=小麦&status=awaiting_model").json()) >= 1
    after_upload = client.get("/api/dashboard").json()["stats"]
    assert after_upload["total"] == before["total"] + 1
    assert after_upload["pending"] == before["pending"] + 1
    print("PASS: MySQL-backed plot create/update, image upload/read, awaiting-model record and cache refresh", flush=True)

    assert client.delete(f"/api/plots/{plot['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/detections/{detection['id']}").json()["plot_id"] is None
    assert client.delete(f"/api/detections/{detection['id']}", headers=headers).status_code == 200
    assert client.get(detection["image_url"], headers=headers).status_code == 404
    assert client.get("/api/dashboard").json()["stats"] == before
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    print("PASS: plot deletion preserves history, record deletion removes image, cache restored, logout revokes token", flush=True)
    print(json.dumps({"result": "all integration checks passed", "database": "mysql", "redis": "connected"}, ensure_ascii=False))
