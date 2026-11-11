import json
import os
from pathlib import Path
import subprocess

branch = 'codex/workspace-ui-and-plot-management-20261028'
def git(*args, env=None):
    result = subprocess.run(['git', *args], check=True, capture_output=True, text=True,
                            env=env, timeout=90)
    return result.stdout.strip()

assert git('branch','--show-current') == branch
assert not git('status','--porcelain','--untracked-files=no')
git('fetch','origin','main',branch)
base = git('rev-parse','origin/main')
feature = git('rev-parse','HEAD')
assert feature == git('rev-parse','origin/' + branch)
git('merge-base','--is-ancestor',base,feature)
readme = git('rev-parse','HEAD:README.md')
index = Path('.runtime/domain-migration-20261029/main-docs.index').resolve()
assert not index.exists()
environment = dict(os.environ, GIT_INDEX_FILE=str(index))
git('read-tree',base,env=environment)
git('update-index','--add','--cacheinfo','100644,'+readme+',README.md',env=environment)
tree = git('write-tree',env=environment)
assert git('diff','--name-only',base,tree) == 'README.md'
commit = git('commit-tree',tree,'-p',base,'-m','docs: update official production domain')
git('push','origin',commit+':refs/heads/main')
local_main = git('rev-parse','refs/heads/main')
if 'branch refs/heads/main' not in git('worktree','list','--porcelain'):
    assert local_main == base
    git('update-ref','refs/heads/main',commit,local_main)
git('merge','--no-ff',commit,'-m','Merge updated production links from main')
assert git('rev-parse','HEAD^{tree}') == git('rev-parse',feature+'^{tree}')
git('push','origin',branch)
git('merge-base','--is-ancestor','origin/main','HEAD')
assert git('rev-parse','HEAD:README.md') == git('rev-parse','origin/main:README.md')
remote = git('ls-remote','origin','refs/heads/main','refs/heads/'+branch)
report = {'status':'passed','main_readme_commit':commit,'feature_code_commit':feature,
          'feature_merge_commit':git('rev-parse','HEAD'),'branch':branch,
          'main_diff_files':['README.md'],'merge_preserves_feature_tree':True,
          'main_is_feature_ancestor':True,'remote_refs':remote.splitlines()}
Path('.runtime/domain-migration-20261029/git.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
