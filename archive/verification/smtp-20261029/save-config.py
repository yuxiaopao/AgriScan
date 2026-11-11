"""CAS-patch only verified SMTP fields; preserve the user's other configuration."""
import json,subprocess
from pathlib import Path
folder=Path(__file__).resolve().parent
private=json.loads((folder/'credentials.json').read_text(encoding='utf-8'))
probe=json.loads((folder/'probe.json').read_text(encoding='utf-8'))
assert probe['status']=='passed' and probe['authentication_succeeded'] and probe['tls_verified']
source=r'''
import json,hashlib,hmac
from pathlib import Path
from datetime import datetime,timezone
import httpx
from dotenv import dotenv_values
from cryptography.fernet import Fernet
from sqlalchemy import create_engine,text
private=json.loads(PRIVATE_LITERAL)
environment=dotenv_values('/srv/agriscan/shared/production.env')
engine=create_engine(environment['DATABASE_URL'])
cipher=Fernet(environment['CONFIG_ENCRYPTION_KEY'].encode('ascii'))
def row():
    with engine.connect() as db:
        return dict(db.execute(text("SELECT id,version,data,encrypted_secrets,updated_by,updated_at FROM workspace_configuration WHERE id='workspace'")).mappings().one())
def secrets_for(record):
    return json.loads(cipher.decrypt(record['encrypted_secrets'].encode()).decode()) if record['encrypted_secrets'] else {}
report={'mail_sent':False,'smtp_tls_login_preverified':True,'only_smtp_configuration_written':True}
token=None
try:
    with httpx.Client(base_url='http://127.0.0.1:18000/api',trust_env=False,timeout=20,follow_redirects=False) as client:
        login=client.post('/auth/login',json={'username':environment['ADMIN_USERNAME'],'password':environment['ADMIN_PASSWORD']})
        assert login.status_code==200,'Configuration control authentication failed'
        token=login.json()['access_token']
        headers={'Authorization':'Bearer '+token}
        for attempt in range(3):
            before=client.get('/admin/config',headers=headers)
            assert before.status_code==200
            before=before.json()
            old_row=row()
            if old_row['version']!=before['version']:continue
            old_secrets=secrets_for(old_row)
            backup=Path('/srv/agriscan/shared/backups')/('smtp-config-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
            with backup.open('x',encoding='utf-8') as output:json.dump(old_row,output,ensure_ascii=False,default=str,indent=2)
            backup.chmod(0o600)
            patch={**private,'email_verification_enabled':True}
            saved=client.patch('/admin/config',headers=headers,json={'version':before['version'],'integrations':patch})
            if saved.status_code==409:continue
            assert saved.status_code==200,'Configuration save failed; private response suppressed'
            after=saved.json()
            assert after['version']==before['version']+1
            for group in ('brand','features','limits'):assert after[group]==before[group]
            for name,value in before['integrations'].items():
                if name not in {*private,'email_verification_enabled','smtp_password_configured'}:assert after['integrations'][name]==value
            assert after['integrations']['smtp_password_configured'] and after['integrations']['email_verification_enabled']
            current=row()
            new_secrets=secrets_for(current)
            assert hmac.compare_digest(new_secrets['smtp_password'],private['smtp_password'])
            assert old_secrets.get('llm_api_key')==new_secrets.get('llm_api_key')
            assert private['smtp_password'] not in current['encrypted_secrets']
            report.update(status='passed',configuration_before=before['version'],configuration_after=after['version'],
                          other_settings_preserved=True,registration_switch_preserved=True,
                          smtp_password_encrypted=True,llm_secret_preserved=True,backup=str(backup))
            break
        else:raise RuntimeError('Configuration changed concurrently; no SMTP update was applied')
        assert token
        report['owned_control_session_revoked']=client.post('/auth/logout',headers={'Authorization':'Bearer '+token}).status_code==200
        token=None
except Exception as error:
    report.update(status='failed',error_type=type(error).__name__)
finally:
    if token:
        try:
            with httpx.Client(base_url='http://127.0.0.1:18000/api',trust_env=False,timeout=10) as client:
                report['owned_control_session_revoked']=client.post('/auth/logout',headers={'Authorization':'Bearer '+token}).status_code==200
        except Exception:report['owned_control_session_revoked']=False
    engine.dispose()
print(json.dumps(report))
'''.replace('PRIVATE_LITERAL',repr(json.dumps(private)))
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','/srv/agriscan/venv/bin/python -'],
                      input=source,encoding='utf-8',capture_output=True,timeout=120)
if result.returncode:raise SystemExit('Configuration update did not return a safe report; private stderr suppressed.')
report=json.loads(result.stdout)
(folder/'configuration-saved.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
raise SystemExit(0 if report['status']=='passed' else 1)
