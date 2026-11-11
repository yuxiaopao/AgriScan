"""Authenticate SMTP over verified TLS; no message is sent."""
import json,subprocess,sys
from pathlib import Path
folder=Path(__file__).resolve().parent
credentials=json.loads((folder/'credentials.json').read_text(encoding='utf-8'))
assert credentials['smtp_host']=='smtp.qq.com' and credentials['smtp_port']==465 and credentials['smtp_security']=='ssl'
source='''import json,smtplib,ssl
from datetime import datetime,timezone
config=json.loads(CONFIG_LITERAL)
report={'checked_at':datetime.now(timezone.utc).isoformat(),'smtp_host':config['smtp_host'],'smtp_port':config['smtp_port'],'mail_sent':False,'phase':'connect'}
try:
    with smtplib.SMTP_SSL(config['smtp_host'],config['smtp_port'],timeout=15,context=ssl.create_default_context()) as smtp:
        report.update(tls_verified=True,tls_version=smtp.sock.version(),phase='ehlo')
        smtp.ehlo('agriscan.ming-ai.top')
        report['auth_mechanisms']=smtp.esmtp_features.get('auth','')
        report['phase']='login'
        if USE_LOGIN_ONLY:
            smtp.user=config['smtp_username'];smtp.password=config['smtp_password']
            result=smtp.auth('LOGIN',smtp.auth_login,initial_response_ok=False)
        else:
            result=smtp.login(config['smtp_username'],config['smtp_password'])
        report.update(status='passed',phase='authenticated',authentication_succeeded=result[0]==235)
except Exception as error:
    if not report.get('authentication_succeeded'):report.update(status='failed',error_type=type(error).__name__,smtp_code=getattr(error,'smtp_code',None))
print(json.dumps(report))
'''.replace('CONFIG_LITERAL',repr(json.dumps(credentials))).replace('USE_LOGIN_ONLY',repr('--auth-login' in sys.argv))
command=([sys.executable,'-'] if '--local' in sys.argv else ['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','python3 -'])
result=subprocess.run(command,
                      input=source,encoding='utf-8',capture_output=True,timeout=50)
if result.returncode:raise SystemExit('SMTP connection test did not return a safe report; private stderr was suppressed.')
report=json.loads(result.stdout)
report['origin']='local' if '--local' in sys.argv else 'production_server'
(folder/('probe-local.json' if '--local' in sys.argv else 'probe.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
raise SystemExit(0 if report['status']=='passed' and report['authentication_succeeded'] else 1)
