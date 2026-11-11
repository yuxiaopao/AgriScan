"""Apply the verified tiny website delta to a complete static release copy."""
import hashlib,json,os,shutil,subprocess,sys,tarfile
from pathlib import Path
from urllib.request import urlopen
from urllib.parse import urlsplit

root=Path('/srv/agriscan')
archive=root/'bootstrap/latest-website-cachefix-20261029.tar.gz'
archive_sha,manifest_sha,release_id=sys.argv[1:4]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(archive)==archive_sha
assert release_id.startswith('release-20261029-full-ui-') and '/' not in release_id
current=root/'current'
previous=current.resolve(strict=True)
assert previous==root/'releases/release-20261029-full-ui-131640'
release=root/'releases'/release_id
assert release.parent==root/'releases' and not release.exists()
def service():
    return subprocess.check_output(['systemctl','show','agriscan-api','-p','MainPID','-p','NRestarts',
                                    '-p','ExecMainStartTimestamp','-p','ActiveState'],text=True).strip()
def get(url):
    with urlopen(url,timeout=25) as response:return response.read(),dict(response.headers)
before_service=service()
before_env=sha(root/'shared/production.env')
before_conf=sha(Path('/etc/nginx/agriscan-locations.inc'))
before_vhost=sha(Path('/etc/nginx/conf.d/zz-agriscan.conf'))
report={'previous_release':str(previous),'new_release':str(release),'database_writes':False,
        'api_restarted':False,'nginx_configuration_changed':False,'nginx_reloaded':False}
switched=False
try:
    shutil.copytree(previous,release,symlinks=True)
    with tarfile.open(archive,'r:gz') as bundle:
        members=bundle.getmembers()
        assert {m.name for m in members}=={'public/index.html','release-info.json','payload-files.json'}
        for member in members:
            assert member.isfile() and (release/member.name).resolve().is_relative_to(release.resolve())
        bundle.extractall(release)
    assert sha(release/'payload-files.json')==manifest_sha
    manifest=json.loads((release/'payload-files.json').read_text())
    for name,digest in manifest.items():
        assert (release/name).resolve().is_relative_to(release.resolve())
        assert sha(release/name)==digest,name
    info=json.loads((release/'release-info.json').read_text())
    assert info['release_id']==release_id
    assert sha(release/'public/downloads/agriscan-test.apk')==info['apk']['sha256']
    assert sha(release/'public/downloads/agriscan-test.apk')==sha(previous/'public/downloads/agriscan-test.apk')
    for name in ('public/index.html','release-info.json','payload-files.json'):(release/name).chmod(0o644)
    assert current.resolve()==previous
    temporary=root/'.current.latest-cachefix.next'
    assert not temporary.exists() and not temporary.is_symlink()
    temporary.symlink_to(release,target_is_directory=True)
    os.replace(temporary,current)
    switched=True
    base='https://agriscan.ming-ai.top/agriscan/'
    content,headers=get(base+'index.html')
    assert content==(release/'public/index.html').read_bytes()
    assert 'no-cache' in headers.get('Cache-Control','')
    import re
    script=re.search(r'src="(\./app\.js\?v=[a-f0-9]+)"',content.decode()).group(1)
    style=re.search(r'href="(\./style\.css\?v=[a-f0-9]+)"',content.decode()).group(1)
    for reference in (script,style):
        response,asset_headers=get(base+reference[2:])
        path=urlsplit(reference).path[2:]
        assert response==(release/'public'/path).read_bytes()
        assert 'no-cache' in asset_headers.get('Cache-Control','')
        assert reference.split('?v=')[1]==sha(release/'public'/path)[:12]
    for path in ('workspace/index.html','admin/index.html','downloads/release.json'):
        assert get(base+path)[0]==(release/'public'/path).read_bytes()
    health=json.loads(get('http://127.0.0.1:18000/api/health')[0])
    assert health['status']=='ok' and health['model']=='ready'
    assert service()==before_service
    assert sha(root/'shared/production.env')==before_env
    assert sha(Path('/etc/nginx/agriscan-locations.inc'))==before_conf
    assert sha(Path('/etc/nginx/conf.d/zz-agriscan.conf'))==before_vhost
    report.update(status='passed',release_id=release_id,source_tree_sha256=info['source_tree_sha256'],
                  source_file_count=info['source_file_count'],payload_files_verified=len(manifest),
                  versioned_script=script,versioned_style=style,apk_unchanged=True,
                  service_unchanged=True,health=health)
except Exception as error:
    report.update(status='failed',error_type=type(error).__name__,rollback_errors=[])
    try:
        if switched and current.resolve()==release:
            temporary=root/'.current.latest-cachefix.rollback'
            assert not temporary.exists() and not temporary.is_symlink()
            temporary.symlink_to(previous,target_is_directory=True)
            os.replace(temporary,current)
        old_home,_=get('https://agriscan.ming-ai.top/agriscan/index.html')
        rollback_health=json.loads(get('http://127.0.0.1:18000/api/health')[0])
        report['rolled_back']=(current.resolve()==previous and old_home==(previous/'public/index.html').read_bytes()
                               and rollback_health.get('status')=='ok')
    except Exception as rollback_error:
        report['rolled_back']=False
        report['rollback_errors'].append(type(rollback_error).__name__)
    raise
finally:
    log=root/'shared/logs'/(release_id+'.json')
    log.write_text(json.dumps(report,indent=2),encoding='utf-8')
    log.chmod(0o600)
    print(json.dumps(report),flush=True)
