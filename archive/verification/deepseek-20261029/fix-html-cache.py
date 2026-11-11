import base64
import hashlib
import json
from pathlib import Path
import subprocess

data=Path('deploy/agriscan-locations.inc').read_text(encoding='utf-8').encode()
expected=hashlib.sha256(data).hexdigest()
program='''import base64,hashlib,json,os,subprocess
from pathlib import Path
target=Path('/etc/nginx/agriscan-locations.inc')
original=target.read_bytes()
assert hashlib.sha256(original).hexdigest()=='fdf598821742ca666b81c5e262ece2cf9bc500b8980a30acfd2d7771d50f9e19'
backup=Path('/srv/agriscan/shared/backups/deepseek-20261029/nginx-locations-before-cache.inc')
assert not backup.exists()
backup.write_bytes(original)
backup.chmod(0o600)
data=base64.b64decode(PAYLOAD)
assert hashlib.sha256(data).hexdigest()==DIGEST
temporary=target.with_name('.agriscan-locations.next')
temporary.write_bytes(data)
temporary.chmod(0o644)
os.replace(temporary,target)
try:
    subprocess.run(['nginx','-t'],check=True,capture_output=True)
    subprocess.run(['systemctl','reload','nginx'],check=True,capture_output=True)
except Exception:
    if target.read_bytes()==data:
        target.write_bytes(original)
        subprocess.run(['nginx','-t'],check=True,capture_output=True)
        subprocess.run(['systemctl','reload','nginx'],check=True,capture_output=True)
    raise
print(json.dumps({'status':'passed','sha256':DIGEST,'backup':str(backup)}))
'''.replace('PAYLOAD',repr(base64.b64encode(data).decode())).replace('DIGEST',repr(expected))
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','python3 -'],
                      input=program,text=True,capture_output=True,timeout=45,check=True)
report=json.loads(result.stdout)
Path('.runtime/deepseek-20261029/cache.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
