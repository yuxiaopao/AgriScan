"""Validate public deployment metadata, then explicitly run the reviewed server script."""
import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Queue
import re
import shlex
import subprocess
from threading import Thread
from time import monotonic

folder=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--plan',type=Path,default=folder/'deployment-plan.json')
parser.add_argument('--apply',action='store_true')
parser.add_argument('--timeout',type=int,default=1200)
args=parser.parse_args()
if args.timeout<600:
    raise SystemExit('Wrapper timeout must allow at least 600 seconds for graceful restart and rollback.')
plan=json.loads(args.plan.read_text(encoding='utf-8'))
source=(folder/'activate-server.py').read_text(encoding='utf-8')
ast.parse(source)
allowed={'patch_archive_path','patch_sha256','release_id','payload_manifest_sha256','expected_current',
         'expected_schema','expected_configuration_version','expected_configuration_sha256','expected_api_pid',
         'classification_archive_path','classification_archive_sha256','classification_onnx_sha256',
         'detection_onnx_sha256','apk_path','apk_sha256','apk_bytes','apk_version','apk_version_code',
         'expected_previous_classification_value'}
if set(plan)!=allowed:
    raise SystemExit('Plan fields must match the documented public-metadata-only schema.')
for key,value in plan.items():
    if key.endswith('_sha256') and (not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value)):
        raise SystemExit('Fill every SHA256 with the verified package value before execution.')
if not re.fullmatch(r'release-[a-z0-9][a-z0-9-]{5,100}',plan['release_id']):
    raise SystemExit('Fill the release id from the actual release-info.json before execution.')
summary={'status':'validated_local_only','release_id':plan['release_id'],'expected_current':plan['expected_current'],
         'server_script_sha256':hashlib.sha256(source.encode()).hexdigest(),
         'patch_sha256':plan['patch_sha256'],'payload_manifest_sha256':plan['payload_manifest_sha256']}
if not args.apply:
    print(json.dumps(summary))
    raise SystemExit(0)
encoded=base64.b64encode(json.dumps(plan,ensure_ascii=True).encode()).decode()
remote='/srv/agriscan/venv/bin/python - --plan-base64 '+shlex.quote(encoded)+' --apply'
command=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15',
         '-o','ServerAliveCountMax=8','tencent-server',remote]
process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
messages=Queue()
def read_output():
    for line in process.stdout:
        messages.put(line.rstrip('\n'))
    messages.put(None)
Thread(target=read_output,daemon=True).start()
process.stdin.write(source)
process.stdin.close()
deadline=monotonic()+args.timeout
result=None
ended=False
while not ended:
    remaining=deadline-monotonic()
    if remaining<=0:
        process.terminate()
        raise SystemExit('SSH wrapper deadline reached. Inspect the private server release log before any retry; do not assume activation stopped.')
    try:
        line=messages.get(timeout=min(1,remaining))
    except Empty:
        continue
    if line is None:
        ended=True
    elif line.startswith('STAGE '):
        print(line,flush=True)
    elif line.startswith('RESULT '):
        result=json.loads(line.removeprefix('RESULT '))
    elif line.startswith('PRECHECK_FAILED '):
        print(line,flush=True)
    # Suppress raw SSH/Python stderr: only fixed stage/error codes and the
    # explicitly safe server report are emitted, never environment data.
exit_code=process.wait(timeout=30)
if result is None:
    raise SystemExit('No final activation report received. Inspect /srv/agriscan/shared/logs/'+plan['release_id']+'.json before retrying.')
result['activation_script_sha256']=summary['server_script_sha256']
result['ssh_exit_code']=exit_code
target=folder/'deployment.json'
target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':result['status'],'release_id':plan['release_id'],'report':str(target)}),flush=True)
raise SystemExit(0 if exit_code==0 and result['status']=='passed' else 1)
