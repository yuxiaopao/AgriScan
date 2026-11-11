from pathlib import Path
import hashlib,json,tarfile
folder=Path('.runtime/dual-model-20261029')
folder.mkdir(exist_ok=True)
source=Path('models/candidates/plantvillage-yolo26m')
metadata=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
assert metadata['validation_passed'] and metadata['task']=='classify'
assert hashlib.sha256((source/'model.onnx').read_bytes()).hexdigest()==metadata['onnx_sha256']
archive=folder/'classification-model.tar.gz'
with tarfile.open(archive,'w:gz') as bundle:
    for name in ('model.onnx','manifest.json'):bundle.add(source/name,arcname='model-classification/'+name,recursive=False)
report={'archive':str(archive),'bytes':archive.stat().st_size,
        'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
        'model_onnx_sha256':metadata['onnx_sha256'],'class_count':len(metadata['classes'])}
(folder/'classification-package.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
