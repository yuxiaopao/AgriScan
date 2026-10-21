from datetime import timedelta

import httpx
from app.assistant import Conversation
from app.db import utcnow
from test_api import client, auth, picture
from test_extensions import member_auth


def fake_provider(client, monkeypatch):
    client.app.state.settings.llm_enabled = True
    calls = []
    def reply(url, **kwargs):
        calls.append(kwargs["json"]["messages"])
        return httpx.Response(200, json={"choices": [{"message": {"content": "记下叶片变化与采样日期。"}}]},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr("app.extensions.httpx.post", reply)
    return calls


def test_history_is_private_and_authentication_required(client):
    headers = auth(client)
    chat = client.post("/api/assistant/conversations", headers=headers).json()
    other = member_auth(client)
    assert client.get("/api/assistant/conversations").status_code == 401
    assert client.post("/api/assistant/conversations").status_code == 401
    assert client.get("/api/assistant/conversations", headers=other).json() == []
    route = f"/api/assistant/conversations/{chat['id']}"
    assert client.get(route, headers=other).status_code == 404
    assert client.post(route + "/messages", headers=other, json={"question": "查看对话"}).status_code == 404
    assert client.get(route, headers=headers).json()["messages"] == []


def test_messages_persist_and_followups_include_server_history(client, monkeypatch):
    calls = fake_provider(client, monkeypatch)
    headers = auth(client)
    chat = client.post("/api/assistant/conversations", headers=headers).json()
    route = f"/api/assistant/conversations/{chat['id']}"
    for question in ["我的番茄叶片出现了黄斑", "刚才说的是哪种作物？"]:
        response = client.post(route + "/messages", headers=headers, json={"question": question})
        assert response.status_code == 200, response.text
        assert set(response.json()) == {"conversation", "messages"}
    history = client.get(route, headers=headers).json()
    assert len(history["messages"]) == 4
    assert [m["role"] for m in history["messages"]] == ["user", "assistant", "user", "assistant"]
    assert history["conversation"]["title"] == "我的番茄叶片出现了黄斑"
    assert calls[1][1:] == [
        {"role": "user", "content": "我的番茄叶片出现了黄斑"},
        {"role": "assistant", "content": "记下叶片变化与采样日期。"},
        {"role": "user", "content": "刚才说的是哪种作物？"},
    ]
    assert client.get("/api/assistant/conversations", headers=headers).json()[0]["id"] == chat["id"]


def test_failure_preserves_history_and_releases_conversation(client, monkeypatch):
    headers = auth(client)
    chat = client.post("/api/assistant/conversations", headers=headers).json()
    route = f"/api/assistant/conversations/{chat['id']}"
    client.app.state.settings.llm_enabled = False
    assert client.post(route + "/messages", headers=headers, json={"question": "种植问题"}).status_code == 503
    assert client.get(route, headers=headers).json()["messages"] == []
    fake_provider(client, monkeypatch)
    assert client.post(route + "/messages", headers=headers, json={"question": "重新发送问题"}).status_code == 200
    assert len(client.get(route, headers=headers).json()["messages"]) == 2


def test_busy_conversation_and_blank_question_do_not_call_provider(client, monkeypatch):
    calls = fake_provider(client, monkeypatch)
    headers = auth(client)
    chat = client.post("/api/assistant/conversations", headers=headers).json()
    route = f"/api/assistant/conversations/{chat['id']}/messages"
    assert client.post(route, headers=headers, json={"question": "   "}).status_code == 422
    with client.app.state.session() as db:
        db.get(Conversation, chat["id"]).busy_until = utcnow() + timedelta(minutes=1)
        db.commit()
    assert client.post(route, headers=headers, json={"question": "第二个问题"}).status_code == 409
    assert calls == []


def uploaded_detection(client, headers):
    response = client.post("/api/detections", headers=headers, data={"crop": "番茄", "note": "叶背发现小孔"},
                           files={"file": ("leaf.png", picture(), "image/png")})
    assert response.status_code == 201
    return response.json()


def test_detection_analysis_uses_saved_facts_and_image_and_is_idempotent(client, monkeypatch):
    import base64
    import io
    from PIL import Image
    calls = fake_provider(client, monkeypatch)
    headers = auth(client)
    detection = uploaded_detection(client, headers)
    route = f"/api/assistant/detections/{detection['id']}/analysis"
    response = client.post(route, headers=headers, json={"result": "伪造的虫害确诊"})
    assert response.status_code == 200, response.text
    parts = calls[0][-1]["content"]
    assert parts[0]["type"] == "text" and "等待分类模型" in parts[0]["text"]
    assert "叶背发现小孔" in parts[0]["text"] and "伪造的虫害确诊" not in parts[0]["text"]
    assert "无法确认是否有虫害" in parts[0]["text"]
    assert "复拍与复检建议" in parts[0]["text"]
    image = Image.open(io.BytesIO(base64.b64decode(parts[1]["image_url"]["url"].split(",")[1])))
    assert image.format == "JPEG" and max(image.size) <= 1024
    assert len(response.json()["messages"]) == 2
    assert "尚无模型结论" in response.json()["messages"][0]["content"]
    repeated = client.post(route, headers=headers)
    assert repeated.json() == response.json()
    assert len(calls) == 1
    chat_id = response.json()["conversation"]["id"]
    other = member_auth(client)
    assert client.get(f"/api/assistant/conversations/{chat_id}", headers=other).status_code == 404
    # The persisted interpretation survives original sample deletion.
    assert client.delete(f"/api/detections/{detection['id']}", headers=headers).status_code == 200
    assert client.get(f"/api/assistant/conversations/{chat_id}", headers=headers).status_code == 200


def test_analysis_failure_keeps_detection_and_can_retry(client, monkeypatch):
    headers = auth(client)
    detection = uploaded_detection(client, headers)
    route = f"/api/assistant/detections/{detection['id']}/analysis"
    assert client.post(route, headers=headers).status_code == 503
    assert client.get(f"/api/detections/{detection['id']}", headers=headers).status_code == 200
    assert client.get("/api/assistant/conversations", headers=headers).json() == []
    calls = fake_provider(client, monkeypatch)
    assert client.post(route, headers=headers).status_code == 200
    assert len(calls) == 1


def test_analysis_rejects_anonymous_missing_and_demo_records(client, monkeypatch):
    calls = fake_provider(client, monkeypatch)
    headers = auth(client)
    assert client.post("/api/assistant/detections/demo-001/analysis").status_code == 401
    assert client.post("/api/assistant/detections/demo-001/analysis", headers=headers).status_code == 422
    assert client.post("/api/assistant/detections/missing/analysis", headers=headers).status_code == 404
    assert calls == []
