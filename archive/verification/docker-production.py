import io
import json
import secrets
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values
from PIL import Image

root = Path(__file__).parent
old = dotenv_values(root / "docker-test.env")
state_file = root / "docker-transition.json"
with httpx.Client(base_url=f"http://127.0.0.1:{old['API_PORT']}", timeout=10) as client:
    if sys.argv[1] == "prepare":
        token = client.post("/api/auth/login", json={
            "username": old["ADMIN_USERNAME"], "password": old["ADMIN_PASSWORD"],
        }).json()["access_token"]
        image = io.BytesIO()
        Image.new("RGB", (24, 24), (80, 140, 50)).save(image, format="PNG")
        response = client.post("/api/detections", headers={"Authorization": f"Bearer {token}"},
                               data={"crop": "番茄"}, files={"file": ("persistence.png", image.getvalue(), "image/png")})
        assert response.status_code == 201, response.text
        record = response.json()
        config = dict(old)
        config["DEMO_MODE"] = "false"
        config["ADMIN_PASSWORD"] = secrets.token_hex(20)
        (root / "docker-production.env").write_text(
            "".join(f"{key}={value}\n" for key, value in config.items()), encoding="utf-8",
        )
        state_file.write_text(json.dumps({"token": token, "record": record}), encoding="utf-8")
        print("Prepared protected image persistence and credential-rotation test; no credentials logged.")
    else:
        config = dotenv_values(root / "docker-production.env")
        state = json.loads(state_file.read_text(encoding="utf-8"))
        for attempt in range(30):
            try:
                health = client.get("/api/health").json()
                if health["status"] == "ok" and health["mode"] == "production":
                    break
            except (httpx.RequestError, ValueError):
                pass
            time.sleep(1)
        else:
            raise AssertionError("Production API did not become ready")
        assert client.get("/api/detections").status_code == 401
        assert client.get(state["record"]["image_url"]).status_code == 401
        assert client.post("/api/auth/login", json={
            "username": old["ADMIN_USERNAME"], "password": old["ADMIN_PASSWORD"],
        }).status_code == 401
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {state['token']}"}).status_code == 401
        response = client.post("/api/auth/login", json={
            "username": config["ADMIN_USERNAME"], "password": config["ADMIN_PASSWORD"],
        })
        assert response.status_code == 200, response.text
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        assert client.get(state["record"]["image_url"], headers=headers).status_code == 200
        assert client.get(f"/api/detections/{state['record']['id']}", headers=headers).status_code == 200
        assert client.get("/api/dashboard", headers=headers).json()["is_demo"] is False
        assert client.delete(f"/api/detections/{state['record']['id']}", headers=headers).status_code == 200
        assert client.post("/api/auth/logout", headers=headers).status_code == 200
        print("PASS: production read/image authorization, password rotation, old-token invalidation, MySQL/upload persistence across API recreation.")
