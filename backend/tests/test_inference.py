"""Synthetic ONNX fixtures test API behavior, never disease-model accuracy."""
import hashlib
import json

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import Settings
from app.inference import AwaitingWeightsProvider, InferenceResult, OnnxClassificationProvider
from app.main import create_app
from test_api import auth, client, picture


def model_fixture(folder, probabilities=(0.9, 0.08, 0.02), **overrides):
    folder.mkdir(parents=True, exist_ok=True)
    output = numpy_helper.from_array(np.array([probabilities], dtype=np.float32), name="probabilities")
    graph = helper.make_graph(
        [helper.make_node("Constant", [], ["output"], value=output)],
        "SYNTHETIC_TEST_ONLY",
        [helper.make_tensor_value_info("images", TensorProto.FLOAT, ["batch", 3, 224, 224])],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 3])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)], ir_version=9)
    onnx.checker.check_model(model)
    path = folder / "model.onnx"
    onnx.save(model, path)
    metadata = {
        "name": "SYNTHETIC_TEST_ONLY", "task": "classify", "validation_passed": True,
        "onnx_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "image_size": 224, "threshold": 0.7, "test_top1": 0.0, "test_macro_f1": 0.0,
        "preprocessing": "resize-shortest-bilinear-center-crop-rgb-div255",
        "classes": [
            {"key": "Tomato___healthy", "crop": "番茄", "healthy": True, "label": "番茄健康"},
            {"key": "Tomato___Early_blight", "crop": "番茄", "healthy": False, "label": "番茄早疫病"},
            {"key": "Corn___healthy", "crop": "玉米", "healthy": True, "label": "玉米健康"},
        ], **overrides,
    }
    manifest = folder / "manifest.json"
    manifest.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    return manifest


def model_client(tmp_path, probabilities=(0.9, 0.08, 0.02)):
    manifest = model_fixture(tmp_path / "fixture", probabilities)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}",
                        upload_dir=tmp_path / "uploads", redis_url="", demo_mode=True,
                        admin_username="admin", admin_password="admin12345",
                        email_verification_enabled=False, llm_enabled=False,
                        model_manifest=str(manifest))
    return TestClient(create_app(settings))


def upload(client, crop="番茄", **fields):
    data = {**fields, **({"crop": crop} if crop is not None else {})}
    return client.post("/api/detections", headers=auth(client), data=data,
                       files={"file": ("sample.png", picture(), "image/png")})


@pytest.mark.parametrize("crop", [None, "", "   "])
def test_automatic_crop_uses_global_prediction_and_persists_candidates(tmp_path, crop):
    with model_client(tmp_path, (0.03, 0.02, 0.95)) as client:
        response = upload(client, crop, note="无需先选作物")
        assert response.status_code == 201, response.text
        row = response.json()
        assert row["crop"] == "玉米" and row["result"] == "玉米健康"
        assert row["status"] == "healthy" and row["confidence"] == pytest.approx(0.95)
        assert row["note"] == "无需先选作物" and row["plot_id"] is None
        assert [item["crop"] for item in row["candidates"]] == ["玉米", "番茄", "番茄"]
        assert [item["confidence"] for item in row["candidates"]] == pytest.approx([0.95, 0.03, 0.02])
        saved = client.get(f"/api/detections/{row['id']}").json()
        assert saved == row
        filtered = client.get('/api/detections', params={"crop": "玉米"}).json()
        assert any(item["id"] == row["id"] for item in filtered)
        assert client.get(row["image_url"]).status_code == 200


@pytest.mark.parametrize("probabilities,expected_crop,expected_label", [
    ((0.05, 0.9, 0.05), "番茄", "番茄早疫病"),
    ((0.35, 0.25, 0.4), "玉米", "置信度不足"),
])
def test_automatic_disease_and_low_confidence_remain_attention(tmp_path, probabilities, expected_crop, expected_label):
    with model_client(tmp_path, probabilities) as client:
        response = upload(client, None)
        assert response.status_code == 201, response.text
        row = response.json()
        assert row["crop"] == expected_crop and expected_label in row["result"]
        assert row["status"] == "attention"
        assert row["confidence"] == pytest.approx(max(probabilities))
        assert row["candidates"][0]["crop"] == expected_crop
        assert client.get('/api/dashboard').json()["stats"]["healthy"] == 8


@pytest.mark.parametrize("crop", [None, ""])
def test_automatic_crop_without_model_has_clear_error_and_saves_nothing(client, crop):
    before = client.get('/api/dashboard').json()["stats"]["total"]
    response = upload(client, crop)
    assert response.status_code == 422
    assert "模型" in response.json()["detail"] and "作物" in response.json()["detail"]
    assert client.get('/api/dashboard').json()["stats"]["total"] == before
    assert list(client.app.state.settings.upload_dir.iterdir()) == []


def test_provider_accepts_omitted_crop_and_reports_predicted_species(tmp_path):
    manifest = model_fixture(tmp_path / 'fixture', (0.03, 0.02, 0.95))
    path = tmp_path / 'sample.png'
    path.write_bytes(picture())
    result = OnnxClassificationProvider(manifest).predict(path)
    assert result.crop == '玉米' and result.label == '玉米健康'
    assert result.candidates[0]['crop'] == result.crop
    with pytest.raises(HTTPException) as error:
        AwaitingWeightsProvider().predict(path)
    assert error.value.status_code == 422


def test_automatic_inference_failure_leaves_no_image_or_record(tmp_path):
    with model_client(tmp_path, (float('nan'), 0.1, 0.2)) as client:
        response = upload(client, None)
        assert response.status_code == 503
        assert client.get('/api/dashboard').json()['stats']['total'] == 12
        assert list(client.app.state.settings.upload_dir.iterdir()) == []


def test_automatic_crop_links_matching_plot(tmp_path):
    with model_client(tmp_path, (0.03, 0.02, 0.95)) as client:
        response = upload(client, None, plot_id='plot-corn')
        assert response.status_code == 201, response.text
        row = response.json()
        assert row['crop'] == '玉米' and row['plot_id'] == 'plot-corn'
        assert row['plot_name'] == '03 号玉米种植区'
        assert client.get(f"/api/detections/{row['id']}").json() == row


@pytest.mark.parametrize('plot_id,expected', [('missing', 404), ('plot-tomato', 422)])
def test_automatic_crop_rejects_invalid_plot_without_saving(tmp_path, plot_id, expected):
    with model_client(tmp_path, (0.03, 0.02, 0.95)) as client:
        response = upload(client, None, plot_id=plot_id)
        assert response.status_code == expected
        if expected == 422:
            assert '玉米' in response.json()['detail'] and '取消关联' in response.json()['detail']
        assert client.get('/api/dashboard').json()['stats']['total'] == 12
        assert list(client.app.state.settings.upload_dir.iterdir()) == []


def test_automatic_crop_requires_valid_species_from_provider(tmp_path, monkeypatch):
    with model_client(tmp_path) as client:
        monkeypatch.setattr(client.app.state.inference, 'predict',
                            lambda path, crop=None: InferenceResult('attention', 'unknown', 0.4))
        assert upload(client, None).status_code == 503
        assert client.get('/api/dashboard').json()['stats']['total'] == 12
        assert list(client.app.state.settings.upload_dir.iterdir()) == []


def test_real_onnx_execution_is_saved_and_visible_in_api(tmp_path):
    with model_client(tmp_path) as client:
        result = upload(client)
        assert result.status_code == 201, result.text
        row = result.json()
        assert row["status"] == "healthy"
        assert row["result"] == "番茄健康"
        assert row["confidence"] == pytest.approx(0.9)
        assert [item["confidence"] for item in row["candidates"]] == pytest.approx([0.9, 0.08, 0.02])
        assert [item["crop"] for item in row["candidates"]] == ["番茄", "番茄", "玉米"]
        assert row["prediction_model"]["task"] == "classify"
        assert row["is_demo"] is False
        saved = client.get(f"/api/detections/{row['id']}").json()
        assert saved["result"] == "番茄健康"
        assert saved["candidates"] == row["candidates"]
        assert saved["prediction_model"] == row["prediction_model"]
        assert client.get("/api/health").json()["model"] == "ready"
        info = client.get("/api/models").json()
        assert info["active"]["task"] == "classify"
        assert set(info["supported_crops"]) == {"番茄", "玉米"}
        assert "苹果" in info["available_crops"]
        assert client.get("/api/dashboard").json()["stats"]["healthy"] == 9
        assert client.delete(f"/api/detections/{row['id']}", headers=auth(client)).status_code == 200
        assert client.get(f"/api/detections/{row['id']}").status_code == 404


@pytest.mark.parametrize("probabilities,expected", [
    ((0.05, 0.9, 0.05), "番茄早疫病"),
    ((0.5, 0.3, 0.2), "置信度不足"),
])
def test_disease_and_uncertainty_are_not_counted_as_healthy(tmp_path, probabilities, expected):
    with model_client(tmp_path, probabilities) as client:
        result = upload(client)
        assert result.status_code == 201
        assert result.json()["status"] == "attention"
        assert expected in result.json()["result"]
        assert client.get("/api/dashboard").json()["stats"]["healthy"] == 8


@pytest.mark.parametrize("crop", ["水稻", "玉米"])
def test_uncovered_and_mismatched_crops_leave_no_record_or_image(tmp_path, crop):
    with model_client(tmp_path) as client:
        result = upload(client, crop)
        assert result.status_code == 422
        assert client.get("/api/dashboard").json()["stats"]["total"] == 12
        assert list(client.app.state.settings.upload_dir.iterdir()) == []


def test_concurrent_inference_reports_busy_and_releases_no_extra_slot(tmp_path):
    with model_client(tmp_path) as client:
        guard = client.app.state.inference.guard
        assert guard.acquire(blocking=False)
        try:
            assert upload(client).status_code == 503
            assert not guard.acquire(blocking=False)
            assert list(client.app.state.settings.upload_dir.iterdir()) == []
        finally:
            guard.release()
        assert upload(client).status_code == 201


def test_nonfinite_model_output_rejected_and_slot_released(tmp_path):
    with model_client(tmp_path, (float("nan"), 0.1, 0.2)) as client:
        assert upload(client).status_code == 503
        assert list(client.app.state.settings.upload_dir.iterdir()) == []
        guard = client.app.state.inference.guard
        assert guard.acquire(blocking=False)
        guard.release()


@pytest.mark.parametrize("scores", [(0.999999, 0.0000008, 0.0000002), (1.0, 0.0, 0.0)])
def test_high_scores_are_preserved_without_artificial_caps(tmp_path, scores):
    with model_client(tmp_path, scores) as client:
        row = upload(client).json()
        assert row["confidence"] == float(np.float32(scores[0]))
        assert row["candidates"][0]["confidence"] == row["confidence"]


def test_probabilities_above_one_are_rejected_even_with_approximately_unit_sum(tmp_path):
    with model_client(tmp_path, (1.00001, 0.0, 0.0)) as client:
        assert upload(client).status_code == 503


@pytest.mark.parametrize("overrides,match", [
    ({"validation_passed": False}, "validated"),
    ({"onnx_sha256": "invalid"}, "SHA256"),
    ({"threshold": 1.1}, "threshold"),
    ({"preprocessing": "unknown"}, "preprocessing"),
])
def test_invalid_artifact_never_activates(tmp_path, overrides, match):
    manifest = model_fixture(tmp_path, **overrides)
    with pytest.raises(ValueError, match=match):
        OnnxClassificationProvider(manifest)


def test_every_available_crop_can_be_uploaded_filtered_and_shown_on_dashboard(client):
    headers = auth(client)
    crops = client.get("/api/models").json()["available_crops"]
    for crop in crops:
        response = client.post("/api/detections", headers=headers, data={"crop": crop},
                               files={"file": (f"{crop}.png", picture(), "image/png")})
        assert response.status_code == 201
        assert client.get("/api/detections", params={"crop": crop}).status_code == 200
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    distribution = dashboard.json()["distribution"]
    assert {item["name"] for item in distribution} == set(crops)
    assert all(item["color"].startswith("#") for item in distribution)
