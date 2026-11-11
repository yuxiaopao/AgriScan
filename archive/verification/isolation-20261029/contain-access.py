"""Temporarily stop leaking personal APIs while ownership is migrated."""
import json
from pathlib import Path
import subprocess

program='''import hashlib,json,os,subprocess
from pathlib import Path
target=Path('/etc/nginx/agriscan-locations.inc')
original=target.read_bytes()
assert hashlib.sha256(original).hexdigest()=='c5b9642a387c621f74d48f3ef0d3ad882f3a4df32b4c926ae8b244b93a531d9d'
os.umask(0o077)
backup=Path('/srv/agriscan/shared/backups/user-isolation-20261029')
backup.mkdir(parents=True,exist_ok=True,mode=0o700)
(backup/'nginx-before.inc').write_bytes(original)
gate=b"""# Temporary containment until user ownership migration is verified.
location ~ ^/agriscan/api/(dashboard(?:/|$)|detections(?:/|$)|plots(?:/|$)|uploads(?:/|$)|assistant/detections(?:/|$)|media/(video|frame)(?:/|$)) {
    default_type application/json;
    add_header Retry-After 60 always;
    add_header Cache-Control no-store always;
    return 503 '{"detail":"Personal data isolation upgrade in progress. Please retry shortly."}';
}
"""
target.write_bytes(gate+original)
target.chmod(0o644)
try:
    subprocess.run(['nginx','-t'],capture_output=True,check=True)
    subprocess.run(['systemctl','reload','nginx'],capture_output=True,check=True)
except Exception:
    target.write_bytes(original)
    subprocess.run(['nginx','-t'],capture_output=True,check=True)
    subprocess.run(['systemctl','reload','nginx'],capture_output=True,check=True)
    raise
print(json.dumps({'status':'contained','backup':str(backup),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','python3 -'],
                      input=program,text=True,encoding='utf-8',capture_output=True,timeout=45,check=True)
folder=Path('.runtime/isolation-20261029')
folder.mkdir(parents=True,exist_ok=True)
(folder/'containment.json').write_text(result.stdout,encoding='utf-8')
print(result.stdout.strip())
