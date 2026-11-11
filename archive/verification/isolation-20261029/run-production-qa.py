import json
import os
from pathlib import Path
import subprocess

folder=Path(__file__).resolve().parent
manifest=json.loads((folder/'qa-fixtures.json').read_text(encoding='utf-8'))
target=folder/'qa-credentials.json'
assert not target.exists(),'Existing credentials preserved; resume the owned fixtures explicitly.'
source=(folder/'production-qa-server.py').read_text(encoding='utf-8')
source=source.replace('__QA_FIXTURE_MANIFEST__',repr(manifest))
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15',
                       'tencent-server','/srv/agriscan/venv/bin/python -'],
                      input=source,text=True,capture_output=True,timeout=360,encoding='utf-8')
if result.returncode:
    raise SystemExit('Owned QA transport failed; private remote checkpoint retained. No response body printed.')
try:envelope=json.loads(result.stdout)
except ValueError:raise SystemExit('QA response was not a single JSON envelope; private output was not printed.')
user=os.environ.get('USERDOMAIN','')+'\\'+os.environ['USERNAME']
temporary=target.with_suffix('.json.next')
with temporary.open('x',encoding='utf-8') as output:
    subprocess.run(['icacls',str(temporary),'/inheritance:r','/grant:r',user+':(F)'],capture_output=True,check=True)
    json.dump(envelope['private_credentials'],output,ensure_ascii=False,indent=2)
os.replace(temporary,target)
report=envelope['report']
(folder/'production-preflight.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'run_id':report['run_id'],'checks':len(report['checks']),
                  'fixtures':report.get('retained_owned_fixtures'),'error':report.get('error'),
                  'error_type':report.get('error_type'),'credential_file':str(target),
                  'report_file':str(folder/'production-preflight.json')}))
if report['status']!='passed':raise SystemExit(1)
