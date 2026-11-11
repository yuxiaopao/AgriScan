"""Activate ownership checks while personal API containment remains enabled."""
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from urllib.request import urlopen
from dotenv import dotenv_values
from sqlalchemy import create_engine, text, inspect

root=Path('/srv/agriscan')
archive=root/'bootstrap/user-isolation-patch-20261029.tar.gz'
expected=sys.argv[1]
assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
gate=Path('/etc/nginx/agriscan-locations.inc')
assert hashlib.sha256(gate.read_bytes()).hexdigest()=='d848ad854f9803d5ca51cdfb101484b6904a4b3f242d9bc27c0f3133c309d691'
baseline=json.loads((root/'shared/backups/user-isolation-20261029/baseline.json').read_text())
assert baseline['status']=='passed' and Path(baseline['backup']).is_file()
current=root/'current'
previous=current.resolve(strict=True)
assert previous.is_relative_to(root/'releases')
release=root/'releases'/('release-20261029-user-isolation-'+time.strftime('%H%M%S'))
assert not release.exists()
report={'previous_release':str(previous),'new_release':str(release),'archive_sha256':expected,
        'personal_api_containment':True}
report_path=root/'shared/logs/user-isolation-deployment-20261029.json'
environment=dotenv_values(root/'shared/production.env')
engine=create_engine(environment['DATABASE_URL'])
def snapshot():
    with engine.connect() as db:
        tables={}
        for table in ('detections','plots','assistant_conversations','assistant_messages','assistant_detection_discussions'):
            rows=[]
            for row in db.execute(text('SELECT * FROM '+table)).mappings():
                data=dict(row)
                data.pop('owner_id',None)
                rows.append(json.dumps(data,ensure_ascii=False,sort_keys=True,default=str))
            tables[table]=hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()
        row=dict(db.execute(text("SELECT version,data,encrypted_secrets,updated_by,updated_at FROM workspace_configuration WHERE id='workspace'")).mappings().one())
        return {'tables':tables,'configuration_version':row['version'],
                'configuration_sha256':hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()}
before=snapshot()
try:
    shutil.copytree(previous,release,symlinks=True)
    with tarfile.open(archive,'r:gz') as bundle:
        for member in bundle.getmembers():
            assert (release/member.name).resolve().is_relative_to(release.resolve())
            assert member.isfile() or member.isdir()
            assert member.name.startswith(('backend/app/','backend/alembic/','public/workspace/','public/admin/')) or member.name=='backend/alembic.ini'
        bundle.extractall(release)
    for package in ('app','alembic'):
        for source in (release/'backend'/package).rglob('*.py'):
            ast.parse(source.read_text(encoding='utf-8'))
            source.chmod(0o644)
    for public in (release/'public/workspace',release/'public/admin'):
        for entry in public.rglob('*'):
            if not entry.is_symlink(): entry.chmod(0o755 if entry.is_dir() else 0o644)
    assert hashlib.sha256((release/'model/model.onnx').read_bytes()).hexdigest()=='ff623c94555ade8c08a425caee3fe6fba5465ebc61ebd81ee502376bca8d4773'
    assert current.resolve()==previous
    temporary=root/'.current.user-isolation.next'
    assert not temporary.exists() and not temporary.is_symlink()
    temporary.symlink_to(release,target_is_directory=True)
    os.replace(temporary,current)
    subprocess.run(['systemctl','restart','agriscan-api'],check=True,timeout=45)
    until=time.monotonic()+80
    while True:
        try:
            with urlopen('http://127.0.0.1:18000/api/health',timeout=2) as response:
                health=json.load(response)
            if health=={'status':'ok','database':'connected','redis':'connected','mode':'production','model':'ready'}: break
        except Exception: pass
        if time.monotonic()>until: raise RuntimeError('New ownership API is not healthy; containment retained for repair.')
        time.sleep(1)
    with engine.connect() as db:
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar()=='20261029_06'
        for table in ('plots','detections'):
            inspector=inspect(db)
            assert 'owner_id' in {column['name'] for column in inspector.get_columns(table)}
            constraints=[item for item in inspector.get_foreign_keys(table) if item['constrained_columns']==['owner_id']]
            assert len(constraints)==1 and constraints[0]['referred_table']=='users' and constraints[0]['options']['ondelete']=='SET NULL'
        report['legacy_unknown_detections']=db.execute(text('SELECT count(*) FROM detections WHERE owner_id IS NULL')).scalar()
    after=snapshot()
    assert after==before,'Pre-existing data or integration configuration changed unexpectedly.'
    assert hashlib.sha256(gate.read_bytes()).hexdigest()=='d848ad854f9803d5ca51cdfb101484b6904a4b3f242d9bc27c0f3133c309d691'
    for surface in ('workspace','admin'):
        with urlopen('https://agriscan.ming-ai.top/agriscan/'+surface+'/',timeout=20) as response:
            assert response.read()==(release/'public'/surface/'index.html').read_bytes()
    report.update(status='passed',schema='20261029_06',health=health,preserved_snapshot=after,
                  database_backup=baseline['backup'],requires_account_isolation_verification=True)
except Exception as error:
    # Returning to code without ownership checks would restore the leak.
    # Retain the gate and additive schema for a safe forward repair.
    report.update(status='failed',error_type=type(error).__name__,containment_retained=True)
    raise
finally:
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    report_path.chmod(0o600)
print(json.dumps(report))
