"""Run on this project's production host; no configuration or user data writes."""
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

root=Path('/srv/agriscan')
archive=root/'bootstrap/llm-assistant-patch-20261029.tar.gz'
expected=sys.argv[1]
assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
current=root/'current'
previous=current.resolve(strict=True)
releases=(root/'releases').resolve(strict=True)
assert current.is_symlink() and previous.is_relative_to(releases)
release=releases/('release-20261029-llm-assistant-'+time.strftime('%H%M%S'))
assert not release.exists()
report={'previous_release':str(previous),'new_release':str(release),'archive_sha256':expected}
target=root/'shared/logs/llm-assistant-deploy-20261029.json'
paths=[Path('/etc/nginx/conf.d/flowly-share.conf'),Path('/etc/nginx/conf.d/zz-agriscan.conf'),
       root/'shared/production.env',Path('/etc/nginx/agriscan-locations.inc')]
def fingerprints():
    return {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
before=fingerprints()
with urlopen('http://127.0.0.1:18000/api/client/config',timeout=10) as response:
    before_config=json.load(response)
next_link=root/'.current.llm-assistant.next'
assert not next_link.exists() and not next_link.is_symlink()
switched=False
def healthy(seconds=60):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        try:
            with urlopen('http://127.0.0.1:18000/api/health',timeout=2) as response:
                data=json.load(response)
            if data=={'status':'ok','database':'connected','redis':'connected','mode':'production','model':'ready'}:
                return data
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError('Production API did not become healthy.')
try:
    shutil.copytree(previous,release,symlinks=True)
    with tarfile.open(archive,'r:gz') as bundle:
        for member in bundle.getmembers():
            destination=(release/member.name).resolve()
            assert destination.is_relative_to(release.resolve()) and (member.isfile() or member.isdir())
            assert member.name.startswith(('backend/app/','public/workspace/','public/admin/'))
        bundle.extractall(release)
    for source in (release/'backend/app').rglob('*.py'):
        ast.parse(source.read_text(encoding='utf-8'))
        source.chmod(0o644)
    for public in (release/'public/workspace',release/'public/admin'):
        for entry in public.rglob('*'):
            if not entry.is_symlink():
                entry.chmod(0o755 if entry.is_dir() else 0o644)
    assert hashlib.sha256((release/'model/model.onnx').read_bytes()).hexdigest()=='ff623c94555ade8c08a425caee3fe6fba5465ebc61ebd81ee502376bca8d4773'
    assert current.resolve()==previous
    next_link.symlink_to(release,target_is_directory=True)
    os.replace(next_link,current)
    switched=True
    subprocess.run(['systemctl','restart','agriscan-api'],check=True,timeout=45)
    report['health']=healthy()
    with urlopen('http://127.0.0.1:18000/openapi.json',timeout=10) as response:
        schema=json.load(response)
    assert '/api/admin/config/llm/test' in schema['paths']
    with urlopen('http://127.0.0.1:18000/api/client/config',timeout=10) as response:
        assert json.load(response)==before_config
    assert fingerprints()==before
    for surface in ('workspace','admin'):
        with urlopen('https://agriscan.ming-ai.top/agriscan/'+surface+'/',timeout=20) as response:
            content=response.read()
        assert content==(release/'public'/surface/'index.html').read_bytes()
    report.update(status='passed',configuration_preserved=True,nginx_and_environment_preserved=True,
                  previous_model_preserved=True,client_config_version=before_config['version'])
except Exception as error:
    report.update(status='failed',error_type=type(error).__name__)
    if switched and current.resolve()==release:
        try:
            next_link.symlink_to(previous,target_is_directory=True)
            os.replace(next_link,current)
            subprocess.run(['systemctl','restart','agriscan-api'],check=True,timeout=45)
            healthy()
            report['rollback']='passed'
        except Exception as rollback_error:
            report['rollback']='failed'
            report['rollback_error_type']=type(rollback_error).__name__
    raise
finally:
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    target.chmod(0o600)
print(json.dumps(report))
