import argparse,json
from pathlib import Path
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('--apply-after-browser-signoff',action='store_true')
args=parser.parse_args()
assert args.apply_after_browser_signoff,'Cleanup requires root browser sign-off; no operation performed.'
folder=Path(__file__).resolve().parent
private_path=folder/'qa-credentials.json'
private=json.loads(private_path.read_text(encoding='utf-8'))
allow_file=folder/'qa-extra-owned-ids.json'
allowed=json.loads(allow_file.read_text(encoding='utf-8')) if allow_file.exists() else {'detections':[],'plots':[]}
fixtures=json.loads((folder/'qa-fixtures.json').read_text(encoding='utf-8'))['fixtures']
source=(folder/'cleanup-qa-server.py').read_text(encoding='utf-8')
source=source.replace('__QA_RUN_ID__',repr(private['run_id'])).replace('__QA_CLEANUP_ALLOWLIST__',repr(allowed)).replace('__QA_FIXTURES__',repr(fixtures))
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server',
                       '/srv/agriscan/venv/bin/python -'],input=source,text=True,capture_output=True,timeout=180)
if result.returncode:raise SystemExit('Owned cleanup transport failed; no response body or credential was printed.')
report=json.loads(result.stdout)
(folder/'production-cleanup.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(folder/'cleanup.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
if report['status']=='passed':
    for account in private['accounts'].values():account['password']='[removed after disposable account deletion]'
    private['cleanup_status']='completed; disposable users and their exact allowed fixtures deleted'
    private_path.write_text(json.dumps(private,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'checks':len(report['checks']),'deleted':report['deleted'],
                  'error':report.get('error'),'error_type':report.get('error_type'),
                  'unexpected_owned_detection_ids':report.get('unexpected_owned_detection_ids'),
                  'unexpected_owned_plot_ids':report.get('unexpected_owned_plot_ids'),
                  'report':str(folder/'production-cleanup.json')}))
if report['status']!='passed':raise SystemExit(1)
