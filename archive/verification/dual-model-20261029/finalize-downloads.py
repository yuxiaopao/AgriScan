import hashlib,json,shutil
from pathlib import Path
folder=Path('.runtime/mobile-cancel-final-20261029')
verified=json.loads((folder/'apk/verification.json').read_text(encoding='utf-8'))
assert verified['status']=='passed' and verified['version']=='1.0.4' and verified['version_code']==5
source=Path(verified['artifact'])
assert hashlib.sha256(source.read_bytes()).hexdigest()==verified['sha256']
public=Path('website/downloads')
shutil.copy2(source,public/'agriscan-test.apk')
(public/'agriscan-test.apk.sha256').write_text(verified['sha256']+'  agriscan-test.apk\n',encoding='ascii')
release=json.loads((public/'release.json').read_text(encoding='utf-8'))
release.update(version='1.0.4',version_code=5,size_bytes=source.stat().st_size,sha256=verified['sha256'],published_at='2026-10-29')
(public/'release.json').write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'prepared','version':release['version'],'bytes':release['size_bytes'],'sha256':release['sha256']}))
