"""Administrator workflows use isolated temporary databases, never the local workspace."""
from datetime import datetime, timedelta
import csv
import io

import pytest
from sqlalchemy import func, select

from app.admin_models import AuditLog, KnowledgeArticle, initialize_admin_data
from app.db import Detection, Plot, utcnow
from test_api import auth, client, picture


def new_user(client, headers, username="field_member", **overrides):
    response = client.post("/api/admin/users", headers=headers, json={
        "username": username, "name": "田间成员", "password": "field-password-2026", **overrides,
    })
    assert response.status_code == 201, response.text
    return response.json()


def login_as(client, username, password="field-password-2026"):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["access_token"]}


@pytest.mark.parametrize("path", ["overview", "users", "knowledge", "detections", "detections/export.csv", "plots", "audit"])
def test_admin_reads_never_inherit_anonymous_demo_access(client, path):
    assert client.get(f"/api/admin/{path}").status_code == 403
    admin = auth(client)
    member = new_user(client, admin)
    headers = login_as(client, member["username"])
    assert client.get(f"/api/admin/{path}", headers=headers).status_code == 403


def test_member_cannot_write_any_admin_resource(client):
    admin = auth(client)
    member = new_user(client, admin)
    headers = login_as(client, member["username"])
    assert client.post("/api/admin/users", headers=headers, json={
        "username": "hijack", "name": "非法", "password": "password-long-enough",
    }).status_code == 403
    assert client.patch(f"/api/admin/users/{member['id']}", headers=headers,
                        json={"role": "admin"}).status_code == 403
    assert client.post(f"/api/admin/users/{member['id']}/password", headers=headers,
                       json={"password": "other-password-2026"}).status_code == 403
    assert client.patch("/api/admin/knowledge/tomato-early-blight", headers=headers,
                        json={"status": "draft"}).status_code == 403
    assert client.delete("/api/admin/knowledge/tomato-early-blight", headers=headers).status_code == 403
    assert client.patch("/api/admin/detections/demo-001", headers=headers,
                        json={"name": "非法"}).status_code == 403


def test_user_create_filters_email_and_no_credential_disclosure(client):
    headers = auth(client)
    row = new_user(client, headers, email=" FIELD@EXAMPLE.COM ")
    assert row["email"] == "field@example.com" and row["role"] == "member"
    assert row["is_active"] and row["status"] == "active"
    assert row["managed"] is False and row["is_managed"] is False and row["is_self"] is False
    assert row["created_at"].endswith("+00:00") and row["updated_at"].endswith("+00:00")
    assert not ({"password", "password_hash", "token_version", "access_token"} & row.keys())
    result = client.get("/api/admin/users", headers=headers, params={
        "search": "field@example.com", "role": "member", "status": "active", "page_size": 1,
    }).json()
    assert result["total"] == 1 and result["page_size"] == 1 and result["items"][0]["id"] == row["id"]
    assert client.get("/api/admin/users", headers=headers, params={"search": "%"}).json()["total"] == 0
    assert client.post("/api/admin/users", headers=headers, json={
        "username": row["username"], "name": "重复", "password": "field-password-2026",
    }).status_code == 409
    assert client.post("/api/admin/users", headers=headers, json={
        "username": "duplicate_mail", "name": "重复邮箱", "password": "field-password-2026", "email": row["email"],
    }).status_code == 409
    assert client.get("/api/admin/users", headers=headers, params={"search": "duplicate_mail"}).json()["total"] == 0
    assert client.get("/api/admin/users?page=0", headers=headers).status_code == 422
    assert client.get("/api/admin/users?page_size=101", headers=headers).status_code == 422


def test_disabled_users_and_old_sessions_stay_revoked_after_reenable(client):
    admin = auth(client)
    row = new_user(client, admin)
    old = login_as(client, row["username"])
    assert client.patch(f"/api/admin/users/{row['id']}", headers=admin,
                        json={"status": "disabled"}).json()["is_active"] is False
    assert client.get("/api/auth/me", headers=old).status_code == 401
    assert client.post("/api/auth/login", json={
        "username": row["username"], "password": "field-password-2026",
    }).status_code == 401
    assert client.get("/api/admin/users?is_active=false", headers=admin).json()["total"] == 1
    assert client.patch(f"/api/admin/users/{row['id']}", headers=admin,
                        json={"is_active": True}).status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401
    assert client.get("/api/auth/me", headers=login_as(client, row["username"])).status_code == 200


def test_role_and_password_changes_revoke_sessions_and_are_audited(client):
    admin = auth(client)
    row = new_user(client, admin)
    old = login_as(client, row["username"])
    assert client.patch(f"/api/admin/users/{row['id']}", headers=admin, json={"role": "admin"}).status_code == 200
    assert client.get("/api/auth/me", headers=old).status_code == 401
    elevated = login_as(client, row["username"])
    assert client.get("/api/admin/overview", headers=elevated).status_code == 200
    reset = client.post(f"/api/admin/users/{row['id']}/password", headers=admin,
                        json={"password": "replacement-password-2026"})
    assert reset.status_code == 200
    assert client.get("/api/auth/me", headers=elevated).status_code == 401
    assert client.post("/api/auth/login", json={
        "username": row["username"], "password": "field-password-2026",
    }).status_code == 401
    assert client.get("/api/auth/me", headers=login_as(client, row["username"], "replacement-password-2026")).status_code == 200
    audit = client.get("/api/admin/audit", headers=admin,
                       params={"action": "user.password_reset", "resource_type": "user"}).json()
    assert audit["total"] == 1 and audit["items"][0]["resource_id"] == row["id"]
    assert "replacement-password-2026" not in str(audit) and "pbkdf2" not in str(audit)


def test_environment_admin_and_self_cannot_be_disabled_or_demoted(client):
    admin = auth(client)
    users = client.get("/api/admin/users", headers=admin).json()["items"]
    managed = next(row for row in users if row["managed"])
    assert managed["is_self"]
    for body in ({"role": "member"}, {"is_active": False}, {"status": "disabled"}):
        assert client.patch(f"/api/admin/users/{managed['id']}", headers=admin, json=body).status_code == 409
    assert client.post(f"/api/admin/users/{managed['id']}/password", headers=admin,
                       json={"password": "replacement-password-2026"}).status_code == 409
    second = new_user(client, admin, username="second_admin", role="admin")
    second_auth = login_as(client, second["username"])
    assert client.patch(f"/api/admin/users/{second['id']}", headers=second_auth,
                        json={"role": "member"}).status_code == 409
    assert client.patch(f"/api/admin/users/{second['id']}", headers=second_auth,
                        json={"is_active": False}).status_code == 409
    assert client.patch(f"/api/admin/users/{second['id']}", headers=admin,
                        json={"role": "member"}).status_code == 200


@pytest.mark.parametrize("body", [
    {"password": "short"}, {"password": "x" * 129}, {"name": "   "},
    {"role": "super_admin"}, {"email": "not-an-email"}, {"is_active": None},
    {"status": "disabled", "is_active": True},
])
def test_invalid_user_changes_are_rejected_without_audit_or_partial_mutation(client, body):
    headers = auth(client)
    row = new_user(client, headers)
    endpoint = f"/api/admin/users/{row['id']}"
    before = client.get("/api/admin/audit", headers=headers).json()["total"]
    if "password" in body:
        response = client.post(endpoint + "/password", headers=headers, json=body)
    else:
        response = client.patch(endpoint, headers=headers, json=body)
    assert response.status_code == 422
    assert client.get("/api/admin/audit", headers=headers).json()["total"] == before
    assert client.get("/api/admin/users", headers=headers, params={"search": row["username"]}).json()["items"][0]["name"] == row["name"]


def test_knowledge_publication_archive_and_one_time_seed(client):
    headers = auth(client)
    original = client.get("/api/knowledge").json()
    assert len(original) == 4
    body = {"title": "田间新指南", "crop": "番茄", "category": "采样指南", "summary": "摘要",
            "content": "请记录叶片正反面的变化。", "sources": [{"title": "来源", "url": "https://example.com/guide"}]}
    response = client.post("/api/admin/knowledge", headers=headers, json=body)
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["status"] == "draft" and row["published_at"] is None
    assert row["id"] not in {article["id"] for article in client.get("/api/knowledge").json()}
    published = client.patch(f"/api/admin/knowledge/{row['id']}", headers=headers, json={"status": "published"})
    assert published.status_code == 200 and published.json()["published_at"].endswith("+00:00")
    assert row["id"] in {article["id"] for article in client.get("/api/knowledge").json()}
    assert client.get("/api/admin/knowledge?status=published&crop=番茄&search=新指南", headers=headers).json()["total"] == 1
    archived = client.delete(f"/api/admin/knowledge/{row['id']}", headers=headers)
    assert archived.status_code == 200 and archived.json()["status"] == "archived"
    assert row["id"] not in {article["id"] for article in client.get("/api/knowledge").json()}
    assert client.get("/api/admin/knowledge?status=archived", headers=headers).json()["total"] == 1
    seeded = original[0]["id"]
    client.patch(f"/api/admin/knowledge/{seeded}", headers=headers, json={"title": "编辑后标题", "status": "draft"})
    with client.app.state.session() as db:
        initialize_admin_data(db)
        db.commit()
        assert db.get(KnowledgeArticle, seeded).title == "编辑后标题"
        assert db.get(KnowledgeArticle, seeded).status == "draft"
        assert db.scalar(select(func.count()).select_from(KnowledgeArticle)) == 5
    logs = client.get("/api/admin/audit?resource_type=knowledge", headers=headers).json()
    assert logs["total"] == 4 and not any(body["content"] in item["summary"] for item in logs["items"])


def test_invalid_knowledge_cannot_be_published_and_sources_are_safe(client):
    headers = auth(client)
    for body in (
        {"title": "空正文", "category": "指南", "status": "published"},
        {"title": "来源", "category": "指南", "sources": [{"title": "恶意", "url": "javascript:alert(1)"}]},
        {"title": "作物", "category": "指南", "crop": "不存在的作物"},
    ):
        assert client.post("/api/admin/knowledge", headers=headers, json=body).status_code == 422
    assert client.patch("/api/admin/knowledge/tomato-early-blight", headers=headers,
                        json={"content": ""}).status_code == 422
    assert client.get("/api/admin/audit", headers=headers).json()["total"] == 0


def test_detection_pagination_sources_dates_and_metadata_only_edit(client):
    headers = auth(client)
    first = client.get("/api/admin/detections?page_size=3", headers=headers).json()
    second = client.get("/api/admin/detections?page_size=3&page=2", headers=headers).json()
    assert first["total"] == 12 and len(first["items"]) == len(second["items"]) == 3
    assert not ({row["id"] for row in first["items"]} & {row["id"] for row in second["items"]})
    assert client.get("/api/admin/detections?source=upload", headers=headers).json()["total"] == 0
    assert client.get("/api/admin/detections?source=demo&crop=番茄&status=attention", headers=headers).json()["total"] == 2
    one_day = client.get("/api/admin/detections?date_from=2026-10-20&date_to=2026-10-20", headers=headers).json()
    assert one_day["total"] == 3
    assert client.get("/api/admin/detections?date_from=2026-10-21&date_to=2026-10-20", headers=headers).status_code == 422
    assert client.get("/api/admin/detections?search=%", headers=headers).json()["total"] == 0
    before = client.get("/api/detections/demo-001").json()
    wrong = client.patch("/api/admin/detections/demo-001", headers=headers,
                         json={"name": "不应保存", "plot_id": "plot-rice"})
    assert wrong.status_code == 422
    assert client.get("/api/detections/demo-001").json()["name"] == before["name"]
    assert client.patch("/api/admin/detections/demo-001", headers=headers,
                        json={"status": "healthy", "confidence": 1}).status_code == 422
    changed = client.patch("/api/admin/detections/demo-001", headers=headers,
                           json={"name": "核实后的采样名", "note": " 农技员备注 ", "plot_id": None})
    assert changed.status_code == 200, changed.text
    after = changed.json()
    assert after["plot_id"] is None and after["plot_name"] == "未关联地块"
    assert after["note"] == "农技员备注" and after["name"] == "核实后的采样名"
    assert all(after[key] == before[key] for key in ("crop", "status", "result", "confidence", "candidates", "prediction_model"))
    assert client.get("/api/admin/audit?action=detection.update", headers=headers).json()["total"] == 1
    uploaded = client.post("/api/detections", headers=headers, data={"crop": "番茄"},
                           files={"file": ("real.png", picture(), "image/png")})
    assert uploaded.status_code == 201
    assert client.get("/api/admin/detections?source=real", headers=headers).json()["total"] == 1
    assert client.get("/api/admin/detections?source=upload", headers=headers).json()["total"] == 1


def test_plot_query_overview_and_audit_are_real_database_results(client):
    headers = auth(client)
    plots = client.get("/api/admin/plots?crop=番茄&page_size=1", headers=headers).json()
    assert plots["total"] == 1 and plots["items"][0]["id"] == "plot-tomato"
    assert {"latitude", "longitude", "cover_url", "detections", "health_score"} <= plots["items"][0].keys()
    now = utcnow()
    with client.app.state.session() as db:
        db.add(Detection(id="recent-real", name="近期实测", crop="番茄", status="attention", is_demo=False,
                         created_at=now - timedelta(minutes=1)))
        db.commit()
    overview = client.get("/api/admin/overview", headers=headers)
    assert overview.status_code == 200, overview.text
    result = overview.json()
    assert result["counts"] == {"users": 1, "active_users": 1, "plots": 4, "detections": 13,
                                 "published_articles": 4, "model_artifacts": 0}
    assert result["services"] == {"database": "connected", "redis": "disabled", "model": "awaiting_weights"}
    assert len(result["trend"]) == 7 and result["trend"][-1]["total"] == 1 and result["trend"][-1]["attention"] == 1
    assert len(client.get("/api/admin/overview?days=30", headers=headers).json()["trend"]) == 30
    assert client.get("/api/admin/overview?days=8", headers=headers).status_code == 422
    assert result["recent_activity"] == []
    new_user(client, headers)
    audit = client.get("/api/admin/audit?resource_type=user&search=field_member&page_size=1", headers=headers).json()
    assert audit["total"] == 1 and audit["items"][0]["action"] == "user.create"
    assert client.get("/api/admin/overview", headers=headers).json()["recent_activity"][0]["id"] == audit["items"][0]["id"]


def test_detection_dates_and_overview_use_china_calendar_boundaries(client, monkeypatch):
    headers = auth(client)
    points = {
        "boundary-before": datetime(2026, 10, 19, 15, 59, 59, 999999),
        "boundary-start": datetime(2026, 10, 19, 16),
        "boundary-end": datetime(2026, 10, 20, 15, 59, 59, 999999),
        "boundary-after": datetime(2026, 10, 20, 16),
    }
    with client.app.state.session() as db:
        db.add_all(Detection(id=key, name="日界测试", crop="番茄", status="attention", created_at=moment)
                   for key, moment in points.items())
        db.commit()
    result = client.get("/api/admin/detections", headers=headers, params={
        "search": "日界测试", "date_from": "2026-10-20", "date_to": "2026-10-20",
    }).json()
    assert result["total"] == 2
    assert {row["id"] for row in result["items"]} == {"boundary-start", "boundary-end"}
    monkeypatch.setattr("app.admin.utcnow", lambda: datetime(2026, 10, 20, 16, 30))
    overview = client.get("/api/admin/overview", headers=headers).json()
    trend = {row["date"]: row for row in overview["trend"]}
    assert overview["trend"][-1]["date"] == "2026-10-21"
    assert trend["2026-10-20"]["total"] == 5
    assert trend["2026-10-21"]["total"] == 1


def test_detection_csv_exports_all_filtered_pages_and_escapes_formulas(client):
    headers = auth(client)
    names = ["=SUM(1,1)", "+1+1", "-1+1", "@SUM(1)", "\tformula", "\rformula", "  =1+1"]
    with client.app.state.session() as db:
        db.get(Plot, "plot-tomato").name = "=地块公式"
        db.add_all(Detection(id=f"csv-{index}", name=name, crop="番茄", plot_id="plot-tomato",
                             status="attention", result="=结果公式", confidence=0.8,
                             note="@备注公式\n含换行", created_at=datetime(2026, 10, 20, 8), is_demo=False)
                   for index, name in enumerate(names))
        db.commit()
    filters = {"source": "upload", "crop": "番茄", "status": "attention", "plot_id": "plot-tomato",
               "date_from": "2026-10-20", "date_to": "2026-10-20", "search": "备注公式"}
    page = client.get("/api/admin/detections", headers=headers, params={**filters, "page_size": 2}).json()
    assert page["total"] == 7 and len(page["items"]) == 2
    response = client.get("/api/admin/detections/export.csv", headers=headers, params=filters)
    assert response.status_code == 200, response.text
    assert response.content.startswith(b"\xef\xbb\xbf")
    assert response.headers["content-disposition"] == 'attachment; filename="agriscan-detections.csv"'
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"), newline="")))
    assert len(rows) == 7 and {row["id"] for row in rows} == {f"csv-{index}" for index in range(7)}
    assert set(rows[0]) == {"id", "name", "crop", "plot_name", "status", "result", "confidence", "created_at", "is_demo", "note"}
    assert {row["name"] for row in rows} == {"'" + name for name in names}
    assert all(row["plot_name"] == "'=地块公式" and row["result"] == "'=结果公式"
               and row["note"] == "'@备注公式\n含换行" and row["is_demo"] == "false" for row in rows)
    assert client.get("/api/admin/detections/export.csv", headers=headers,
                      params={**filters, "date_to": "2026-10-19"}).status_code == 422


def test_detection_csv_refuses_more_than_ten_thousand_matches(client):
    headers = auth(client)
    with client.app.state.session() as db:
        db.execute(Detection.__table__.insert(), [
            {"id": f"export-limit-{index}", "name": "大批量导出", "crop": "番茄", "status": "healthy"}
            for index in range(10001)
        ])
        db.commit()
    response = client.get("/api/admin/detections/export.csv", headers=headers, params={"search": "大批量导出"})
    assert response.status_code == 422
    assert "10000" in response.json()["detail"] and "缩小" in response.json()["detail"]
