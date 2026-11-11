import hashlib
import json
from pathlib import Path
import shutil

folder=Path('.runtime/server-latest-20261029')
verified=json.loads((folder/'apk/verification.json').read_text(encoding='utf-8'))
assert verified['status']=='passed' and verified['version']=='1.0.3' and verified['version_code']==4
source=Path(verified['artifact'])
assert hashlib.sha256(source.read_bytes()).hexdigest()==verified['sha256']
downloads=Path('website/downloads')
backup=folder/'previous-downloads'
backup.mkdir(exist_ok=False)
for name in ('agriscan-test.apk','agriscan-test.apk.sha256','release.json'):
    shutil.copy2(downloads/name,backup/name)
metadata=json.loads((downloads/'release.json').read_text(encoding='utf-8'))
assert metadata['version']=='1.0.2'
metadata.update(version='1.0.3',version_code=4,size_bytes=verified['apk_bytes'],
                sha256=verified['sha256'],published_at='2026-10-29')
shutil.copy2(source,downloads/'agriscan-test.apk')
(downloads/'agriscan-test.apk.sha256').write_text(verified['sha256']+'  agriscan-test.apk\n',encoding='ascii')
(downloads/'release.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'status':'ready','version':metadata['version'],'version_code':metadata['version_code'],
                  'bytes':metadata['size_bytes'],'sha256':metadata['sha256']}))
