from pathlib import Path
import hashlib
import json
import os
import shutil
import sys

ROOT = Path('E:/AgriScan')
WORK = ROOT / '.runtime/detect-export'
WORK.mkdir(parents=True, exist_ok=True)
os.environ['YOLO_CONFIG_DIR'] = str(WORK / 'ultralytics')
os.environ['YOLO_AUTOINSTALL'] = 'false'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['ULTRALYTICS_OFFLINE'] = 'true'
sys.stdout.reconfigure(encoding='utf-8')

from ultralytics import YOLO
import onnx

source = ROOT / 'best.pt'
expected = 'fafc2bb3ce9ef66189436e0ad175bf07a8a0973d52cf6ece210f827798733be4'
assert hashlib.file_digest(source.open('rb'), 'sha256').hexdigest() == expected
target = ROOT / 'models/candidates/user-detect-fafc2bb3ce9e'
target.mkdir(parents=True, exist_ok=True)
checkpoint = target / 'best.pt'
if not checkpoint.exists():
    shutil.copyfile(source, checkpoint)
model = YOLO(str(checkpoint), task='detect')
assert model.task == 'detect' and len(model.names) == 38
# The 8.4.37 checkpoint predates the current _end2end runtime flag. Restore
# its trained one-to-one branch before the newer package fuses the model.
model.model.model[-1].end2end = True
print('TRUSTED_MODEL_NAMES', json.dumps(model.names, ensure_ascii=False), flush=True)
result = model.export(format='onnx', imgsz=640, batch=1, dynamic=False, simplify=False,
                      opset=17, device='cpu', half=False, nms=False, end2end=True)
exported = Path(result)
graph = onnx.load(str(exported), load_external_data=False)
def shape(value):
    return [dim.dim_value if dim.HasField('dim_value') else dim.dim_param for dim in value.type.tensor_type.shape.dim]
report = {'source_sha256': expected, 'task': model.task, 'classes': model.names,
          'onnx_path': str(exported), 'onnx_sha256': hashlib.file_digest(exported.open('rb'), 'sha256').hexdigest(),
          'inputs': [{'name': value.name, 'shape': shape(value)} for value in graph.graph.input],
          'outputs': [{'name': value.name, 'shape': shape(value)} for value in graph.graph.output]}
(target / 'export-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('EXPORT_REPORT', json.dumps(report, ensure_ascii=False), flush=True)
