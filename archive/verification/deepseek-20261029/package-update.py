import hashlib
import json
from pathlib import Path
import tarfile

root=Path.cwd()
folder=root/'.runtime/deepseek-20261029'
archive=folder/'llm-assistant-patch.tar.gz'
files={}
for source in (root/'backend/app').rglob('*.py'):
    if '__pycache__' not in source.parts:
        files[source.relative_to(root).as_posix()]=source
for source_dir,target in [('frontend','workspace'),('admin','admin')]:
    dist=root/source_dir/'dist'
    index=(dist/'index.html').read_text(encoding='utf-8')
    assert '/agriscan/'+target+'/assets/' in index
    files['public/'+target+'/index.html']=dist/'index.html'
    for source in (dist/'assets').rglob('*'):
        if source.is_file():
            files['public/'+target+'/assets/'+source.relative_to(dist/'assets').as_posix()]=source
assert 'backend/app/llm_probe.py' in files
manifest={name:hashlib.sha256(source.read_bytes()).hexdigest() for name,source in files.items()}
with tarfile.open(archive,'w:gz') as bundle:
    for name,source in sorted(files.items()):
        bundle.add(source,arcname=name,recursive=False)
report={'archive':str(archive),'bytes':archive.stat().st_size,
        'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':manifest}
(folder/'patch-manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({key:report[key] for key in ('archive','bytes','sha256')}))
