import hashlib
import json
from pathlib import Path
import tarfile

folder=Path('.runtime/isolation-20261029')
build=json.loads((folder/'ui-builds.json').read_text(encoding='utf-8'))
assert build['status']=='passed' and build['unknown_design_imports_excluded']
sources={}
for name in ('app','alembic'):
    for source in (Path('backend')/name).rglob('*.py'):
        if '__pycache__' not in source.parts:
            sources[source.as_posix()]=source
sources['backend/alembic.ini']=Path('backend/alembic.ini')
for surface,public in [('frontend','workspace'),('admin','admin')]:
    dist=folder/'build'/surface/'dist'
    for relative,metadata in build['surfaces'][surface]['files'].items():
        source=dist/relative
        assert hashlib.sha256(source.read_bytes()).hexdigest()==metadata['sha256']
        sources['public/'+public+'/'+relative]=source
archive=folder/'user-isolation-patch.tar.gz'
with tarfile.open(archive,'w:gz') as bundle:
    for name,source in sorted(sources.items()):
        bundle.add(source,arcname=name,recursive=False)
report={'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'archive':str(archive),
        'bytes':archive.stat().st_size,'files':{name:hashlib.sha256(source.read_bytes()).hexdigest() for name,source in sources.items()}}
(folder/'patch-manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({key:report[key] for key in ('sha256','archive','bytes')}))
