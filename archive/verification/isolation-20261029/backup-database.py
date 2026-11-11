import json
from pathlib import Path
import subprocess

program='''from datetime import datetime,timezone,timedelta
import gzip,hashlib,json,os,subprocess
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
environment=dotenv_values('/srv/agriscan/shared/production.env')
database=make_url(environment['DATABASE_URL']).database
assert database and database.replace('_','').isalnum()
os.umask(0o077)
folder=Path('/srv/agriscan/shared/backups/user-isolation-20261029')
folder.mkdir(parents=True,exist_ok=True,mode=0o700)
stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%dT%H%M%S')
target=folder/('database-before-'+stamp+'.sql.gz')
assert not target.exists()
process=subprocess.Popen(['mysqldump','--defaults-extra-file=/root/.my.cnf','--single-transaction',
    '--routines','--triggers','--set-gtid-purged=OFF','--databases',database],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
with gzip.open(target,'wb') as compressed:
    for chunk in iter(lambda:process.stdout.read(1024*1024),b''):
        compressed.write(chunk)
process.wait(timeout=120)
assert process.returncode==0,'Database backup failed; migration must not proceed.'
target.chmod(0o600)
with gzip.open(target,'rb') as original:
    restored_bytes=sum(len(chunk) for chunk in iter(lambda:original.read(1024*1024),b''))
engine=create_engine(environment['DATABASE_URL'])
with engine.connect() as db:
    counts={table:db.execute(text('SELECT count(*) FROM '+table)).scalar() for table in ('users','detections','plots','assistant_conversations')}
    row=dict(db.execute(text("SELECT version,data,encrypted_secrets,updated_by,updated_at FROM workspace_configuration WHERE id='workspace'")).mappings().one())
    config_hash=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()
    revision=db.execute(text('SELECT version_num FROM alembic_version')).scalar()
report={'status':'passed','backup':str(target),'gzip_bytes':target.stat().st_size,'sql_bytes':restored_bytes,
    'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'counts':counts,'schema_before':revision,
    'configuration_version':row['version'],'configuration_sha256':config_hash}
(folder/'baseline.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server',
    '/srv/agriscan/venv/bin/python -'],input=program,text=True,encoding='utf-8',capture_output=True,timeout=150,check=True)
Path('.runtime/isolation-20261029/database-backup.json').write_text(result.stdout,encoding='utf-8')
print(result.stdout.strip())
