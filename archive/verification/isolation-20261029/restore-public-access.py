import json
from pathlib import Path
import subprocess

assert json.loads(Path('.runtime/isolation-20261029/production-preflight.json').read_text(encoding='utf-8'))['status']=='passed'
program='''import hashlib,json,subprocess
from pathlib import Path
target=Path('/etc/nginx/agriscan-locations.inc')
contained=target.read_bytes()
assert hashlib.sha256(contained).hexdigest()=='d848ad854f9803d5ca51cdfb101484b6904a4b3f242d9bc27c0f3133c309d691'
restored=Path('/srv/agriscan/shared/backups/user-isolation-20261029/nginx-before.inc').read_bytes()
assert hashlib.sha256(restored).hexdigest()=='c5b9642a387c621f74d48f3ef0d3ad882f3a4df32b4c926ae8b244b93a531d9d'
target.write_bytes(restored)
target.chmod(0o644)
try:
    subprocess.run(['nginx','-t'],check=True,capture_output=True)
    subprocess.run(['systemctl','reload','nginx'],check=True,capture_output=True)
except Exception:
    target.write_bytes(contained)
    subprocess.run(['nginx','-t'],check=True,capture_output=True)
    subprocess.run(['systemctl','reload','nginx'],check=True,capture_output=True)
    raise
print(json.dumps({'status':'restored','temporary_gate_removed':True,'nginx_config_test':'passed'}))
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','python3 -'],
        input=program,text=True,encoding='utf-8',capture_output=True,timeout=45,check=True)
Path('.runtime/isolation-20261029/restored.json').write_text(result.stdout,encoding='utf-8')
print(result.stdout.strip())
