import hashlib,json,shutil
from pathlib import Path
folder=Path('.runtime/dual-model-20261029')
verified=json.loads((folder/'apk/verification.json').read_text(encoding='utf-8'))
assert verified['status']=='passed' and verified['version']=='1.0.4' and verified['version_code']==5
source=folder/'apk/agriscan-test-1.0.4-code5.apk'
assert hashlib.sha256(source.read_bytes()).hexdigest()==verified['sha256']
public=Path('website/downloads')
backup=folder/'previous-downloads'
backup.mkdir(exist_ok=False)
for name in ('agriscan-test.apk','agriscan-test.apk.sha256','release.json'):shutil.copy2(public/name,backup/name)
shutil.copy2(source,public/'agriscan-test.apk')
(public/'agriscan-test.apk.sha256').write_text(verified['sha256']+'  agriscan-test.apk\n',encoding='ascii')
release=json.loads((public/'release.json').read_text(encoding='utf-8'))
release.update(version='1.0.4',version_code=5,size_bytes=source.stat().st_size,sha256=verified['sha256'],published_at='2026-10-29')
(public/'release.json').write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'prepared','version':release['version'],'bytes':release['size_bytes'],'sha256':release['sha256']}))
