"""Detection remains primary; an independent whole-image classifier verifies it."""
from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
from threading import BoundedSemaphore

from fastapi import HTTPException


def validated_mapping(detection_labels, classification_labels, mapping):
    detection = {entry['key']: entry for entry in detection_labels}
    classification = {entry['key']: entry for entry in classification_labels}
    if (not isinstance(mapping, dict) or not mapping
            or any(not isinstance(key, str) or not isinstance(value, str) for key, value in mapping.items())
            or len(detection) != len(detection_labels) or len(classification) != len(classification_labels)
            or set(detection) != set(mapping) or set(classification) != set(mapping.values())
            or len(set(mapping.values())) != len(mapping)):
        raise ValueError('The explicit verification map must cover every class on both models exactly once')
    for key, canonical in mapping.items():
        left, right = detection[key], classification[canonical]
        if left['crop'] != right['crop'] or left['healthy'] is not right['healthy']:
            raise ValueError('Verification class mapping disagrees on crop or healthy status')
    return detection, classification


class DetectionWithClassificationProvider:
    status = 'ready'

    def __init__(self, detection, classification, mapping=None):
        if (not isinstance(detection.active, dict) or not isinstance(classification.active, dict)
                or detection.active.get('task') != 'detect' or classification.active.get('task') != 'classify'
                or detection.status != 'ready' or classification.status != 'ready'):
            raise ValueError('A ready detector and classifier are required for independent verification')
        if mapping is None:
            mapping = json.loads(Path(__file__).with_name('class_verification_mapping.json').read_text(encoding='utf-8'))
        self.detection_labels, self.classification_labels = validated_mapping(detection.labels, classification.labels, mapping)
        self.mapping = dict(mapping)
        self.detection, self.classification = detection, classification
        self.supported_crops = list(detection.supported_crops)
        self.guard = BoundedSemaphore(1)
        self.active = {**deepcopy(detection.active), 'pipeline': 'detection_with_classification',
                       'components': [{**deepcopy(detection.active), 'role': 'detection', 'status': 'ready'},
                                      {**deepcopy(classification.active), 'role': 'verification', 'status': 'ready'}]}

    def predict(self, image_path: Path, crop: str | None = None):
        if not self.guard.acquire(blocking=False):
            raise HTTPException(503, '双模型正在处理另一张图片，请稍后重试。')
        try:
            detected = self.detection.predict(image_path, crop)
            if not detected.boxes or detected.key not in self.detection_labels:
                raise HTTPException(503, '检测结果缺少可靠的主目标类别，请检查模型服务。')
            metadata = self.detection_labels[detected.key]
            verification = {
                'status': 'unavailable', 'scope': 'whole_image',
                'message': '独立分类复核暂不可用，已保留检测结果，请稍后重试或人工复核。',
                'model': {name: self.classification.active[name] for name in ('name', 'task', 'onnx_sha256')},
                'detection': {name: metadata[name] for name in ('key', 'crop', 'label', 'healthy')},
                'classification': None,
            }
            verification['detection']['confidence'] = detected.confidence
            try:
                # Always send the same entire saved image without a crop hint.
                # This is not a per-box second opinion or score fusion.
                classified = self.classification.predict(image_path, None)
                top = classified.candidates[0]
                key = top['key']
                candidate = self.classification_labels[key]
                confidence = top['confidence']
                if (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                        or not math.isfinite(confidence) or not 0 <= confidence <= 1):
                    raise ValueError('Invalid classification score')
                classification = {name: candidate[name] for name in ('key', 'crop', 'label', 'healthy')}
                classification.update(confidence=confidence, candidates=deepcopy(classified.candidates))
                verification['classification'] = classification
                if len(detected.boxes) > 1 or confidence < self.classification.threshold:
                    reasons = []
                    if len(detected.boxes) > 1:
                        reasons.append('检测到多个目标；整图分类不能逐框复核或证明各框一致')
                    if confidence < self.classification.threshold:
                        reasons.append('整图分类分数低于复核阈值')
                    verification.update(status='uncertain', message='；'.join(reasons) + '，请逐叶复拍并人工复核。')
                elif self.mapping[detected.key] == key:
                    verification.update(status='agree', message='整图分类与主检测类别一致；两模型分数独立，仍需结合现场确认。')
                else:
                    verification.update(status='disagree', message='整图分类与主检测类别不一致，保留原检测结论，请复拍并人工复核。')
            except Exception:
                # A classifier failure never discards valid detector boxes, and
                # raw exceptions, local paths and provider details stay private.
                verification['classification'] = None
            model = {**(detected.model or {}), 'pipeline': 'detection_with_classification', 'verification': verification}
            return replace(detected, status=detected.status if verification['status'] == 'agree' else 'attention', model=model)
        finally:
            self.guard.release()
