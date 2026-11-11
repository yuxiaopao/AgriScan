"""Real ONNX pipeline smoke and latency samples, not an accuracy benchmark."""
import hashlib,json,sys,time
from pathlib import Path
root=Path('E:/AgriScan')
sys.path.insert(0,str(root/'backend'))
from app.config import Settings
from app.inference import create_provider

settings=Settings(model_manifest=str(root/'models/candidates/user-detect-fafc2bb3ce9e/manifest.json'),
                  classification_model_manifest=str(root/'models/candidates/plantvillage-yolo26m/manifest.json'),
                  inference_threads=2)
started=time.perf_counter()
provider=create_provider(settings)
initialized=time.perf_counter()-started
assert provider.active['pipeline']=='detection_with_classification'
assert [p['task'] for p in provider.active['components']]==['detect','classify']
assert len(provider.mapping)==38
records=json.loads((root/'.runtime/detect-export/pt-results.json').read_text(encoding='utf-8'))
results=[]
for sample in records:
    path=Path(sample['path'])
    assert path.is_file()
    started=time.perf_counter()
    predicted=provider.predict(path)
    elapsed=time.perf_counter()-started
    evidence=predicted.model['verification']
    assert evidence['classification'] is not None
    assert evidence['status'] in {'agree','disagree','uncertain'}
    assert predicted.boxes
    assert evidence['model']['onnx_sha256']=='906cf72f6bf08854dab6e3bf2ba2be481928da122b8943f0e2a21f941fc930b7'
    assert evidence['scope']=='whole_image'
    if len(predicted.boxes)>1:assert evidence['status']=='uncertain'
    if evidence['status']!='agree':assert predicted.status=='attention'
    results.append({'sample':path.name,'sample_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'elapsed_seconds_local_cpu':round(elapsed,4),'crop':predicted.crop,
                    'detection':{'label':predicted.label,'confidence':predicted.confidence,'boxes':len(predicted.boxes)},
                    'classification':{'label':evidence['classification']['label'],'confidence':evidence['classification']['confidence']},
                    'verification':evidence['status'],'message':evidence['message']})
report={'status':'passed','scope':'Five technical smoke images, not an independent accuracy evaluation.',
        'load_seconds':round(initialized,4),'components':provider.active['components'],'results':results}
folder=root/'.runtime/dual-model-20261029'
(folder/'real-model-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=True))
