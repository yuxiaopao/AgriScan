from pathlib import Path
import json
import secrets
import httpx

ROOT = Path('E:/AgriScan')
RUN = 'qa20261028_1935'
folder = ROOT / '.runtime/qa-comprehensive'
folder.mkdir(exist_ok=True)
path = folder / 'fixtures-private.json'
if path.exists():
    raise SystemExit('Fixtures already recorded; reuse or clean them rather than duplicating.')
access = dict(line.split(': ', 1) for line in (ROOT / '.runtime/server-admin-access.txt').read_text().splitlines() if ': ' in line)
client = httpx.Client(base_url='http://127.0.0.1:5180/agriscan/api', timeout=90)
response = client.post('/auth/login', json={'username': access['Username'], 'password': access['Password']})
response.raise_for_status()
client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
baseline = {'config': client.get('/admin/config').json(),
            'users': client.get('/admin/users?page_size=100').json(),
            'plots': client.get('/plots').json(), 'detections': client.get('/detections').json(),
            'articles': client.get('/admin/knowledge?page_size=100').json()}
(folder / 'baseline.json').write_text(json.dumps(baseline, ensure_ascii=False, indent=2), encoding='utf8')
state = {'run_id': RUN, 'users': [], 'plots': [], 'detections': [], 'articles': []}
path.write_text(json.dumps(state, indent=2), encoding='utf8')
for suffix, active in [('member', True), ('disabled', False)]:
    body = {'username': RUN + '_' + suffix, 'name': RUN + ' ' + suffix,
            'password': secrets.token_urlsafe(18), 'role': 'member', 'is_active': active}
    response = client.post('/admin/users', json=body)
    response.raise_for_status()
    state['users'].append({**body, 'id': response.json()['id']})
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf8')
client.post('/auth/logout').raise_for_status()
print('Recorded baseline and created two uniquely named member fixtures; no credentials printed.')
