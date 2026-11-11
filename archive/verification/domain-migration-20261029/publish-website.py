import base64
import hashlib
import json
from pathlib import Path
import subprocess

local = Path('website/index.html').read_bytes()
expected = hashlib.sha256(local).hexdigest()
remote = '''import base64, hashlib, json, os, shutil
from pathlib import Path
target = Path('/srv/agriscan/current/public/index.html')
backup = Path('/srv/agriscan/shared/backups/domain-migration-20261029-website')
backup.mkdir(mode=0o700, parents=True, exist_ok=True)
saved = backup / 'index.html'
if not saved.exists():
    shutil.copy2(target, saved)
    saved.chmod(0o600)
data = base64.b64decode(PAYLOAD)
assert hashlib.sha256(data).hexdigest() == EXPECTED
temporary = target.with_name('.index.html.domain-next')
temporary.write_bytes(data)
temporary.chmod(0o644)
os.replace(temporary, target)
assert hashlib.sha256(target.read_bytes()).hexdigest() == EXPECTED
print(json.dumps({'status':'passed','sha256':EXPECTED,'backup':str(saved)}))
'''.replace('PAYLOAD', repr(base64.b64encode(local).decode())).replace('EXPECTED', repr(expected))
result = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',
                         'tencent-server','python3 -'], input=remote,
                        text=True, capture_output=True, check=True, timeout=45)
report = json.loads(result.stdout)
Path('.runtime/domain-migration-20261029/website.json').write_text(
    json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report))
