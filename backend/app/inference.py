"""Validated ONNX providers and inference snapshots; uploaded pickle stays inert."""
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from threading import BoundedSemaphore
from typing import Protocol

from fastapi import HTTPException
from PIL import Image

from .image_preprocessing import prepare_image

CROP_COLORS = json.loads(Path(__file__).with_name("crops.json").read_text(encoding="utf-8"))
SUPPORTED_CROPS = list(CROP_COLORS)


@dataclass(frozen=True)
class InferenceResult:
    status: str
    label: str | None
    confidence: float | None
    candidates: list[dict] = field(default_factory=list)
    model: dict | None = None
    crop: str | None = None
    boxes: list[dict] = field(default_factory=list)
    key: str | None = None


def prediction_snapshot(result):
    if not result.model:
        return None
    return {**result.model, **({'boxes': result.boxes} if result.boxes else {})}


def public_prediction_model(model):
    return {key: value for key, value in model.items() if key != 'boxes'} if model else None


class InferenceProvider(Protocol):
    status: str
    active: dict | None
    supported_crops: list[str]

    def predict(self, image_path: Path, crop: str | None = None) -> InferenceResult:
        ...


class AwaitingWeightsProvider:
    status = "awaiting_weights"
    active = None
    supported_crops = []

    def predict(self, image_path: Path, crop: str | None = None) -> InferenceResult:
        if not crop:
            raise HTTPException(422, "尚未启用作物识别模型，无法自动识别。请选择作物以保存待检测样本。")
        return InferenceResult(status="awaiting_model", label=None, confidence=None, crop=crop)


class OnnxClassificationProvider:
    status = "ready"

    def __init__(self, manifest_path, threads=2):
        import onnxruntime as ort
        manifest_path = Path(manifest_path).resolve(strict=True)
        metadata = json.loads(manifest_path.read_text(encoding="utf-8"))
        if metadata.get("task") != "classify" or metadata.get("validation_passed") is not True:
            raise ValueError("Model manifest must contain a validated classification model")
        labels = metadata["classes"]
        if not labels or len({entry["key"] for entry in labels}) != len(labels):
            raise ValueError("Invalid or duplicate model labels")
        if any(entry["crop"] not in SUPPORTED_CROPS or not isinstance(entry["healthy"], bool)
               or not isinstance(entry["label"], str) for entry in labels):
            raise ValueError("Invalid model class metadata")
        self.threshold = float(metadata["threshold"])
        self.image_size = int(metadata["image_size"])
        if not 0 < self.threshold <= 1 or not 32 <= self.image_size <= 1024:
            raise ValueError("Invalid model confidence threshold or image size")
        expected_transform = metadata.get("preprocessing")
        if expected_transform != "resize-shortest-bilinear-center-crop-rgb-div255":
            raise ValueError("Unsupported preprocessing contract")
        model_path = manifest_path.with_name("model.onnx")
        with model_path.open("rb") as model_file:
            actual_sha = hashlib.file_digest(model_file, "sha256").hexdigest()
        if actual_sha != metadata["onnx_sha256"]:
            raise ValueError("ONNX SHA256 does not match the validated manifest")
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(str(model_path), sess_options=options,
                                           providers=["CPUExecutionProvider"])
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if len(inputs) != 1 or len(outputs) != 1 or inputs[0].type != "tensor(float)":
            raise ValueError("Unsupported ONNX inputs/outputs")
        shape = inputs[0].shape
        if len(shape) != 4 or shape[1] != 3 or any(
            isinstance(dimension, int) and dimension != self.image_size for dimension in shape[2:]
        ):
            raise ValueError("ONNX input shape does not match the manifest")
        if outputs[0].shape[-1] != len(labels):
            raise ValueError("ONNX output size does not match the class list")
        self.input_name = inputs[0].name
        self.labels = labels
        self.supported_crops = sorted({entry["crop"] for entry in labels})
        self.guard = BoundedSemaphore(1)
        self.active = {key: metadata[key] for key in (
            "name", "task", "image_size", "threshold", "test_top1", "test_macro_f1", "onnx_sha256")}
        self.active["class_count"] = len(labels)
        self.active["scope"] = "单叶图像分类；不输出病斑位置框，田间泛化尚需独立验证。"

    def predict(self, image_path: Path, crop: str | None = None) -> InferenceResult:
        import numpy as np
        if crop and crop not in self.supported_crops:
            raise HTTPException(422, f"当前模型未覆盖{crop}，请选择模型支持的作物。")
        if not self.guard.acquire(blocking=False):
            raise HTTPException(503, "模型正在处理另一张图片，请稍后重试。")
        try:
            with Image.open(image_path) as image:
                tensor = prepare_image(image, self.image_size)
            probabilities = self.session.run(None, {self.input_name: tensor})[0][0]
            if (probabilities.shape != (len(self.labels),) or not np.all(np.isfinite(probabilities))
                    or np.any(probabilities < 0) or np.any(probabilities > 1)
                    or not np.isclose(probabilities.sum(), 1, atol=0.001)):
                raise ValueError("Model output is not a finite probability vector")
            index = int(np.argmax(probabilities))
            confidence = float(probabilities[index])
            label = self.labels[index]
            # Preserve the global probability vector's scores: never renormalize
            # candidates by the user's crop or treat softmax scores as multilabel.
            candidates = [
                {**self.labels[int(i)], "confidence": float(probabilities[i])}
                for i in np.argsort(-probabilities, kind="stable")[:5]
            ]
            model = {key: self.active[key] for key in ("name", "task", "onnx_sha256")}
            if confidence < self.threshold:
                return InferenceResult("attention", f"置信度不足，请人工复核（候选：{label['label']}）",
                                       confidence, candidates, model, label["crop"], key=label['key'])
            if crop and label["crop"] != crop:
                raise HTTPException(422, f"图片更接近{label['crop']}，与所选{crop}不一致，请核对作物和照片。")
            return InferenceResult("healthy" if label["healthy"] else "attention",
                                   label["label"], confidence, candidates, model, label["crop"], key=label['key'])
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "模型推理失败，请检查模型服务或稍后重试。")
        finally:
            self.guard.release()


def create_provider(settings):
    if not settings.model_manifest:
        if settings.classification_model_manifest:
            raise ValueError('Independent classification verification requires a primary detection manifest')
        return AwaitingWeightsProvider()
    metadata = json.loads(Path(settings.model_manifest).read_text(encoding='utf-8'))
    if metadata.get('task') == 'detect':
        from .detection_inference import OnnxDetectionProvider
        detector = OnnxDetectionProvider(settings.model_manifest, settings.inference_threads)
        if settings.classification_model_manifest:
            from .combined_inference import DetectionWithClassificationProvider
            classifier = OnnxClassificationProvider(settings.classification_model_manifest, settings.inference_threads)
            return DetectionWithClassificationProvider(detector, classifier)
        return detector
    if settings.classification_model_manifest:
        raise ValueError('Independent classification verification requires a primary detection model')
    return OnnxClassificationProvider(settings.model_manifest, settings.inference_threads)
