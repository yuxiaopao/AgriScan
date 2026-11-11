"""Complete this migration's renewal check without the cron random-sleep delay."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

REPORT = Path('/srv/agriscan/shared/logs/domain-migration-20261029-server.json')
CERT = Path('/etc/letsencrypt/live/agriscan.ming-ai.top/fullchain.pem')
report = json.loads(REPORT.read_text())
assert report['domain'] == 'agriscan.ming-ai.top' and report['stage'] == 'renewal_test'
before_cert = hashlib.sha256(CERT.read_bytes()).hexdigest()
report['initial_renewal_test'] = {'failure_type': report.get('failure_type'),
    'reason': 'Certbot noninteractive random sleep was 380.285876 seconds; the verification command timed out before ACME ran.'}
args = ['certbot', 'renew', '--cert-name', 'agriscan.ming-ai.top', '--dry-run', '--non-interactive',
        '--no-random-sleep-on-renew']
print('Checking a staging renewal; only this manual run skips cron random sleep.', flush=True)
result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=180)
report['certificate_renewal_dry_run'] = {'exit_code': result.returncode, 'stdout': result.stdout.strip(),
                                        'stderr': result.stderr.strip(), 'manual_random_sleep_disabled': True}
unit = subprocess.run(['systemctl', 'cat', 'certbot-renew.service'], capture_output=True, text=True, check=True)
report['renewal_unit'] = unit.stdout.strip()
timer = subprocess.run(['systemctl', 'is-enabled', 'certbot-renew.timer'], capture_output=True, text=True, check=True)
report['renewal_timer_enabled'] = timer.stdout.strip()
certificate_unchanged = before_cert == hashlib.sha256(CERT.read_bytes()).hexdigest()
report['renewal_dry_run_kept_production_certificate'] = certificate_unchanged
check = subprocess.run(['curl', '--silent', '--show-error', '--noproxy', '*', '--fail', '--max-time', '20',
    'https://agriscan.ming-ai.top/agriscan/api/health'], capture_output=True, text=True, timeout=25)
report['final_normal_dns_health'] = {'exit_code': check.returncode,
    'body': json.loads(check.stdout) if check.returncode == 0 else None}
if (result.returncode == 0 and certificate_unchanged and check.returncode == 0
        and 'certbot renew' in report['renewal_unit'] and 'systemctl reload nginx' in report['renewal_unit']):
    report['status'] = 'passed'
    report['stage'] = 'complete'
    report.pop('failure', None)
    report.pop('failure_type', None)
else:
    report['status'] = 'deployed_renewal_test_failed'
report['finished_at'] = datetime.now(timezone.utc).isoformat()
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
REPORT.chmod(0o600)
print(json.dumps({'status': report['status'], 'report': str(REPORT),
    'renewal_exit_code': result.returncode, 'renewal_output': result.stdout.strip()}, indent=2))
raise SystemExit(0 if report['status'] == 'passed' else 1)
