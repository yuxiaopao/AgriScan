"""Executed through SSH stdin; only booleans and non-secret settings leave host."""
import hashlib
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet
from dotenv import dotenv_values
from sqlalchemy import create_engine, text

EXPECTED_KEY = None
BACKUP = False
environment=dotenv_values('/srv/agriscan/shared/production.env')
engine=create_engine(environment['DATABASE_URL'])
with engine.connect() as connection:
    row=dict(connection.execute(text('SELECT version,data,encrypted_secrets,updated_by,updated_at FROM workspace_configuration WHERE id=:id'),{'id':'workspace'}).mappings().one())
    data=json.loads(row['data']) if isinstance(row['data'],str) else row['data']
    encoded=json.dumps(row,default=str,ensure_ascii=False,sort_keys=True)
    report={'version':row['version'],'row_sha256':hashlib.sha256(encoded.encode()).hexdigest(),
            'encrypted_secrets_present':bool(row['encrypted_secrets'])}
    if BACKUP:
        os.umask(0o077)
        backup=Path('/srv/agriscan/shared/backups/deepseek-20261029')
        backup.mkdir(parents=True,exist_ok=True,mode=0o700)
        destination=backup/'configuration-before.json'
        if not destination.exists():
            destination.write_text(encoded,encoding='utf-8')
            destination.chmod(0o600)
        report['backup']=str(destination)
    if EXPECTED_KEY:
        ciphertext=row['encrypted_secrets'] or ''
        secrets=json.loads(Fernet(environment['CONFIG_ENCRYPTION_KEY'].encode()).decrypt(ciphertext.encode()))
        report.update(credential_matches=secrets.get('llm_api_key')==EXPECTED_KEY,
                      plaintext_absent_from_json=EXPECTED_KEY not in json.dumps(data),
                      plaintext_absent_from_ciphertext=EXPECTED_KEY not in ciphertext,
                      cipher_length=len(ciphertext),
                      audit_contains_no_key=not bool(connection.execute(text('SELECT count(*) FROM audit_logs WHERE summary LIKE :value'),{'value':'%'+EXPECTED_KEY+'%'}).scalar()))
        report['llm']={name:data['integrations'][name] for name in ('llm_enabled','llm_base_url','llm_model','llm_timeout')}
print(json.dumps(report))
