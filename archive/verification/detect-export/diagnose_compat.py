from pathlib import Path
import hashlib
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
import torch
import ultralytics

torch.set_num_threads(2)
path = ROOT / 'best.pt'
before = hashlib.sha256(path.read_bytes()).hexdigest()
# The human supplied and expressly authorized this checkpoint for isolated loading.
checkpoint = torch.load(path, map_location='cpu', weights_only=False)
model = checkpoint.get('ema')
if model is None:
    model = checkpoint['model']
model = model.float().eval()
head = model.model[-1]
args = checkpoint.get('train_args') or {}
report = {
    'checkpoint_sha256_before': before,
    'checkpoint_version': checkpoint.get('version'),
    'epoch': checkpoint.get('epoch'),
    'current_ultralytics': ultralytics.__version__,
    'torch': torch.__version__,
    'train_args': {key: args.get(key) for key in ('task', 'model', 'imgsz', 'end2end')},
    'head': type(head).__name__,
    'nc': head.nc,
    'reg_max': head.reg_max,
    'state_has_end2end': 'end2end' in head.__dict__,
    'state_has_private_end2end': '_end2end' in head.__dict__,
    'has_one2one_cv2': head.one2one_cv2 is not None,
    'has_one2one_cv3': head.one2one_cv3 is not None,
    'default_current_end2end': head.end2end,
    'old_version_getter_equivalent': getattr(head, '_end2end', True) and hasattr(head, 'one2one'),
    'blank_inputs': [],
}
with torch.inference_mode():
    for size in (320, 640):
        head.end2end = False
        decoded, raw = model(torch.zeros(1, 3, size, size))
        item = {'size': size, 'default_decoded_shape': list(decoded.shape), 'branches': {}}
        for branch in ('one2many', 'one2one'):
            data = raw[branch]
            probabilities = data['scores'].sigmoid()
            decoded_branch = head._inference(data)
            final = head.postprocess(decoded_branch.permute(0, 2, 1))
            item['branches'][branch] = {
                'logit_min': float(data['scores'].min()),
                'logit_max': float(data['scores'].max()),
                'max_score': float(probabilities.max()),
                'scores_exactly_one': int((probabilities == 1).sum()),
                'scores_total': probabilities.numel(),
                'topk_over_025': int((final[..., 4] >= 0.25).sum()),
                'topk_exactly_one': int((final[..., 4] == 1).sum()),
                'all_finite': bool(torch.isfinite(decoded_branch).all()),
            }
        report['blank_inputs'].append(item)
    head.end2end = True
    report['explicit_true_before_fuse'] = head.end2end
    head.fuse()
    report['after_true_head_fuse'] = {
        'end2end': head.end2end,
        'one2many_removed': head.cv2 is None and head.cv3 is None,
        'one2one_retained': head.one2one_cv2 is not None and head.one2one_cv3 is not None,
    }
report['checkpoint_sha256_after'] = hashlib.sha256(path.read_bytes()).hexdigest()
report['original_unchanged'] = report['checkpoint_sha256_before'] == report['checkpoint_sha256_after']
(WORK / 'compat-diagnosis.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
