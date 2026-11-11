import json
from pathlib import Path
import subprocess

folder = Path('E:/AgriScan/.runtime/isolation-20261029/apk')
manifest = json.loads((folder / 'upload-manifest.json').read_text(encoding='utf-8'))
script = ('import json\nmanifest = json.loads(' + repr(json.dumps(manifest,ensure_ascii=True)) + ')\n'
          + Path('E:/AgriScan/.runtime/isolation-20261029/publish-server-apk.py').read_text(encoding='utf-8'))
result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','python3 -'],
                         input=script,text=True,capture_output=True,timeout=90)
if result.returncode:
    print('Server publish did not complete; published bytes were guarded by rollback checks.')
    if result.stdout:
        print(result.stdout)
    raise SystemExit(result.stderr)
report = json.loads(result.stdout)
(folder / 'server-publish.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'target_directory':report['target_directory'],
                  'backup_directory':report['backup_directory'],'files':report['files']}))
