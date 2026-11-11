import json
from pathlib import Path
import subprocess
import sys

mode=sys.argv[1] if len(sys.argv)==2 else ''
if mode not in {'inspect','apply'}:raise SystemExit('Explicit inspect or apply required.')
source=Path('.runtime/server-latest-20261029/cleanup-owned-qa-server.py').read_text(encoding='utf-8')
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server',
                       '/srv/agriscan/venv/bin/python - '+mode],input=source,text=True,capture_output=True,timeout=150)
try:report=json.loads(result.stdout)
except ValueError:
    raise SystemExit('No safe structured cleanup report returned; inspect server manually without exposing credentials.')
target=Path('.runtime/server-latest-20261029/qa-cleanup.json' if mode=='apply' else '.runtime/server-latest-20261029/qa-cleanup-preflight.json')
target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:report.get(key) for key in ['status','mode','detection_id','conversation_id','qa_row_counts','preserved_detection_count','backup','error']},ensure_ascii=False))
print('Report: '+str(target))
if result.returncode:raise SystemExit(result.returncode)
