"""Change only the two stable asset URLs, then refresh their static manifest entries."""
import hashlib,json
from datetime import datetime,timezone
from pathlib import Path

folder=Path(__file__).resolve().parent
root=folder.parents[1]
source=root/'website/index.html'
stage=folder/'website/index.html'
report_path=folder/'web-ready.json'
report=json.loads(report_path.read_text(encoding='utf-8'))
old=source.read_bytes()
assert stage.read_bytes()==old,'Source/staged website index diverged; preserve both for explicit review.'
assert len(report['source_files'])==report['source_file_count']==113
before_sources=dict(report['source_files'])
for name,item in before_sources.items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==item['sha256'],name
compiled_before={surface:report['builds'][surface] for surface in ['frontend','admin']}
archive=folder/'latest-full-ui.tar.gz'
archive_before=hashlib.sha256(archive.read_bytes()).hexdigest()
assets={}
new=old
for name,attribute in [('style.css','href'),('app.js','src')]:
    content=(root/'website'/name).read_bytes()
    assert (folder/'website'/name).read_bytes()==content
    digest=hashlib.sha256(content).hexdigest()
    original=f'{attribute}="./{name}"'.encode()
    replacement=f'{attribute}="./{name}?v={digest[:12]}"'.encode()
    assert new.count(original)==1,(name,'Expected one unversioned reference')
    new=new.replace(original,replacement,1)
    assets[name]={'sha256':digest,'version':digest[:12],'url':f'./{name}?v={digest[:12]}'}
assert len(new)==len(old)+30
source.write_bytes(new)
stage.write_bytes(new)
index={'bytes':len(new),'sha256':hashlib.sha256(new).hexdigest()}
report['source_files']['website/index.html']=index
report['website']['files']['index.html']=index
report['finished_at']=datetime.now(timezone.utc).isoformat()
report['checks']['website_content_hash_cache_busting']=True
report['cache_busting_fix']={
    'status':'passed','reason':'A browser opened before no-cache headers can retain old stable app.js/style.css URLs after HTML reload.',
    'change':'Only style.css and app.js reference URLs now include the first 12 hex characters of their actual content SHA256.',
    'assets':assets,'index_before_sha256':hashlib.sha256(old).hexdigest(),'index_after':index,
    'only_two_reference_replacements':True,'source_file_count':113,'compiled_artifacts_changed':False,
    'apk_artifact_changed':False,'original_full_archive_changed':False,'browser_verified':False,
}
assert report['builds']==compiled_before
for name,item in report['source_files'].items():
    current=(root/name).read_bytes()
    assert len(current)==item['bytes'] and hashlib.sha256(current).hexdigest()==item['sha256'],name
    if name!='website/index.html':assert item==before_sources[name],name
for name,item in report['website']['files'].items():
    current=(folder/'website'/name).read_bytes()
    assert len(current)==item['bytes'] and hashlib.sha256(current).hexdigest()==item['sha256'],name
assert hashlib.sha256(archive.read_bytes()).hexdigest()==archive_before
report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(folder/'cache-busting-fix.json').write_text(json.dumps(report['cache_busting_fix'],ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','assets':assets,'index':index,'source_file_count':113,
                  'full_archive_unchanged':True,'compiled_apk_unchanged':True,'report':str(report_path)}))
