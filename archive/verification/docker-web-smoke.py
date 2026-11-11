import io
import re
from pathlib import Path

import httpx
from dotenv import dotenv_values
from PIL import Image

config = dotenv_values(Path(__file__).with_name("docker-production.env"))
with httpx.Client(base_url=f"http://127.0.0.1:{config['WEB_PORT']}", timeout=10) as client:
    response = client.get("/")
    assert response.status_code == 200 and '<div id="root"></div>' in response.text
    assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', response.text)
    assert assets
    for asset in assets:
        response = client.get(asset)
        assert response.status_code == 200 and len(response.content) > 1000
    response = client.get("/images/xiaohe.png")
    assert response.status_code == 200
    Image.open(io.BytesIO(response.content)).verify()
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["mode"] == "production"
    assert health["redis"] == "connected" and health["database"] == "connected"
    assert client.get("/api/detections").status_code == 401
    response = client.post("/api/auth/login", json={
        "username": config["ADMIN_USERNAME"], "password": config["ADMIN_PASSWORD"],
    })
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/api/dashboard", headers=headers).status_code == 200
    image = io.BytesIO()
    Image.new("RGB", (20, 20), (60, 120, 70)).save(image, format="PNG")
    response = client.post("/api/detections", headers=headers,
                           data={"crop": "玉米"}, files={"file": ("nginx.png", image.getvalue(), "image/png")})
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["status"] == "awaiting_model"
    assert client.get(record["image_url"]).status_code == 401
    assert client.get(record["image_url"], headers=headers).status_code == 200
    assert client.delete(f"/api/detections/{record['id']}", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    print("PASS: Nginx serves React HTML/JS/CSS/IP image; proxies health, login, protected reads, uploads and image authorization; sample cleanup complete.")
