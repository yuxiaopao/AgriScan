"""Local-only plan validation by default; explicit flags are required for SSH."""
import argparse
import ast
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--plan', type=Path, default=ROOT / 'cleanup-plan.json')
action = parser.add_mutually_exclusive_group()
action.add_argument('--inspect-server', action='store_true')
action.add_argument('--apply', action='store_true')
args = parser.parse_args()
source_path = ROOT / 'cleanup-qa-server.py'
source = source_path.read_text(encoding='utf-8-sig')
ast.parse(source)
spec = importlib.util.spec_from_file_location('qa_cleanup_reviewed', source_path)
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
plan = module.validate_plan(json.loads(args.plan.read_text(encoding='utf-8-sig')))
summary = {'status': 'validated_local_only', 'run_tag': plan['run_tag'],
           'detection_count': len(plan['detections']), 'plot_count': len(plan['plots']),
           'plan_sha256': module.digest(plan), 'script_sha256': hashlib.sha256(source.encode()).hexdigest()}
if not (args.apply or args.inspect_server):
    print(json.dumps(summary)); raise SystemExit(0)
encoded = base64.b64encode(json.dumps(plan).encode()).decode()
remote = '/srv/agriscan/venv/bin/python - --plan-base64 ' + shlex.quote(encoded) + (' --apply' if args.apply else '')
command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15',
           '-o', 'ServerAliveCountMax=8', 'tencent-server', remote]
result = subprocess.run(command, input=source, text=True, encoding='utf-8', errors='replace',
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
lines = [line.removeprefix('RESULT ') for line in result.stdout.splitlines() if line.startswith('RESULT ')]
if len(lines) != 1:
    raise SystemExit('No unique safe server report received. Inspect the QA-only backup before any retry.')
report = json.loads(lines[0]); report['server_script_sha256'] = summary['script_sha256']
report['ssh_exit_code'] = result.returncode
output = ROOT / ('cleanup-report.json' if args.apply else 'cleanup-inspect.json')
output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': report['status'], 'mode': 'apply' if args.apply else 'inspect', 'report': str(output)}))
raise SystemExit(0 if result.returncode == 0 and report['status'] in {'passed', 'prepared_read_only'} else 1)
