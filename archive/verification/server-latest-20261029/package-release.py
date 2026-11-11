"""Package the verified latest complete UI and APK, not stale root dist output."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile

folder=Path('.runtime/server-latest-20261029')
web=json.loads((folder/'web-ready.json').read_text(encoding='utf-8'))
mobile=json.loads((folder/'mobile-source-manifest.json').read_text(encoding='utf-8'))
apk=json.loads((folder/'apk/verification.json').read_text(encoding='utf-8'))
assert web['status']=='passed' and web['source_unchanged_during_build'] and apk['status']=='passed'
assert apk['version']=='1.0.3' and apk['version_code']==4 and apk['source_root_stable_after_build']
sources={}
for name,record in web['source_files'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==record['sha256'],name
    sources[name]=record['sha256']
for record in mobile['files']:
    name='mobile/'+record['path']
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==record['sha256'],name
    sources[name]=record['sha256']
files={}
for surface,public in [('frontend','workspace'),('admin','admin')]:
    dist=folder/surface/'dist'
    assert {p.relative_to(dist).as_posix() for p in dist.rglob('*') if p.is_file()}==set(web['builds'][surface]['files'])
    for name,record in web['builds'][surface]['files'].items():
        assert hashlib.sha256((dist/name).read_bytes()).hexdigest()==record['sha256'],name
    for source in dist.rglob('*'):
        if source.is_file():
            files['public/'+public+'/'+source.relative_to(dist).as_posix()]=source
for source in (folder/'website').rglob('*'):
    if source.is_file():
        relative=source.relative_to(folder/'website').as_posix()
        assert not relative.startswith('downloads/')
        files['public/'+relative]=source
assert {p.relative_to(folder/'website').as_posix() for p in (folder/'website').rglob('*') if p.is_file()}==set(web['website']['files'])
for name,record in web['website']['files'].items():
    assert hashlib.sha256((folder/'website'/name).read_bytes()).hexdigest()==record['sha256'],name
release=json.loads(Path('website/downloads/release.json').read_text(encoding='utf-8'))
assert release['version']=='1.0.3' and release['sha256']==apk['sha256']
assert hashlib.sha256(Path('website/downloads/agriscan-test.apk').read_bytes()).hexdigest()==apk['sha256']
for name in ('agriscan-test.apk','agriscan-test.apk.sha256','release.json'):
    files['public/downloads/'+name]=Path('website/downloads')/name
files['ops/agriscan-locations.inc']=Path('deploy/agriscan-locations.inc')
stamp=datetime.now(timezone(timedelta(hours=8)))
fingerprint=hashlib.sha256('\n'.join(name+':'+digest for name,digest in sorted(sources.items())).encode()).hexdigest()
metadata={'release_id':'release-'+stamp.strftime('%Y%m%d-full-ui-%H%M%S'),
          'version':'1.0.3','prepared_at':stamp.isoformat(),'source_tree_sha256':fingerprint,
          'source_file_count':len(sources),'base_commit':subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(),
          'includes_completed_working_tree_ui':True,'backend_unchanged':True,'database_migration_required':False,
          'workspace_entries':web['builds']['frontend']['entries'],
          'admin_entries':web['builds']['admin']['entries'],
          'apk':{key:apk[key] for key in ('version','version_code','apk_bytes','sha256','signer_sha256')},
          'sources':sources}
(folder/'release-info.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
files['release-info.json']=folder/'release-info.json'
manifest={name:hashlib.sha256(source.read_bytes()).hexdigest() for name,source in files.items()}
(folder/'payload-files.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
files['payload-files.json']=folder/'payload-files.json'
archive=folder/'latest-full-ui.tar.gz'
with tarfile.open(archive,'w:gz') as bundle:
    for name,source in sorted(files.items()):
        assert not any(part in name.split('/') for part in ('.env','node_modules','.runtime'))
        bundle.add(source,arcname=name,recursive=False)
report={'status':'packaged','archive':str(archive),'bytes':archive.stat().st_size,
        'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'release_id':metadata['release_id'],
        'source_tree_sha256':fingerprint,'source_file_count':len(sources),'payload_files':len(files)}
(folder/'package.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
