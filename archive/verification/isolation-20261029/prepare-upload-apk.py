import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

root = Path('E:/AgriScan')
folder = root / '.runtime/isolation-20261029/apk'
verification = json.loads((folder / 'verification.json').read_text(encoding='utf-8'))
assert verification['status'] == 'passed'
apk = Path(verification['artifact'])
assert hashlib.sha256(apk.read_bytes()).hexdigest() == verification['sha256']
remote_code = (root / '.runtime/isolation-20261029/backup-server-apk.py').read_text(encoding='utf-8')
result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','python3 -'],
                         input=remote_code, text=True, capture_output=True, timeout=60, check=True)
backup = json.loads(result.stdout)
(folder / 'server-backup.json').write_text(json.dumps(backup,indent=2),encoding='utf-8')
print('Server APK, checksum and release metadata backed up.', flush=True)
downloads = root / 'website/downloads'
local_backup = folder / 'local-before'
local_backup.mkdir(exist_ok=True)
names = ('agriscan-test.apk','agriscan-test.apk.sha256','release.json')
for name in names:
    saved = local_backup / name
    if saved.exists():
        assert saved.read_bytes() == (downloads / name).read_bytes(), 'Existing local backup differs; preserved.'
    else:
        shutil.copy2(downloads / name, saved)
release = json.loads((downloads / 'release.json').read_text(encoding='utf-8'))
assert release['version'] == '1.0.1' and release['version_code'] == 2
release.update(status='ready', version='1.0.2', version_code=3,
               size_bytes=verification['apk_bytes'], sha256=verification['sha256'],
               api_base_url=verification['compiled_api_base'], published_at='2026-10-29')
prepared = folder / 'publish-files'
prepared.mkdir(exist_ok=True)
shutil.copy2(apk, prepared / names[0])
(prepared / names[1]).write_text(verification['sha256']+'  agriscan-test.apk\n',encoding='ascii')
(prepared / names[2]).write_text(json.dumps(release,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
stage = '/srv/agriscan/bootstrap/isolation-20261029-apk-code3-' + uuid4().hex[:10]
manifest = {'stage':stage,'files':[], 'backup':backup, 'release':release}
for name in names:
    local = prepared / name
    manifest['files'].append({'name':name,'sha256':hashlib.sha256(local.read_bytes()).hexdigest(),
                              'bytes':local.stat().st_size})
(folder / 'upload-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
for item in manifest['files']:
    subprocess.run([sys.executable,str(root / 'deploy/upload-artifact.py'),
                    str(prepared / item['name']),stage+'/'+item['name']],check=True,timeout=900)
print('All staged files transferred and verified.',flush=True)
for name in names:
    temporary = downloads / (name+'.isolation-code3.next')
    assert not temporary.exists()
    shutil.copy2(prepared / name, temporary)
    os.replace(temporary, downloads / name)
print('Local download artifacts updated; production files not yet replaced.',flush=True)
