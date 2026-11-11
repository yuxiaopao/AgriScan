"""Build an index containing this repair, without staging parallel UI designs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

folder=Path('.runtime/isolation-20261029')
base='135c887f521da67da98c5d25ff0a13f659663310'
def git(*args,input_bytes=None,environment=None):
    result=subprocess.run(['git',*args],input=input_bytes,capture_output=True,env=environment,check=True)
    return result.stdout.decode('utf-8').strip()
assert git('rev-parse','HEAD')==base
assert git('branch','--show-current')=='codex/workspace-ui-and-plot-management-20261028'
suite=ET.parse('.runtime/pytest-user-isolation-final.xml').getroot().find('testsuite')
assert int(suite.attrib['failures'])==0 and int(suite.attrib['errors'])==0
assert int(suite.attrib['tests'])==255 and int(suite.attrib['skipped'])==1
for report in ('production-preflight.json','production-public.json','cleanup.json','deployment.json'):
    assert json.loads((folder/report).read_text(encoding='utf-8'))['status']=='passed'
sources={}
manifest=json.loads((folder/'patch-manifest.json').read_text(encoding='utf-8'))
for name,digest in manifest['files'].items():
    if name.startswith('backend/'):
        source=Path(name)
        assert hashlib.sha256(source.read_bytes()).hexdigest()==digest,name
        sources[name]=source
ui=json.loads((folder/'ui-builds.json').read_text(encoding='utf-8'))
for name,digest in ui['source_files'].items():
    source=folder/'owned-ui'/name
    if not source.exists(): source=folder/'owned-network'/name
    assert hashlib.sha256(source.read_bytes()).hexdigest()==digest,name
    sources[name]=source
for name in ('test_admin','test_api','test_assistant','test_auto_crop_assistant','test_detection_inference',
             'test_extensions','test_import_legacy','test_inference','test_media','test_migrations','test_plots',
             'test_user_isolation','migration_helpers'):
    path='backend/tests/'+name+'.py'
    assert Path(path).is_file()
    sources[path]=Path(path)
for name in ('backend/README.md','docs/client-and-admin.md','docs/deepseek-assistant-20261029.md',
             'docs/user-isolation-20261029.md','deploy/README.md','deploy/verify-server-readonly.py',
             'mobile/README.md','mobile/android/app/build.gradle','website/downloads/release.json',
             'website/downloads/agriscan-test.apk.sha256','design/qa-20261029/user-isolation-a.png',
             'design/qa-20261029/user-isolation-b.png','design/qa-20261029/user-isolation-admin.png'):
    assert Path(name).is_file(),name
    sources[name]=Path(name)
sources['website/index.html']=folder/'owned-document/website/index.html'
index=(folder/'repair.index').resolve()
assert not index.exists()
environment=dict(os.environ,GIT_INDEX_FILE=str(index))
git('read-tree',base,environment=environment)
blobs={}
for name,source in sorted(sources.items()):
    assert not name.startswith('.runtime/') and not name.endswith(('.env','.apk','.keystore'))
    blob=git('hash-object','-w','--path='+name,str(source))
    git('update-index','--add','--cacheinfo','100644,'+blob+','+name,environment=environment)
    blobs[name]=blob
tree=git('write-tree',environment=environment)
git('diff','--check',base,tree)
changed=git('diff','--name-only',base,tree).splitlines()
assert set(changed).issubset(sources)
assert 'admin/src/RuntimeSettings.tsx' not in changed and 'website/app.js' not in changed
report={'status':'prepared','base':base,'tree':tree,'index':str(index),'blobs':blobs,'changed':changed,
        'excluded_parallel_design':True}
(folder/'commit-plan.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'status':'prepared','changed_files':len(changed),'tree':tree,'files':changed}))
