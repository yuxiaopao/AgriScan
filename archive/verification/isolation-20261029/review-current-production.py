"""Read-only release, source hashes, schema revision and public artifact inventory."""
import hashlib,json,subprocess
from pathlib import Path

root=Path(__file__).resolve().parents[2]
revision='7ad3794'
def git(*args):return subprocess.run(['git',*args],cwd=root,check=True,capture_output=True).stdout
paths=[path for path in git('ls-tree','-r','--name-only',revision,'--','backend').decode().splitlines()
       if (path.startswith(('backend/app/','backend/alembic/')) and path.endswith('.py'))
       or path in ['backend/alembic.ini','backend/requirements.txt','backend/requirements-inference.txt','backend/requirements-media.txt']]
commit_hashes={}
for path in paths:
    data=git('show',revision+':'+path)
    commit_hashes[path]={'sha256':hashlib.sha256(data).hexdigest(),'normalized_sha256':hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()}
remote=r'''
import hashlib,json,re,subprocess
from pathlib import Path
from urllib.request import urlopen
from datetime import datetime,timezone
paths=PATHS
current=Path('/srv/agriscan/current').resolve()
report={'checked_at':datetime.now(timezone.utc).isoformat(),'release':str(current),'services':{},'backend_files':{},'entries':{}}
def file_hash(path):
    data=path.read_bytes()
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'normalized_sha256':hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest()}
for unit in ['agriscan-api','agriscan-redis','mysqld','nginx']:
    result=subprocess.run(['systemctl','show',unit,'--property=ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestamp'],capture_output=True,text=True,check=True)
    report['services'][unit]=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
for relative in paths:
    target=current/relative
    report['backend_files'][relative]=file_hash(target) if target.is_file() else None
public=current/'public'
for surface,relative in [('website','index.html'),('workspace','workspace/index.html'),('admin','admin/index.html')]:
    path=public/relative
    entry={'path':str(path),'file':file_hash(path),'assets':{}}
    html=path.read_text(encoding='utf-8')
    for value in re.findall(r'(?:src|href)=[\'\"]([^\'\"]+)[\'\"]',html):
        if not value.split('?',1)[0].endswith(('.js','.css')):continue
        if value.startswith('/agriscan/'):
            asset=public/value.removeprefix('/agriscan/').split('?',1)[0]
        elif value.startswith(('https:','http:','data:')):continue
        else:asset=path.parent/value.split('?',1)[0]
        asset=asset.resolve()
        if not asset.is_relative_to(public.resolve()):raise RuntimeError('Asset path escaped public directory')
        entry['assets'][str(asset.relative_to(public))]=file_hash(asset) if asset.is_file() else None
    report['entries'][surface]=entry
release=public/'downloads/release.json'
report['download_release']=json.loads(release.read_text(encoding='utf-8'))
report['download_release_file']=file_hash(release)
report['apk_file']=file_hash(public/'downloads/agriscan-test.apk')
with urlopen('http://127.0.0.1:18000/api/health',timeout=15) as response:report['health']=json.load(response)
schema=subprocess.run(['mysql','--batch','--skip-column-names','--execute','SELECT version_num FROM agriscan.alembic_version;'],capture_output=True,text=True,check=True,timeout=15)
report['schema_revision']=schema.stdout.strip()
report['release_stable_during_read']=Path('/srv/agriscan/current').resolve()==current
print(json.dumps(report))
'''.replace('PATHS',repr(paths))
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','python3 -'],
                      input=remote,text=True,capture_output=True,timeout=90)
if result.returncode:raise SystemExit('Read-only metadata/hash inspection failed; private stderr was not printed.')
server=json.loads(result.stdout)
comparison=[]
for path,expected in commit_hashes.items():
    actual=server['backend_files'].get(path)
    comparison.append({'path':path,'exists':actual is not None,'exact':bool(actual and actual['sha256']==expected['sha256']),
                       'content_equal':bool(actual and actual['normalized_sha256']==expected['normalized_sha256'])})
report={'status':'passed' if server['release_stable_during_read'] and all(row['content_equal'] for row in comparison) else 'mismatch',
        'compared_commit':git('rev-parse',revision).decode().strip(),'backend_comparison':comparison,
        'server':server,'local_uncommitted_backend_diff':git('diff','--name-only',revision,'--','backend').decode().splitlines()}
target=Path(__file__).resolve().parent/'production-version-review.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'release':server['release'],'stable':server['release_stable_during_read'],
                  'backend_files':len(comparison),'exact_matches':sum(row['exact'] for row in comparison),
                  'content_matches':sum(row['content_equal'] for row in comparison),'mismatch_files':[row['path'] for row in comparison if not row['content_equal']],
                  'schema':server['schema_revision'],'health':server['health'],'download_version':server['download_release']['version'],
                  'download_version_code':server['download_release']['version_code'],'report':str(target)}))
