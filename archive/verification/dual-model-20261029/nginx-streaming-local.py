"""Validate local Nginx streaming plan; SSH only on explicit inspect/apply flags."""
import argparse
import ast
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import types

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--plan',type=Path,default=ROOT/'nginx-streaming-plan.json')
mode=parser.add_mutually_exclusive_group();mode.add_argument('--inspect-server',action='store_true');mode.add_argument('--apply',action='store_true')
args=parser.parse_args()
source_path=ROOT/'nginx-streaming-server.py';source=source_path.read_text(encoding='utf-8-sig');ast.parse(source)
if os.name=='nt':sys.modules['fcntl']=types.SimpleNamespace()
spec=importlib.util.spec_from_file_location('nginx_streaming_reviewed',source_path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
plan=json.loads(args.plan.read_text(encoding='utf-8-sig'));module.validate(plan)
summary={'status':'validated_local_only','run_id':plan['run_id'],'script_sha256':hashlib.sha256(source.encode()).hexdigest(),
         'expected_before_sha256':plan['expected_inc_sha256'],'expected_after_sha256':plan['expected_patched_sha256']}
if not (args.apply or args.inspect_server):print(json.dumps(summary));raise SystemExit(0)
encoded=base64.b64encode(json.dumps(plan).encode()).decode()
remote='python3 - --plan-base64 '+shlex.quote(encoded)+(' --apply' if args.apply else '')
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=8','tencent-server',remote],
                      input=source,text=True,encoding='utf-8',errors='replace',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                      timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
lines=[line.removeprefix('RESULT ') for line in result.stdout.splitlines() if line.startswith('RESULT ')]
if len(lines)!=1:raise SystemExit('No unique safe Nginx report; inspect before retrying. Raw stderr suppressed.')
report=json.loads(lines[0]);report['script_sha256']=summary['script_sha256'];report['ssh_exit_code']=result.returncode
output=ROOT/('nginx-streaming-report.json' if args.apply else 'nginx-streaming-inspect.json')
output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'report':str(output)},ensure_ascii=False))
raise SystemExit(0 if result.returncode==0 and report['status'] in {'passed','already_applied','prepared_read_only'} else 1)
