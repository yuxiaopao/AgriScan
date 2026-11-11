import json
import os
from pathlib import Path
import subprocess

folder=Path('.runtime/isolation-20261029')
plan=json.loads((folder/'commit-plan.json').read_text(encoding='utf-8'))
branch='codex/workspace-ui-and-plot-management-20261028'
def run(*args,environment=None,input_bytes=None):
    result=subprocess.run(['git',*args],env=environment,input=input_bytes,
                          capture_output=True,check=True,timeout=120)
    return result.stdout.decode('utf-8').strip()
assert run('rev-parse','HEAD')==plan['base']
assert run('branch','--show-current')==branch
assert not run('diff','--cached','--name-only'),'Another task has staged changes; preserve its index.'
environment=dict(os.environ,GIT_INDEX_FILE=plan['index'])
assert run('write-tree',environment=environment)==plan['tree']
run('commit','-m','fix(auth): isolate personal detections plots and history',environment=environment)
commit=run('rev-parse','HEAD')
assert run('rev-parse','HEAD^{tree}')==plan['tree']
# Only synchronize this repair's entries in the default index. Parallel working
# files are never checked out, reset or overwritten.
entries=''.join('100644 '+blob+'\t'+name+'\n' for name,blob in sorted(plan['blobs'].items())).encode()
run('update-index','--index-info',input_bytes=entries)
assert not run('diff','--cached','--name-only')
run('push','origin',branch)
remote=run('ls-remote','origin','refs/heads/'+branch)
assert remote.split()[0]==commit
report={'status':'passed','commit':commit,'branch':branch,'files':len(plan['changed']),
        'parallel_working_files_preserved':True,'remote':remote}
(folder/'git.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
