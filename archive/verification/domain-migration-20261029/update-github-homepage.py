import json
import os
from pathlib import Path
import subprocess
import httpx

environment = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never')
result = subprocess.run(['git','credential','fill'], input='protocol=https\nhost=github.com\n\n',
                        text=True, capture_output=True, env=environment, check=True, timeout=45)
values = dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
if not values.get('username') or not values.get('password'):
    raise SystemExit('Existing GitHub credentials unavailable.')
homepage = 'https://agriscan.ming-ai.top/agriscan/'
with httpx.Client(base_url='https://api.github.com',
                  auth=httpx.BasicAuth(values['username'], values['password']),
                  headers={'Accept':'application/vnd.github+json',
                           'X-GitHub-Api-Version':'2022-11-28'}, timeout=45) as client:
    values.clear()
    before = client.get('/repos/yuxiaopao/AgriScan')
    before.raise_for_status()
    check = client.patch('/repos/yuxiaopao/AgriScan', json={'homepage':homepage})
    check.raise_for_status()
    after = client.get('/repos/yuxiaopao/AgriScan')
    after.raise_for_status()
    data = after.json()
    assert data['homepage'] == homepage
    assert data['default_branch'] == before.json()['default_branch']
    assert data['description'] == before.json()['description']
    report = {'status':'passed','repository':data['html_url'],'homepage':data['homepage'],
              'previous_homepage':before.json()['homepage'], 'default_branch':data['default_branch'],
              'description_preserved':True}
    Path('.runtime/domain-migration-20261029/github.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
