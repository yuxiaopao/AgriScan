"""Validated YOLO26 end-to-end boxes; coordinates refer to the saved original image."""
import hashlib
import json
from pathlib import Path
from threading import BoundedSemaphore

from fastapi import HTTPException
import numpy as np
from PIL import Image

from .inference import InferenceResult, SUPPORTED_CROPS


def prepare_detection_image(image, image_size):
    import cv2
    image = image.convert('RGB')
    width, height = image.size
    ratio = min(image_size / width, image_size / height)
    new_width, new_height = round(width * ratio), round(height * ratio)
    left = round((image_size - new_width) / 2 - 0.1)
    top = round((image_size - new_height) / 2 - 0.1)
    resized = cv2.resize(np.asarray(image), (new_width, new_height), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((image_size, image_size, 3), 114, dtype=np.uint8)
    canvas[top:top + new_height, left:left + new_width] = resized
    tensor = np.ascontiguousarray(canvas.transpose(2, 0, 1)[None], dtype=np.float32) / 255
    return tensor, (width, height, ratio, left, top)


class OnnxDetectionProvider:
    status = 'ready'

    def __init__(self, manifest_path, threads=2):
        import onnxruntime as ort
        path = Path(manifest_path).resolve(strict=True)
        metadata = json.loads(path.read_text(encoding='utf-8'))
        if (metadata.get('task') != 'detect' or metadata.get('validation_passed') is not True
                or metadata.get('output_format') != 'end2end_xyxy_score_class'
                or metadata.get('preprocessing') != 'letterbox-rgb-div255'
                or metadata.get('coordinate_space') != 'normalized_xyxy'):
            raise ValueError('A validated YOLO26 detection manifest is required')
        self.labels = metadata['classes']
        if (not self.labels or len({item['key'] for item in self.labels}) != len(self.labels)
                or any(item['crop'] not in SUPPORTED_CROPS or not isinstance(item['healthy'], bool)
                       or not isinstance(item['label'], str) for item in self.labels)):
            raise ValueError('Invalid detection class metadata')
        class_checksum = hashlib.sha256(json.dumps(self.labels, sort_keys=True, ensure_ascii=False,
                                                   separators=(',', ':')).encode()).hexdigest()
        if class_checksum != metadata.get('metadata_sha256'):
            raise ValueError('Detection class metadata SHA256 does not match')
        self.image_size = int(metadata['image_size'])
        self.threshold = float(metadata['threshold'])
        self.max_detections = int(metadata.get('max_detections', 100))
        if (not 32 <= self.image_size <= 1280 or self.image_size % 32
                or not 0 < self.threshold <= 1 or not 1 <= self.max_detections <= 300):
            raise ValueError('Invalid detection image size, threshold or count limit')
        model_path = path.with_name('model.onnx')
        with model_path.open('rb') as model_file:
            checksum = hashlib.file_digest(model_file, 'sha256').hexdigest()
        if checksum != metadata['onnx_sha256']:
            raise ValueError('Detection ONNX SHA256 does not match its manifest')
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model_path), sess_options=options, providers=['CPUExecutionProvider'])
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if (len(inputs) != 1 or len(outputs) != 1 or inputs[0].type != 'tensor(float)'
                or inputs[0].shape != [1, 3, self.image_size, self.image_size]
                or len(outputs[0].shape) != 3 or outputs[0].shape[0] != 1 or outputs[0].shape[2] != 6
                or not isinstance(outputs[0].shape[1], int) or not 1 <= outputs[0].shape[1] <= 300):
            raise ValueError('Unsupported detection ONNX input/output contract')
        self.input_name = inputs[0].name
        self.output_count = outputs[0].shape[1]
        self.guard = BoundedSemaphore(1)
        self.supported_crops = sorted({item['crop'] for item in self.labels})
        self.active = {'name': metadata['name'], 'task': 'detect', 'image_size': self.image_size,
                       'threshold': self.threshold, 'class_count': len(self.labels), 'onnx_sha256': checksum,
                       'test_top1': None, 'test_macro_f1': None, 'coordinate_space': 'normalized_xyxy',
                       'score_semantics': 'independent_detection_confidence',
                       'scope': '真实检测目标矩形框；不代表病斑精确边界或面积，未提供独立检测集 mAP。'}

    def boxes_from_output(self, output, geometry):
        if (output.shape != (1, self.output_count, 6) or not np.all(np.isfinite(output))
                or np.any(output[..., 4] < 0) or np.any(output[..., 4] > 1)):
            raise ValueError('Invalid detection output')
        width, height, ratio, left, top = geometry
        boxes = []
        for raw in output[0][np.argsort(-output[0, :, 4], kind='stable')]:
            x1, y1, x2, y2, confidence, class_value = map(float, raw)
            if confidence < self.threshold:
                continue
            class_id = round(class_value)
            if abs(class_value - class_id) > 0.0001 or not 0 <= class_id < len(self.labels):
                raise ValueError('Invalid detection class index')
            if x2 <= x1 or y2 <= y1:
                raise ValueError('Invalid detection rectangle')
            original = [max(0, min(width, (x1 - left) / ratio)) / width,
                        max(0, min(height, (y1 - top) / ratio)) / height,
                        max(0, min(width, (x2 - left) / ratio)) / width,
                        max(0, min(height, (y2 - top) / ratio)) / height]
            if original[2] <= original[0] or original[3] <= original[1]:
                continue  # A prediction entirely inside the letterbox padding is not an image target.
            boxes.append({**self.labels[class_id], 'class_id': class_id, 'confidence': confidence, 'bbox': original})
            if len(boxes) == self.max_detections:
                break
        return boxes

    def predict(self, image_path: Path, crop: str | None = None):
        if crop and crop not in self.supported_crops:
            raise HTTPException(422, f'当前检测模型未覆盖{crop}。')
        if not self.guard.acquire(blocking=False):
            raise HTTPException(503, '模型正在处理另一张图片，请稍后重试。')
        try:
            with Image.open(image_path) as image:
                tensor, geometry = prepare_detection_image(image, self.image_size)
            output = self.session.run(None, {self.input_name: tensor})[0]
            boxes = self.boxes_from_output(output, geometry)
            if not boxes:
                raise HTTPException(422, '未检测到可靠的叶片目标，请靠近叶片、改善光线后重新拍摄。')
            if crop and any(box['crop'] != crop for box in boxes):
                raise HTTPException(422, f'检测目标包含与所选{crop}不一致的作物，请核对照片或取消作物限制。')
            primary_crop = boxes[0]['crop']
            primary = next((box for box in boxes if box['crop'] == primary_crop and not box['healthy']), boxes[0])
            unique = {}
            for box in boxes:
                if box['key'] not in unique:
                    unique[box['key']] = {key: value for key, value in box.items() if key not in {'bbox', 'class_id'}}
            model = {key: self.active[key] for key in ('name', 'task', 'onnx_sha256', 'coordinate_space', 'score_semantics')}
            model['multiple_crops'] = len({box['crop'] for box in boxes}) > 1
            return InferenceResult('attention' if any(not box['healthy'] for box in boxes) else 'healthy',
                                   primary['label'], primary['confidence'], list(unique.values())[:5], model,
                                   primary_crop, boxes)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, '目标检测推理失败，请检查模型或稍后重试。') from None
        finally:
            self.guard.release()
