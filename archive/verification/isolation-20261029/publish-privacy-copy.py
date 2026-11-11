import base64
import hashlib
import json
from pathlib import Path
import subprocess

content=Path('.runtime/isolation-20261029/owned-document/website/index.html').read_bytes()
expected=hashlib.sha256(content).hexdigest()
program='''import base64,hashlib,json,os,shutil
from pathlib import Path
target=Path('/srv/agriscan/current/public/index.html')
assert hashlib.sha256(target.read_bytes()).hexdigest()=='81029344e1263ce7fabf1d107dd4de9cfbe063cd6bb34943b52cec63e4b76059'
backup=Path('/srv/agriscan/shared/backups/user-isolation-20261029/website-before.html')
assert not backup.exists()
shutil.copy2(target,backup)
backup.chmod(0o600)
data=base64.b64decode(PAYLOAD)
assert hashlib.sha256(data).hexdigest()==DIGEST
temporary=target.with_name('.index.isolation.next')
assert not temporary.exists()
temporary.write_bytes(data)
temporary.chmod(0o644)
os.replace(temporary,target)
print(json.dumps({'status':'passed','sha256':DIGEST,'backup':str(backup)}))
'''.replace('PAYLOAD',repr(base64.b64encode(content).decode())).replace('DIGEST',repr(expected))
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','python3 -'],
                       input=program,text=True,encoding='utf-8',capture_output=True,timeout=40,check=True)
Path('.runtime/isolation-20261029/website.json').write_text(result.stdout,encoding='utf-8')
print(result.stdout.strip())
