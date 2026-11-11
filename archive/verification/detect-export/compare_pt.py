from pathlib import Path
import json
import os
import sys

ROOT = Path('E:/AgriScan')
WORK = ROOT / '.runtime/detect-export'
os.environ['YOLO_CONFIG_DIR'] = str(WORK / 'ultralytics')
os.environ['YOLO_AUTOINSTALL'] = 'false'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['ULTRALYTICS_OFFLINE'] = 'true'
sys.stdout.reconfigure(encoding='utf-8')
from ultralytics import YOLO
from PIL import Image

model = YOLO(str(ROOT / 'best.pt'), task='detect')
model.model.model[-1].end2end = True
groups = ['Apple___Apple_scab', 'Corn_(maize)___Common_rust_', 'Tomato___Early_blight', 'Tomato___healthy']
paths = [next((ROOT / 'datasets/plantvillage/classification/test' / group).glob('*')) for group in groups]
with Image.open(paths[-1]) as image:
    image = image.convert('RGB')
    canvas = Image.new('RGB', (image.width * 2, image.height), (114, 114, 114))
    canvas.paste(image, (image.width // 2, 0))
    nonsquare = WORK / 'nonsquare-leaf.jpg'
    canvas.save(nonsquare, quality=95)
    paths.append(nonsquare)
samples = []
for path in paths:
    result = model.predict(str(path), imgsz=640, rect=False, conf=0.25, max_det=100,
                           device='cpu', verbose=False, save=False, end2end=True)[0]
    boxes = [{'class_id': int(box.cls.item()), 'confidence': float(box.conf.item()),
              'bbox': box.xyxyn[0].tolist()} for box in result.boxes]
    samples.append({'path': str(path), 'image_shape': result.orig_shape, 'boxes': boxes})
    print(path.name, len(boxes), 'PT targets', flush=True)
(WORK / 'pt-results.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding='utf-8')
