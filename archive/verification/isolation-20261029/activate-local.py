import json
from pathlib import Path
import subprocess

folder=Path('.runtime/isolation-20261029')
manifest=json.loads((folder/'patch-manifest.json').read_text(encoding='utf-8'))
program=(folder/'activate-update.py').read_text(encoding='utf-8')
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server',
        '/srv/agriscan/venv/bin/python - '+manifest['sha256']],input=program,text=True,
        encoding='utf-8',capture_output=True,timeout=160)
if result.returncode:
    print(result.stdout)
    print(result.stderr)
    raise SystemExit(result.returncode)
report=json.loads(result.stdout)
(folder/'deployment.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
