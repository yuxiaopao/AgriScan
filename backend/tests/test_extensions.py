import hashlib
from datetime import timedelta

import httpx
import pytest

from app.config import Settings
from app.extensions import EmailChallenge
from app.db import utcnow
from test_api import client, auth, picture


def account(**changes):
    return {"username": "field_member", "name": "田间成员", "password": "strong-test-password", **changes}


def member_auth(client):
    assert client.post("/api/auth/register", json=account()).status_code == 201
    response = client.post("/api/auth/login", json=account())
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "member"
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_registration_toggle_validation_duplicates_and_permissions(client):
    assert client.get("/api/auth/config").json() == {
        "registration_enabled": True, "email_verification_enabled": False, "password_reset_enabled": False,
    }
    assert client.post("/api/auth/register", json=account(password="short")).status_code == 422
    assert client.post("/api/auth/register", json=account(email="bad-address")).status_code == 422
    headers = member_auth(client)
    assert client.post("/api/auth/register", json=account()).status_code == 409
    assert client.get("/api/settings/integrations", headers=headers).status_code == 403
    assert client.post("/api/plots", headers=headers, json={"name": "test", "crop": "番茄", "area": 1}).status_code == 201
    assert client.delete("/api/detections/demo-001", headers=headers).status_code == 404
    assert client.post("/api/models", headers=headers, data={"name": "model"},
                       files={"file": ("test.pt", b"test")}).status_code == 403
    upload = client.post("/api/detections", headers=headers, data={"crop": "番茄"},
                         files={"file": ("sample.png", picture(), "image/png")})
    assert upload.status_code == 201
    assert upload.json()["status"] == "awaiting_model"
    client.app.state.settings.registration_enabled = False
    assert client.post("/api/auth/register", json=account(username="another")).status_code == 403
    assert client.post("/api/auth/email-code", json={"email": "test@example.com"}).status_code == 403


def enable_mail(client, monkeypatch):
    settings = client.app.state.settings
    settings.email_verification_enabled = True
    settings.smtp_host = "smtp.example.com"
    settings.smtp_from = "agri@example.com"
    sent = []
    monkeypatch.setattr("app.extensions.send_code", lambda settings, email, code: sent.append((email, code)))
    return sent


def test_email_verification_expiry_attempts_consumption_and_cooldown(client, monkeypatch):
    sent = enable_mail(client, monkeypatch)
    email = "field@example.com"
    assert client.post("/api/auth/register", json=account()).status_code == 400
    assert client.post("/api/auth/email-code", json={"email": email}).status_code == 200
    assert client.post("/api/auth/email-code", json={"email": email}).status_code == 429
    code = sent[0][1]
    wrong = "111111" if code != "111111" else "222222"
    assert client.post("/api/auth/register", json=account(email=email, code=wrong)).status_code == 400
    with client.app.state.session() as db:
        challenge = db.get(EmailChallenge, email)
        assert challenge.digest != code and challenge.attempts == 1
    assert client.post("/api/auth/register", json=account(email=email, code=code)).status_code == 201
    assert client.post("/api/auth/register", json=account(username="reused", email=email, code=code)).status_code == 400
    email = "expired@example.com"
    assert client.post("/api/auth/email-code", json={"email": email}).status_code == 200
    with client.app.state.session() as db:
        db.get(EmailChallenge, email).expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert client.post("/api/auth/register", json=account(username="expired", email=email, code=sent[-1][1])).status_code == 400
    email = "attempts@example.com"
    assert client.post("/api/auth/email-code", json={"email": email}).status_code == 200
    code = sent[-1][1]
    wrong = "111111" if code != "111111" else "222222"
    for _ in range(5):
        assert client.post("/api/auth/register", json=account(username="attempts", email=email, code=wrong)).status_code == 400
    assert client.post("/api/auth/register", json=account(username="attempts", email=email, code=code)).status_code == 400


def test_smtp_failure_does_not_issue_challenge(client, monkeypatch):
    enable_mail(client, monkeypatch)
    def fail(*args):
        raise RuntimeError("provider-password-must-never-leak")
    monkeypatch.setattr("app.extensions.send_code", fail)
    response = client.post("/api/auth/email-code", json={"email": "failed@example.com"})
    assert response.status_code == 503
    assert "provider-password" not in response.text
    with client.app.state.session() as db:
        assert db.get(EmailChallenge, "failed@example.com") is None


def test_weight_registry_preserves_bytes_without_activating_inference(client):
    headers = auth(client)
    payload = b"inert-fixture-not-an-executable-model"
    response = client.post("/api/models", headers=headers, data={"name": "番茄识别 v1"},
                           files={"file": ("../../weights.pt", payload)})
    assert response.status_code == 201
    registry = client.get("/api/models").json()
    model = registry["items"][0]
    assert model["status"] == "pending_validation" and registry["active"] is None
    assert model["filename"] == "weights.pt"
    assert model["sha256"] == hashlib.sha256(payload).hexdigest()
    stored = client.app.state.settings.upload_dir / "models" / (model["id"] + ".pt")
    assert stored.read_bytes() == payload
    assert client.get(f"/api/uploads/models/{stored.name}").status_code in {401, 404}
    assert client.delete(f"/api/models/{model['id']}", headers=headers).status_code == 200
    assert not stored.exists() and client.get("/api/models").json()["items"] == []


@pytest.mark.parametrize("filename,payload,status", [
    ("weights.exe", b"x", 422), ("weights.pt", b"", 422),
    ("weights.onnx", b"x" * (1024 * 1024 + 1), 413),
], ids=["unsupported-extension", "empty-file", "oversized-file"])
def test_invalid_weights_leave_no_artifact(client, filename, payload, status):
    client.app.state.settings.model_max_mb = 1
    response = client.post("/api/models", headers=auth(client), data={"name": "bad"},
                           files={"file": (filename, payload)})
    assert response.status_code == status
    assert client.get("/api/models").json()["items"] == []
    assert list(client.app.state.settings.upload_dir.rglob("*.*")) == []


def test_llm_connection_uses_server_configuration_and_hides_secrets(client, monkeypatch):
    headers = auth(client)
    settings = client.app.state.settings
    assert client.post("/api/knowledge/ask", json={"question": "叶片黄斑"}, headers=headers).status_code == 503
    settings.llm_enabled = True
    settings.llm_base_url = "https://provider.example/v1/"
    settings.llm_api_key = "server-only-secret"
    settings.llm_model = "configured-model"
    calls = []
    def respond(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={"choices": [{"message": {"content": "记录叶片位置与变化时间。"}}]},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr("app.extensions.httpx.post", respond)
    result = client.post("/api/knowledge/ask", headers=headers, json={"question": "叶片黄斑"})
    assert result.status_code == 200 and result.json()["answer"] == "记录叶片位置与变化时间。"
    assert set(result.json()) == {"answer"}
    url, args = calls[0]
    assert url == "https://provider.example/v1/chat/completions"
    assert args["headers"]["Authorization"] == "Bearer server-only-secret"
    assert args["json"]["model"] == "configured-model"
    assert args["json"]["messages"][-1]["content"] == "叶片黄斑"
    assert "server-only-secret" not in client.get("/api/settings/integrations", headers=headers).text
    assert client.get("/api/settings/integrations", headers=headers).json()["llm_model"] == "configured-model"
    member = member_auth(client)
    assert client.get("/api/settings/integrations", headers=member).status_code == 403
    member_answer = client.post("/api/knowledge/ask", headers=member, json={"question": "叶片黄斑"})
    assert set(member_answer.json()) == {"answer"}
    assert "configured-model" not in member_answer.text
    assert client.get("/api/settings/integrations").status_code == 401
    def fail(*args, **kwargs):
        raise RuntimeError("server-only-secret")
    monkeypatch.setattr("app.extensions.httpx.post", fail)
    result = client.post("/api/knowledge/ask", headers=headers, json={"question": "叶片黄斑"})
    assert result.status_code == 502 and "server-only-secret" not in result.text


def test_required_integrations_configuration():
    with pytest.raises(ValueError, match="SMTP_HOST"):
        Settings(email_verification_enabled=True, smtp_host="", smtp_from="").validate()
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(llm_enabled=True, llm_api_key="", llm_model="").validate()


@pytest.mark.parametrize("url", [
    "http://localhost:55807/v1", "http://127.0.0.1:55807/v1",
    "http://[::1]:55807/v1", "https://provider.example/v1",
])
def test_llm_accepts_https_and_loopback_http(url):
    Settings(llm_enabled=True, llm_api_key="test-only", llm_model="test", llm_base_url=url).validate()


@pytest.mark.parametrize("url", [
    "http://provider.example/v1", "http://localhost.evil.example/v1",
    "https:///v1", "https://provider.example/v1?api_key=secret",
    "https://user:password@provider.example/v1",
])
def test_llm_rejects_insecure_remote_or_embedded_credentials(url):
    with pytest.raises(ValueError, match="HTTPS"):
        Settings(llm_enabled=True, llm_api_key="test-only", llm_model="test", llm_base_url=url).validate()
