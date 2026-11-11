"""Verify a trained candidate through the real API before configuring a release."""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import tempfile
import time

from prepare_data import CONFIG, DATA, ROOT, digest, write_json

TRAINING = ROOT / "training"
CANDIDATE = ROOT / "models/candidates" / CONFIG["training"]["name"]
MANIFEST_KEY = re.compile(r"^\s*(?:export\s+)?MODEL_MANIFEST\s*=")


def configured_text(text, manifest):
    """Change only MODEL_MANIFEST, preserving unrelated settings and comments."""
    lines = text.splitlines(keepends=True)
    previous = [line.rstrip("\r\n") for line in lines if MANIFEST_KEY.match(line)]
    retained = "".join(line for line in lines if not MANIFEST_KEY.match(line))
    if retained and not retained.endswith(("\r", "\n")):
        retained += "\n"
    value = Path(manifest).as_posix()
    if any(character in value for character in ('"', "\n", "\r")):
        raise ValueError("Manifest path cannot be represented safely in the environment file")
    return retained + f'MODEL_MANIFEST="{value}"\n', previous


def verify_metadata(candidate):
    metadata = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
    if metadata.get("validation_passed") is not True or metadata.get("task") != "classify":
        raise ValueError("Only a validated classification candidate can be deployed")
    limits = CONFIG["acceptance"]
    if not (
        metadata["validation_top1"] >= limits["validation_top1_min"]
        and metadata["validation_macro_f1"] >= limits["validation_macro_f1_min"]
        and 0 <= metadata["onnx_max_abs_error"] <= 1e-4
    ):
        raise ValueError("Candidate does not satisfy validation/export gates")
    dataset = json.loads((DATA / "dataset-report.json").read_text(encoding="utf-8"))
    if metadata["dataset_manifest_sha256"] != digest(DATA / "manifest.jsonl"):
        raise ValueError("Candidate dataset identity differs from the prepared dataset")
    if [label["key"] for label in metadata["classes"]] != dataset["classes"]:
        raise ValueError("Candidate class order differs from the dataset")
    for filename, field in (("model.onnx", "onnx_sha256"), ("best.pt", "weights_sha256")):
        if digest(candidate / filename) != metadata[field]:
            raise ValueError(f"Candidate checksum failed: {filename}")
    for split, prefix in (("val", "validation"), ("test", "test")):
        report = json.loads((candidate / f"{split}-report.json").read_text(encoding="utf-8"))
        if (
            report["images"] != dataset["counts"][split]
            or report["weights_sha256"] != metadata["weights_sha256"]
            or report["classes"] != dataset["classes"]
            or report["top1"] != metadata[f"{prefix}_top1"]
            or report["macro_f1"] != metadata[f"{prefix}_macro_f1"]
        ):
            raise ValueError(f"Evaluation evidence does not match the candidate: {split}")
    return metadata


def verify_api(candidate):
    """Exercise uploads, actual ONNX inference, persistence and cleanup in an isolated DB."""
    metadata = verify_metadata(candidate)
    # Prevent the module-level application from loading the live deployment in this QA process.
    os.environ["MODEL_MANIFEST"] = ""
    sys.path.insert(0, str(ROOT / "backend"))
    import numpy as np
    from fastapi.testclient import TestClient
    from PIL import Image
    from app.config import Settings
    from app.image_preprocessing import prepare_image
    from app.main import create_app

    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    observations = []
    with tempfile.TemporaryDirectory(prefix="model-verification-", dir=runtime) as temporary:
        folder = Path(temporary).resolve()
        if not folder.is_relative_to(runtime.resolve()):
            raise ValueError("QA directory escaped the project runtime directory")
        password = secrets.token_urlsafe(24)
        settings = Settings(
            database_url=f"sqlite:///{folder / 'test.db'}", upload_dir=folder / "uploads",
            redis_url="", demo_mode=True, admin_username="model-verification",
            admin_password=password, model_manifest=str(candidate / "manifest.json"),
            email_verification_enabled=False, llm_enabled=False,
        )
        with TestClient(create_app(settings)) as client:
            login = client.post("/api/auth/login", json={"username": settings.admin_username, "password": password})
            assert login.status_code == 200, login.text
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            assert client.get("/api/health").json()["model"] == "ready"
            info = client.get("/api/models").json()
            assert info["active"]["onnx_sha256"] == metadata["onnx_sha256"]
            assert info["active"]["class_count"] == len(metadata["classes"])
            baseline = client.get("/api/dashboard").json()["stats"]["total"]
            provider = client.app.state.inference
            for truth_index, label in enumerate(metadata["classes"]):
                path = next(iter(sorted((DATA / "classification/val" / label["key"]).glob("*"))))
                raw = path.read_bytes()
                # The upload endpoint normalizes images to JPEG; compare the exact saved pixels.
                normalized = io.BytesIO()
                with Image.open(io.BytesIO(raw)) as image:
                    image.convert("RGB").save(normalized, format="JPEG", quality=90)
                with Image.open(io.BytesIO(normalized.getvalue())) as image:
                    tensor = prepare_image(image, provider.image_size)
                probabilities = provider.session.run(None, {provider.input_name: tensor})[0][0]
                predicted_index = int(np.argmax(probabilities))
                predicted = metadata["classes"][predicted_index]
                confidence = float(probabilities[predicted_index])
                started = time.perf_counter()
                response = client.post(
                    "/api/detections", headers=headers, data={"crop": label["crop"], "note": "isolated model QA"},
                    files={"file": (path.name, raw, "image/jpeg")},
                )
                elapsed = time.perf_counter() - started
                mismatch = confidence >= provider.threshold and predicted["crop"] != label["crop"]
                if mismatch:
                    assert response.status_code == 422, response.text
                else:
                    assert response.status_code == 201, response.text
                    row = response.json()
                    assert not row["is_demo"]
                    assert abs(row["confidence"] - confidence) <= 1e-5
                    if confidence < provider.threshold:
                        assert row["status"] == "attention" and "置信度不足" in row["result"]
                    else:
                        assert row["result"] == predicted["label"]
                        assert row["status"] == ("healthy" if predicted["healthy"] else "attention")
                    assert client.get(f"/api/detections/{row['id']}").json() == row
                    assert client.get(row["image_url"]).status_code == 200
                    assert client.get("/api/dashboard").json()["stats"]["total"] == baseline + 1
                    assert client.delete(f"/api/detections/{row['id']}", headers=headers).status_code == 200
                    assert client.get(row["image_url"]).status_code == 404
                assert not list(settings.upload_dir.iterdir())
                assert client.get("/api/dashboard").json()["stats"]["total"] == baseline
                observations.append({
                    "class": label["key"], "prediction": predicted["key"], "confidence": confidence,
                    "correct": truth_index == predicted_index, "http_status": response.status_code,
                    "elapsed_seconds": elapsed, "sample": str(path.relative_to(ROOT)),
                })
            assert client.post("/api/detections", data={"crop": label["crop"]},
                               files={"file": ("sample.jpg", raw, "image/jpeg")}).status_code == 401
            assert client.post("/api/detections", headers=headers, data={"crop": label["crop"]},
                               files={"file": ("bad.jpg", b"invalid image", "image/jpeg")}).status_code == 422
            assert client.post("/api/detections", headers=headers, data={"crop": "香蕉"},
                               files={"file": ("sample.jpg", raw, "image/jpeg")}).status_code == 422
            assert not list(settings.upload_dir.iterdir())
            assert client.get("/api/dashboard").json()["stats"]["total"] == baseline
    report = {
        "passed": True, "created_at": time.time(), "manifest_sha256": digest(candidate / "manifest.json"),
        "onnx_sha256": metadata["onnx_sha256"], "class_samples": len(observations),
        "sample_top1": sum(item["correct"] for item in observations) / len(observations),
        "sample_top1_is_not_the_full_test_metric": True,
        "checks": ["actual_onnx", "38_class_uploads", "persistence", "dashboard", "deletion",
                   "authentication", "invalid_image", "unsupported_crop", "temporary_file_cleanup"],
        "observations": observations,
    }
    write_json(TRAINING / "system-verification.json", report)
    return report


def activate(candidate):
    metadata = verify_metadata(candidate)
    verification = json.loads((TRAINING / "system-verification.json").read_text(encoding="utf-8"))
    if verification.get("passed") is not True or verification["manifest_sha256"] != digest(candidate / "manifest.json"):
        raise ValueError("The exact candidate must pass API verification before activation")
    release_name = f'{CONFIG["training"]["name"]}-{metadata["onnx_sha256"][:12]}'
    release = ROOT / "models/releases" / release_name
    if release.exists():
        for source in candidate.iterdir():
            if source.is_file() and (not (release / source.name).exists() or digest(source) != digest(release / source.name)):
                raise ValueError("Existing release differs from candidate; refusing to overwrite")
    else:
        shutil.copytree(candidate, release)
    manifest = release / "manifest.json"
    env_path = ROOT / "backend/.env"
    original = env_path.read_bytes() if env_path.exists() else b""
    updated, previous = configured_text(original.decode("utf-8-sig"), manifest)
    if (env_path.read_bytes() if env_path.exists() else b"") != original:
        raise RuntimeError("Environment file changed concurrently; retry activation")
    record = {
        "configured_at": time.time(), "release": str(release), "manifest": str(manifest),
        "manifest_sha256": digest(manifest), "onnx_sha256": metadata["onnx_sha256"],
        "previous_model_manifest_lines": previous, "backend_restart_required": True,
    }
    backup = ROOT / ".runtime/model-deployments" / f"{release_name}-{time.time_ns()}.json"
    write_json(backup, record)
    temporary = env_path.with_name(f".env.model-{os.getpid()}.tmp")
    temporary.write_text(updated, encoding="utf-8")
    if (env_path.read_bytes() if env_path.exists() else b"") != original:
        temporary.unlink()
        raise RuntimeError("Environment file changed concurrently; retry activation")
    os.replace(temporary, env_path)
    write_json(TRAINING / "deployment.json", record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    report = verify_api(CANDIDATE)
    print(json.dumps({key: value for key, value in report.items() if key != "observations"}, ensure_ascii=False))
    if args.activate:
        print(json.dumps(activate(CANDIDATE), ensure_ascii=False))


if __name__ == "__main__":
    main()
