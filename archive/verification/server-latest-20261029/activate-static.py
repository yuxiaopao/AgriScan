"""Server-side atomic static release; no API restart or database mutation."""
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

root=Path('/srv/agriscan')
archive=root/'bootstrap/latest-full-ui-20261029.tar.gz'
expected,release_id,manifest_sha=sys.argv[1:4]
assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
assert release_id.startswith('release-20261029-full-ui-') and '/' not in release_id
current=root/'current'
previous=current.resolve(strict=True)
assert previous==root/'releases/release-20261029-user-isolation-104127'
release=root/'releases'/release_id
assert release.parent==root/'releases' and not release.exists()
conf=Path('/etc/nginx/agriscan-locations.inc')
old_conf=conf.read_bytes()
old_conf_sha=hashlib.sha256(old_conf).hexdigest()
assert old_conf_sha=='c5b9642a387c621f74d48f3ef0d3ad882f3a4df32b4c926ae8b244b93a531d9d'
backup=root/'shared/backups'/release_id
backup.mkdir(mode=0o700)
(backup/'nginx-locations.before').write_bytes(old_conf)
(backup/'nginx-locations.before').chmod(0o600)
(backup/'previous-release.txt').write_text(str(previous))
report={'previous_release':str(previous),'new_release':str(release),'archive_sha256':expected,
        'database_writes':False,'api_restarted':False,'backup':str(backup)}
report_path=root/'shared/logs'/(release_id+'.json')
switched=False
changed_conf=False
new_conf_sha=None

def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def replace_conf(content):
    temporary=conf.with_name('.agriscan-locations.'+release_id+'.next')
    assert not temporary.exists()
    try:
        with temporary.open('xb') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o644)
        os.replace(temporary,conf)
    finally:
        if temporary.exists(): temporary.unlink()
def backend_tree(path):
    return {p.relative_to(path).as_posix():sha(p) for p in path.rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
def service():
    return subprocess.check_output(['systemctl','show','agriscan-api','-p','MainPID','-p','NRestarts',
                                    '-p','ExecMainStartTimestamp','-p','ActiveState'],text=True).strip()
def get(url):
    for attempt in range(3):
        try:
            with urlopen(url,timeout=25) as response:
                return response.read(),dict(response.headers)
        except Exception:
            if attempt==2: raise
            time.sleep(1)
before_service=service()
assert 'ActiveState=active' in before_service
before_backend=backend_tree(previous/'backend')
before_env=sha(root/'shared/production.env')
before_vhost=sha(Path('/etc/nginx/conf.d/zz-agriscan.conf'))
try:
    shutil.copytree(previous,release,symlinks=True)
    public=release/'public'
    assert public.parent==release and not public.is_symlink()
    shutil.rmtree(public)
    public.mkdir(mode=0o755)
    with tarfile.open(archive,'r:gz') as bundle:
        for member in bundle.getmembers():
            assert (release/member.name).resolve().is_relative_to(release.resolve())
            assert member.isfile()
            assert member.name.startswith('public/') or member.name in (
                'ops/agriscan-locations.inc','release-info.json','payload-files.json')
        bundle.extractall(release)
    assert sha(release/'payload-files.json')==manifest_sha
    manifest=json.loads((release/'payload-files.json').read_text())
    for name,digest in manifest.items():
        assert (release/name).resolve().is_relative_to(release.resolve())
        assert sha(release/name)==digest,name
    retained_assets=0
    for surface in ('workspace','admin'):
        old_assets=previous/'public'/surface/'assets'
        for old_file in old_assets.rglob('*'):
            if old_file.is_file():
                assert not old_file.is_symlink()
                target=public/surface/'assets'/old_file.relative_to(old_assets)
                if target.exists():
                    assert sha(target)==sha(old_file)
                else:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(old_file,target)
                    retained_assets+=1
    info=json.loads((release/'release-info.json').read_text())
    assert info['release_id']==release_id and info['database_migration_required'] is False
    apk=public/'downloads/agriscan-test.apk'
    download=json.loads((public/'downloads/release.json').read_text())
    assert download['version']=='1.0.3' and download['version_code']==4
    assert sha(apk)==info['apk']['sha256']==download['sha256']
    assert apk.stat().st_size==info['apk']['apk_bytes']
    assert backend_tree(release/'backend')==before_backend
    assert sha(release/'model/model.onnx')=='ff623c94555ade8c08a425caee3fe6fba5465ebc61ebd81ee502376bca8d4773'
    for entry in public.rglob('*'):
        assert not entry.is_symlink()
        entry.chmod(0o755 if entry.is_dir() else 0o644)
    new_conf=(release/'ops/agriscan-locations.inc').read_bytes()
    new_conf_sha=hashlib.sha256(new_conf).hexdigest()
    assert sha(conf)==old_conf_sha
    changed_conf=True
    replace_conf(new_conf)
    subprocess.run(['nginx','-t'],check=True,timeout=20,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert current.resolve()==previous
    temporary=root/'.current.latest-full-ui.next'
    assert not temporary.exists() and not temporary.is_symlink()
    temporary.symlink_to(release,target_is_directory=True)
    os.replace(temporary,current)
    switched=True
    subprocess.run(['systemctl','reload','nginx'],check=True,timeout=30)
    base='https://agriscan.ming-ai.top/agriscan/'
    checks={}
    for path in ('index.html','app.js','style.css','workspace/index.html','admin/index.html','downloads/release.json'):
        content,headers=get(base+path)
        assert content==(public/path).read_bytes(),path
        checks[path]={'status':200,'sha256':hashlib.sha256(content).hexdigest(),'cache_control':headers.get('Cache-Control')}
    for path in ('index.html','app.js','style.css','workspace/index.html','admin/index.html'):
        assert 'no-cache' in checks[path]['cache_control'],path
    for entry in info['workspace_entries']+info['admin_entries']:
        content,_=get('https://agriscan.ming-ai.top'+entry)
        assert content==(public/entry[len('/agriscan/'):]).read_bytes()
        checks[entry]={'status':200,'sha256':hashlib.sha256(content).hexdigest()}
    health=json.loads(get('http://127.0.0.1:18000/api/health')[0])
    assert health=={'status':'ok','database':'connected','redis':'connected','mode':'production','model':'ready'}
    assert service()==before_service
    assert sha(root/'shared/production.env')==before_env
    assert sha(Path('/etc/nginx/conf.d/zz-agriscan.conf'))==before_vhost
    assert current.resolve()==release
    report.update(status='passed',release_id=release_id,source_tree_sha256=info['source_tree_sha256'],
                  payload_files_verified=len(manifest),backend_files_unchanged=len(before_backend),
                  retained_previous_hashed_assets=retained_assets,
                  configuration_file_unchanged=True,old_domain_vhost_unchanged=True,
                  service_unchanged=True,service=before_service,health=health,public_checks=checks,apk=info['apk'])
except Exception as error:
    report.update(status='failed',error_type=type(error).__name__,rollback_errors=[])
    try:
        if switched and current.resolve()==release:
            rollback=root/'.current.latest-full-ui.rollback'
            assert not rollback.exists() and not rollback.is_symlink()
            rollback.symlink_to(previous,target_is_directory=True)
            os.replace(rollback,current)
    except Exception as rollback_error:
        report['rollback_errors'].append({'step':'release_pointer','type':type(rollback_error).__name__})
    try:
        if changed_conf and sha(conf)==new_conf_sha:
            replace_conf(old_conf)
            subprocess.run(['nginx','-t'],check=True,timeout=20,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            subprocess.run(['systemctl','reload','nginx'],check=True,timeout=30)
    except Exception as rollback_error:
        report['rollback_errors'].append({'step':'nginx_configuration','type':type(rollback_error).__name__})
    try:
        rollback_health=json.loads(get('http://127.0.0.1:18000/api/health')[0])
        report['rolled_back']=(not report['rollback_errors'] and current.resolve()==previous and sha(conf)==old_conf_sha
                               and rollback_health.get('status')=='ok')
    except Exception as rollback_error:
        report['rolled_back']=False
        report['rollback_errors'].append({'step':'rollback_validation','type':type(rollback_error).__name__})
    raise
finally:
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    report_path.chmod(0o600)
    print(json.dumps(report),flush=True)
