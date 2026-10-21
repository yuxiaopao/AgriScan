"""Resumable local training, sealed-test evaluation and ONNX candidate packaging."""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from prepare_data import CONFIG, DATA, ROOT, digest, write_json

TRAINING = ROOT / "training"
STATUS = TRAINING / "status.json"
RUN = ROOT / "runs" / "classify" / CONFIG["training"]["name"]
STATE = {"pid": os.getpid(), "started_at": time.time()}

CROP_NAMES = {
    "Apple": "苹果", "Blueberry": "蓝莓", "Cherry_(including_sour)": "樱桃",
    "Corn_(maize)": "玉米", "Grape": "葡萄", "Orange": "柑橘", "Peach": "桃",
    "Pepper,_bell": "甜椒", "Potato": "马铃薯", "Raspberry": "树莓",
    "Soybean": "大豆", "Squash": "南瓜", "Strawberry": "草莓", "Tomato": "番茄",
}
DISEASE_NAMES = {
    "Apple_scab": "黑星病", "Black_rot": "黑腐病", "Cedar_apple_rust": "锈病",
    "healthy": "健康", "Powdery_mildew": "白粉病",
    "Cercospora_leaf_spot Gray_leaf_spot": "灰斑病", "Common_rust_": "普通锈病",
    "Northern_Leaf_Blight": "大斑病", "Esca_(Black_Measles)": "埃斯卡病（黑麻疹病）",
    "Leaf_blight_(Isariopsis_Leaf_Spot)": "叶枯病", "Haunglongbing_(Citrus_greening)": "黄龙病",
    "Bacterial_spot": "细菌性斑点病", "Early_blight": "早疫病", "Late_blight": "晚疫病",
    "Leaf_scorch": "叶焦病", "Leaf_Mold": "叶霉病", "Septoria_leaf_spot": "斑枯病",
    "Spider_mites Two-spotted_spider_mite": "二斑叶螨危害", "Target_Spot": "靶斑病",
    "Tomato_Yellow_Leaf_Curl_Virus": "黄化曲叶病毒病", "Tomato_mosaic_virus": "花叶病毒病",
}


def state(stage, **details):
    STATE.update(stage=stage, updated_at=time.time(), **details)
    write_json(STATUS, STATE)
    print(json.dumps(STATE, ensure_ascii=False), flush=True)


def check_dataset():
    report_path = DATA / "dataset-report.json"
    if not report_path.exists():
        raise FileNotFoundError("Dataset preparation has not completed")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if digest(DATA / "manifest.jsonl") != report["manifest_sha256"]:
        raise ValueError("Dataset manifest has changed")
    if report["cross_split_leaf_overlap"] or report["cross_split_sha256_overlap"]:
        raise ValueError("Dataset leakage detected")
    if report["invalid_images"] or len(report["classes"]) != CONFIG["dataset"]["classes"]:
        raise ValueError("Dataset quality checks failed")
    return report


def make_model():
    import torch
    import yaml
    from ultralytics import YOLO
    weight = ROOT / CONFIG["training"]["weights"]
    if digest(weight) != CONFIG["training"]["weights_sha256"]:
        raise ValueError("Source weight SHA256 mismatch")
    detector = YOLO(str(weight))
    if detector.task != "detect":
        raise ValueError(f"Expected detection source weights, received {detector.task}")
    architecture = deepcopy(detector.model.yaml)
    architecture["nc"] = CONFIG["dataset"]["classes"]
    architecture["head"] = [[-1, 1, "Classify", ["nc"]]]
    architecture["scale"] = "m"
    yaml_path = TRAINING / "yolo26m-plantvillage-cls.yaml"
    yaml_path.write_text(yaml.safe_dump(architecture, sort_keys=False), encoding="utf-8")
    classifier = YOLO(str(yaml_path), task="classify")
    classifier.load(str(weight))
    backbone_length = len(architecture["backbone"])
    source = detector.model.float().state_dict()
    target = classifier.model.float().state_dict()
    backbone_keys = [key for key in target if int(key.split(".")[1]) < backbone_length]
    mismatched = [key for key in backbone_keys
                  if key not in source or not torch.equal(source[key], target[key])]
    if mismatched:
        raise ValueError(f"Backbone weights did not transfer exactly: {mismatched[:5]}")
    report = {"source": str(weight), "source_sha256": digest(weight),
              "source_task": detector.task, "target_task": classifier.task,
              "backbone_layers": backbone_length, "verified_backbone_tensors": len(backbone_keys),
              "transferred_parameters": sum(target[key].numel() for key in backbone_keys),
              "total_parameters": sum(parameter.numel() for parameter in classifier.model.parameters()),
              "new_head": "Classify", "classes": CONFIG["dataset"]["classes"]}
    write_json(TRAINING / "transfer-report.json", report)
    return classifier


def gpu_smoke():
    import torch
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; refusing to silently train on CPU")
    model = make_model().model.cuda().train()
    size = CONFIG["training"]["imgsz"]
    batch = CONFIG["training"]["batch"]
    inputs = torch.randn(batch, 3, size, size, device="cuda")
    labels = torch.arange(batch, device="cuda") % CONFIG["dataset"]["classes"]
    optimizer = torch.optim.AdamW(model.parameters(), lr=CONFIG["training"]["lr0"])
    scaler = torch.amp.GradScaler("cuda")
    with torch.autocast("cuda", dtype=torch.float16):
        outputs = model(inputs)
        loss = torch.nn.functional.cross_entropy(outputs, labels)
    scaler.scale(loss).backward()
    scaler.step(optimizer)
    scaler.update()
    torch.cuda.synchronize()
    if not torch.isfinite(loss):
        raise ValueError("GPU smoke test produced a non-finite loss")
    report = {"passed": True, "synthetic_test_only": True, "gpu": torch.cuda.get_device_name(0),
              "torch": torch.__version__, "cuda": torch.version.cuda,
              "batch": batch, "image_size": size, "loss": loss.item(),
              "peak_allocated_bytes": torch.cuda.max_memory_allocated()}
    write_json(TRAINING / "gpu-smoke.json", report)
    print(json.dumps(report), flush=True)
    del model, inputs, labels, optimizer, scaler
    torch.cuda.empty_cache()


def epoch_callback(trainer):
    metrics = {key: float(value) for key, value in trainer.metrics.items()}
    state("training", epoch=trainer.epoch + 1, epochs=trainer.epochs,
          metrics=metrics, run_directory=str(trainer.save_dir))


def evaluate(model_path, split):
    """Evaluate every sample once; the test split never affects checkpoint selection."""
    import numpy as np
    from PIL import Image
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
    from ultralytics import YOLO
    model = YOLO(str(model_path))
    names = [model.names[index] for index in range(len(model.names))]
    expected = check_dataset()["classes"]
    if names != expected:
        raise ValueError("Model class order differs from dataset class order")
    samples = [(path, index) for index, name in enumerate(names)
               for path in sorted((DATA / "classification" / split / name).glob("*")) if path.is_file()]
    truth, predictions, scores, paths = [], [], [], []
    batch_size = CONFIG["training"]["batch"]
    for start in range(0, len(samples), batch_size):
        group = samples[start:start+batch_size]
        images = []
        for path, _ in group:
            with Image.open(path) as image:
                images.append(image.convert("RGB"))
        results = model.predict(images, imgsz=CONFIG["training"]["imgsz"],
                                device=CONFIG["training"]["device"], verbose=False)
        for (path, label), result in zip(group, results, strict=True):
            truth.append(label)
            predictions.append(int(result.probs.top1))
            scores.append(float(result.probs.top1conf))
            paths.append(str(path.relative_to(DATA)))
        if start % (batch_size * 50) == 0:
            state(f"evaluating_{split}", evaluated=min(start+batch_size, len(samples)), total=len(samples))
    metrics = classification_report(truth, predictions, labels=list(range(len(names))),
                                    target_names=names, output_dict=True, zero_division=0)
    confidence = np.array(scores)
    accepted = confidence >= CONFIG["acceptance"]["confidence_threshold"]
    correct = np.array(truth) == np.array(predictions)
    report = {"split": split, "images": len(samples), "top1": accuracy_score(truth, predictions),
              "macro_f1": metrics["macro avg"]["f1-score"], "per_class": metrics,
              "confidence_threshold": CONFIG["acceptance"]["confidence_threshold"],
              "coverage": float(accepted.mean()),
              "accepted_accuracy": float(correct[accepted].mean()) if accepted.any() else None,
              "confusion_matrix": confusion_matrix(truth, predictions, labels=list(range(len(names)))).tolist(),
              "classes": names, "weights_sha256": digest(model_path)}
    write_json(RUN / f"{split}-report.json", report)
    with (RUN / f"{split}-predictions.csv").open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["path", "truth", "prediction", "confidence"])
        writer.writerows((path, names[label], names[prediction], score)
                         for path, label, prediction, score in zip(paths, truth, predictions, scores, strict=True))
    return report


def export_candidate(best_path, validation, test):
    import numpy as np
    import onnxruntime as ort
    from PIL import Image
    from ultralytics import YOLO
    sys.path.insert(0, str(ROOT / "backend"))
    from app.image_preprocessing import prepare_image
    model = YOLO(str(best_path))
    exported = Path(model.export(format="onnx", imgsz=CONFIG["training"]["imgsz"],
                                 dynamic=True, simplify=False, opset=17, device="cpu"))
    session = ort.InferenceSession(str(exported), providers=["CPUExecutionProvider"])
    # Save and use the same exact transforms for training validation and deployment.
    transforms = getattr(model.model, "transforms", None)
    if transforms is None:
        from ultralytics.data.augment import classify_transforms
        transforms = classify_transforms(size=CONFIG["training"]["imgsz"])
    samples = []
    for name in validation["classes"]:
        samples.append(next((DATA / "classification" / "val" / name).glob("*")))
    maximum_difference = 0.0
    for path in samples:
        with Image.open(path) as image:
            image = image.convert("RGB")
            tensor = prepare_image(image, CONFIG["training"]["imgsz"])
            reference_tensor = transforms(image).unsqueeze(0).numpy()
            if not np.allclose(tensor, reference_tensor, atol=1e-7):
                raise ValueError("Deployment preprocessing differs from training validation")
            actual = session.run(None, {session.get_inputs()[0].name: tensor})[0][0]
            expected = model.predict(image, imgsz=CONFIG["training"]["imgsz"], device="cpu", verbose=False)[0].probs.data.cpu().numpy()
        maximum_difference = max(maximum_difference, float(np.max(np.abs(actual-expected))))
        if int(np.argmax(actual)) != int(np.argmax(expected)) or not np.allclose(actual, expected, atol=1e-4, rtol=1e-3):
            raise ValueError(f"PyTorch/ONNX prediction mismatch for {path.name}")
    labels = []
    for name in validation["classes"]:
        crop, disease = name.split("___", 1)
        labels.append({"key": name, "crop": CROP_NAMES[crop], "disease": DISEASE_NAMES[disease],
                       "label": CROP_NAMES[crop] + DISEASE_NAMES[disease], "healthy": disease == "healthy"})
    package = ROOT / "models" / "candidates" / CONFIG["training"]["name"]
    package.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best_path, package / "best.pt")
    shutil.copy2(exported, package / "model.onnx")
    for split in ("val", "test"):
        shutil.copy2(RUN / f"{split}-report.json", package / f"{split}-report.json")
    metadata = {"name": CONFIG["training"]["name"], "task": "classify", "status": "candidate",
                "source_weights_sha256": CONFIG["training"]["weights_sha256"],
                "dataset_manifest_sha256": check_dataset()["manifest_sha256"],
                "onnx_sha256": digest(package / "model.onnx"), "weights_sha256": digest(best_path),
                "image_size": CONFIG["training"]["imgsz"], "classes": labels,
                "preprocessing": "resize-shortest-bilinear-center-crop-rgb-div255",
                "threshold": CONFIG["acceptance"]["confidence_threshold"],
                "transforms_repr": repr(transforms), "validation_top1": validation["top1"],
                "validation_macro_f1": validation["macro_f1"], "test_top1": test["top1"],
                "test_macro_f1": test["macro_f1"], "onnx_max_abs_error": maximum_difference,
                "scope": "Single leaf classification on PlantVillage; field images require external validation.",
                "validation_passed": validation["top1"] >= CONFIG["acceptance"]["validation_top1_min"]
                    and validation["macro_f1"] >= CONFIG["acceptance"]["validation_macro_f1_min"]}
    write_json(package / "manifest.json", metadata)
    return package, metadata


def run(resume=False):
    from ultralytics import YOLO
    import torch
    check_dataset()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; no CPU fallback permitted")
    environment = {name: importlib.metadata.version(name)
                   for name in ("torch", "torchvision", "ultralytics", "numpy", "Pillow", "scikit-learn")}
    environment.update(python=sys.version, gpu=torch.cuda.get_device_name(0))
    write_json(TRAINING / "environment.json", environment)
    with (TRAINING / "requirements-lock.txt").open("w", encoding="utf-8") as output:
        subprocess.run([sys.executable, "-m", "pip", "freeze"], stdout=output, check=True)
    args = deepcopy(CONFIG["training"])
    args.pop("weights")
    args.pop("weights_sha256")
    args["data"] = str(DATA / "classification")
    args["project"] = str(ROOT / "runs" / "classify")
    args["exist_ok"] = True
    args["pretrained"] = True
    args["verbose"] = False
    last = RUN / "weights" / "last.pt"
    finished = RUN / "training-complete.json"
    if not finished.exists():
        if resume:
            if not last.is_file():
                raise FileNotFoundError("Cannot resume: last.pt is absent")
            model = YOLO(str(last))
        else:
            if last.exists() or (RUN / "results.csv").exists():
                raise ValueError("An existing run exists. Use --resume; refusing to overwrite")
            model = make_model()
        model.add_callback("on_fit_epoch_end", epoch_callback)
        state("training", epoch=0, epochs=args["epochs"])
        model.train(**({"resume": True, "device": args["device"]} if resume else args))
        write_json(finished, {"completed_at": time.time(), "best": str(RUN / "weights/best.pt")})
    best = RUN / "weights" / "best.pt"
    if not best.is_file():
        raise FileNotFoundError("Training did not produce best.pt")
    validation = evaluate(best, "val")
    test = evaluate(best, "test")
    state("exporting")
    package, metadata = export_candidate(best, validation, test)
    stage = "ready_for_system_test" if metadata["validation_passed"] else "quality_gate_failed"
    state(stage, candidate_directory=str(package), validation_top1=validation["top1"],
          validation_macro_f1=validation["macro_f1"], test_top1=test["top1"], test_macro_f1=test["macro_f1"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    os.environ.setdefault("YOLO_CONFIG_DIR", str(TRAINING / ".ultralytics"))
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    try:
        if args.smoke:
            gpu_smoke()
        else:
            run(args.resume)
    except BaseException as error:
        state("failed", error=str(error), traceback=traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
