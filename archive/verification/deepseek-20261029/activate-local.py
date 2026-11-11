import hashlib
import json
from pathlib import Path
import subprocess

folder=Path('.runtime/deepseek-20261029')
manifest=json.loads((folder/'patch-manifest.json').read_text(encoding='utf-8'))
for name,digest in manifest['files'].items():
    if name.startswith('backend/'):
        path=Path(name)
    elif name.startswith('public/workspace/'):
        path=Path('frontend/dist')/name[len('public/workspace/'):]
    else:
        path=Path('admin/dist')/name[len('public/admin/'):]
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
program=(folder/'activate-update.py').read_text(encoding='utf-8')
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',
                       'tencent-server','python3 - '+manifest['sha256']],
                      input=program,text=True,capture_output=True,timeout=150)
if result.returncode:
    print(result.stdout)
    print(result.stderr)
    raise SystemExit(result.returncode)
report=json.loads(result.stdout)
(folder/'deployment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
