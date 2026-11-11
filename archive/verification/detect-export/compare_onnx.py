from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
from time import perf_counter

ROOT = Path('E:/AgriScan')
sys.path.insert(0, str(ROOT / 'backend'))
from app.detection_inference import OnnxDetectionProvider

folder = ROOT / 'models/candidates/user-detect-fafc2bb3ce9e'
shutil.copyfile(folder / 'best.onnx', folder / 'model.onnx')
manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
manifest['onnx_sha256'] = hashlib.file_digest((folder / 'model.onnx').open('rb'), 'sha256').hexdigest()
manifest['compatibility'] = {'checkpoint_ultralytics': '8.4.37', 'export_ultralytics': '8.4.183',
                             'export_head': 'one2one', 'end2end_explicitly_restored_before_fusion': True}
manifest['validation_passed'] = False
(folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
private = ROOT / '.runtime/detect-export/parity'
private.mkdir(exist_ok=True)
target = private / 'model.onnx'
if target.exists():
    target.unlink()
os.link(folder / 'model.onnx', target)
temporary_manifest = {**manifest, 'validation_passed': True}
(private / 'manifest.json').write_text(json.dumps(temporary_manifest), encoding='utf-8')
provider = OnnxDetectionProvider(private / 'manifest.json', threads=2)

def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return intersection / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection)

results = []
for sample in json.loads((ROOT / '.runtime/detect-export/pt-results.json').read_text(encoding='utf-8')):
    started = perf_counter()
    result = provider.predict(Path(sample['path']))
    elapsed = perf_counter() - started
    assert len(result.boxes) == len(sample['boxes']), (sample['path'], len(result.boxes), len(sample['boxes']))
    remaining = set(range(len(result.boxes)))
    matches = []
    for expected in sample['boxes']:
        candidates = [i for i in remaining if result.boxes[i]['class_id'] == expected['class_id']]
        assert candidates, (sample['path'], expected, result.boxes)
        index = max(candidates, key=lambda i: iou(expected['bbox'], result.boxes[i]['bbox']))
        actual = result.boxes[index]
        overlap = iou(expected['bbox'], actual['bbox'])
        score_difference = abs(expected['confidence'] - actual['confidence'])
        edge_difference = max(abs(a - b) for a, b in zip(expected['bbox'], actual['bbox']))
        assert overlap > 0.98 and score_difference < 0.005 and edge_difference < 0.005, (overlap, score_difference, edge_difference)
        remaining.remove(index)
        matches.append({'class_id': expected['class_id'], 'label': actual['label'], 'iou': overlap,
                        'confidence_difference': score_difference, 'maximum_normalized_edge_difference': edge_difference})
    results.append({'sample': sample['path'], 'image_shape': sample['image_shape'], 'box_count': len(result.boxes),
                    'result': result.label, 'inference_seconds_local_cpu': elapsed, 'matches': matches})
report = {'passed': True, 'scope': 'Five technical parity smoke images, including one non-square image; not independent detection accuracy evaluation.',
          'source_sha256': manifest['source_weights_sha256'], 'onnx_sha256': manifest['onnx_sha256'], 'results': results}
(folder / 'parity-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
manifest['validation_passed'] = True
(folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
