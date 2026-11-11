"""Freeze complete verified sources; transfer only the necessary application delta."""
from datetime import datetime,timezone,timedelta
import ast,hashlib,json,subprocess,tarfile
from pathlib import Path

folder=Path('.runtime/dual-model-20261029')
web=json.loads((folder/'web-ui-builds.json').read_text(encoding='utf-8'))
mobile=json.loads(Path('.runtime/mobile-cancel-final-20261029/final-mobile-ready.json').read_text(encoding='utf-8'))
apk=json.loads(Path('.runtime/mobile-cancel-final-20261029/apk/verification.json').read_text(encoding='utf-8'))
assert web['status']==mobile['status']==apk['status']=='passed'
assert web.get('auth_email_features') is True
assert web.get('completed_result_view') is True,'Wait for the final result-view build, not the earlier dual-model-only build.'
assert web.get('background_detection_tasks') is True and web.get('release_version')=='1.0.4'
sources={}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
for name,record in web['sources'].items():
    assert sha(Path(name))==record['sha256'],name
    sources[name]=record['sha256']
for name,record in mobile['source_files'].items():
    path=Path(name)
    assert sha(path)==record['sha256'],str(path)
    sources[path.as_posix()]=record['sha256']
files={}
for path in Path('backend/app').rglob('*'):
    if path.is_file() and '__pycache__' not in path.parts and path.suffix in {'.py','.json'}:
        if path.suffix=='.py':ast.parse(path.read_text(encoding='utf-8'))
        files[path.as_posix()]=path
        sources[path.as_posix()]=sha(path)
for path in [Path('backend/.env.example'),*Path('backend/tests').glob('*.py'),*Path('backend').glob('requirements*.txt')]:
    sources[path.as_posix()]=sha(path)
for surface,public in [('frontend','workspace'),('admin','admin')]:
    dist=Path(web['surfaces'][surface]['dist'])
    expected=web['surfaces'][surface]['files']
    assert {p.relative_to(dist).as_posix() for p in dist.rglob('*') if p.is_file()}==set(expected)
    for name,record in expected.items():
        path=dist/name
        assert sha(path)==record['sha256'],name
        files['public/'+public+'/'+name]=path
website=Path('.runtime/server-latest-20261029/website')
for path in website.rglob('*'):
    if path.is_file():
        name=path.relative_to(website).as_posix()
        source=Path('website')/name
        assert sha(source)==sha(path),name
        sources[source.as_posix()]=sha(source)
        files['public/'+name]=path
for name in ('agriscan-test.apk','agriscan-test.apk.sha256','release.json'):
    path=Path('website/downloads')/name
    files['public/downloads/'+name]=path
assert sha(files['public/downloads/agriscan-test.apk'])==apk['sha256']
release=json.loads(files['public/downloads/release.json'].read_text(encoding='utf-8'))
assert release['version']=='1.0.4' and release['version_code']==5 and release['sha256']==apk['sha256']
classifier=Path('models/candidates/plantvillage-yolo26m')
for name in ('model.onnx','manifest.json'):
    files['model-classification/'+name]=classifier/name
    sources[(classifier/name).as_posix()]=sha(classifier/name)
assert sha(classifier/'model.onnx')=='906cf72f6bf08854dab6e3bf2ba2be481928da122b8943f0e2a21f941fc930b7'
stamp=datetime.now(timezone(timedelta(hours=8)))
fingerprint=hashlib.sha256('\n'.join(name+':'+digest for name,digest in sorted(sources.items())).encode()).hexdigest()
info={'release_id':'release-'+stamp.strftime('%Y%m%d-dual-model-%H%M%S'),
      'version':'1.0.4','prepared_at':stamp.isoformat(),
      'parent_release':'/srv/agriscan/releases/release-20261029-dual-model-184401',
      'source_tree_sha256':fingerprint,'source_file_count':len(sources),'sources':sources,
      'base_commit':subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),
      'includes_completed_working_tree_ui':True,'database_migration_required':False,
      'workspace_entries':web['surfaces']['frontend']['entries'],'admin_entries':web['surfaces']['admin']['entries'],
      'completed_result_view':True,
      'pipeline':{'name':'detection_with_classification',
                  'detection_onnx_sha256':'ff623c94555ade8c08a425caee3fe6fba5465ebc61ebd81ee502376bca8d4773',
                  'classification_onnx_sha256':'906cf72f6bf08854dab6e3bf2ba2be481928da122b8943f0e2a21f941fc930b7'},
      'apk':{k:apk[k] for k in ('version','version_code','apk_bytes','sha256','signer_sha256')}}
(folder/'release-info.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
files['release-info.json']=folder/'release-info.json'
manifest={name:sha(path) for name,path in files.items()}
(folder/'payload-files.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
previous=json.loads(Path('.runtime/server-latest-20261029/payload-files.json').read_text(encoding='utf-8'))
external={'public/downloads/agriscan-test.apk','model-classification/model.onnx','model-classification/manifest.json'}
changed={name:path for name,path in files.items() if name not in external and
         (previous.get(name)!=manifest[name] or name.startswith('backend/app/'))}
changed['payload-files.json']=folder/'payload-files.json'
archive=folder/'dual-model-update.tar.gz'
with tarfile.open(archive,'w:gz') as bundle:
    for name,path in sorted(changed.items()):
        assert name.startswith(('backend/app/','public/')) or name in ('release-info.json','payload-files.json')
        assert not any(part in name.split('/') for part in ('.env','node_modules','.runtime','__pycache__'))
        bundle.add(path,arcname=name,recursive=False)
report={'status':'packaged','archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive),
        'release_id':info['release_id'],'source_tree_sha256':fingerprint,'source_file_count':len(sources),
        'payload_files':len(manifest),'transferred_files':len(changed),
        'payload_manifest_sha256':sha(folder/'payload-files.json')}
(folder/'package.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
