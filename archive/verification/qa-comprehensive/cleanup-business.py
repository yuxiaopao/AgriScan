from pathlib import Path
import hashlib
import json
import secrets
import httpx

folder = Path('E:/AgriScan/.runtime/qa-comprehensive')
state = json.loads((folder / 'fixtures-private.json').read_text(encoding='utf8'))
baseline = json.loads((folder / 'baseline.json').read_text(encoding='utf8'))
prefix = state['run_id']
access = dict(line.split(': ', 1) for line in Path('E:/AgriScan/.runtime/server-admin-access.txt').read_text().splitlines() if ': ' in line)
client = httpx.Client(base_url='http://127.0.0.1:5180/agriscan/api', timeout=90)
response = client.post('/auth/login', json={'username': access['Username'], 'password': access['Password']})
response.raise_for_status()
client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
report = {'transport': 'Actual production API over TLS-verified SSH transport; cleanup only', 'detections': [], 'plots': []}
try:
    config = client.get('/admin/config'); config.raise_for_status(); config = config.json()
    assert config['version'] == 5, 'Unexpected config revision: do not overwrite another actor.'
    assert {k:v for k,v in config.items() if k != 'version'} == {k:v for k,v in baseline['config'].items() if k != 'version'}, 'Configuration was not restored.'
    report['baseline_config_restored'] = True
    report['config_version'] = config['version']
    rows = client.get('/admin/detections', params={'search': prefix, 'page_size': 100}); rows.raise_for_status()
    rows = rows.json()['items']
    assert len(rows) == 4, f'Expected exactly 4 owned positive fixtures, found {len(rows)}'
    assert all(prefix in row['name'] or prefix in row['note'] for row in rows)
    assert len({row['id'] for row in rows}) == 4
    plots = client.get('/plots'); plots.raise_for_status()
    plots = [row for row in plots.json() if row['name'] == prefix + '_apple']
    assert len(plots) == 1
    report['positive_results'] = [{k: row.get(k) for k in ['id','name','crop','result','confidence','boxes','prediction_model']} for row in rows]
    (folder / 'cleanup-before.json').write_text(json.dumps({'detections': rows, 'plots': plots}, ensure_ascii=False, indent=2), encoding='utf8')
    state['detections'] = [{'id': row['id']} for row in rows]
    state['plots'] = [{'id': row['id'], 'name': row['name']} for row in plots]
    (folder / 'fixtures-private.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf8')
    print('Exact QA objects and restored production configuration verified.', flush=True)
    member = next(user for user in state['users'] if user['username'] == prefix + '_member')
    session = httpx.Client(base_url=str(client.base_url), timeout=90)
    old_login = session.post('/auth/login', json={'username': member['username'], 'password': member['password']})
    old_login.raise_for_status()
    session.headers['Authorization'] = 'Bearer ' + old_login.json()['access_token']
    replacement = secrets.token_urlsafe(20)
    reset = client.post('/admin/users/' + member['id'] + '/password', json={'password': replacement})
    reset.raise_for_status()
    assert session.get('/auth/me').status_code == 401
    assert session.post('/auth/login', json={'username': member['username'], 'password': member['password']}).status_code == 401
    fresh = session.post('/auth/login', json={'username': member['username'], 'password': replacement})
    fresh.raise_for_status()
    session.headers['Authorization'] = 'Bearer ' + fresh.json()['access_token']
    disabled = client.patch('/admin/users/' + member['id'], json={'is_active': False})
    disabled.raise_for_status()
    assert session.get('/auth/me').status_code == 401
    assert session.post('/auth/login', json={'username': member['username'], 'password': replacement}).status_code == 401
    report['fixture_password_reset_and_disable'] = {'reset_status': reset.status_code, 'old_session': 401, 'old_password': 401, 'new_login': 200, 'disable_status': disabled.status_code, 'disabled_session': 401, 'disabled_login': 401}
    print('Own QA account password reset and disable revoke old sessions as expected.', flush=True)
    for row in rows:
        image_path = row['image_url'].removeprefix('/api')
        image = client.get(image_path); image.raise_for_status()
        deleted = client.delete('/detections/' + row['id']); deleted.raise_for_status()
        after = client.get(image_path)
        assert after.status_code == 404
        report['detections'].append({'id': row['id'], 'deleted': deleted.status_code, 'image_after_delete': after.status_code, 'image_sha256': hashlib.sha256(image.content).hexdigest()})
        print('Removed one exact QA detection and verified its image is unavailable.', flush=True)
    for plot in plots:
        deleted = client.delete('/plots/' + plot['id']); deleted.raise_for_status()
        report['plots'].append({'id': plot['id'], 'deleted': deleted.status_code})
    remaining = client.get('/admin/detections', params={'search': prefix, 'page_size': 100}); remaining.raise_for_status()
    assert remaining.json()['total'] == 0
    remaining_plots = client.get('/plots'); remaining_plots.raise_for_status()
    assert not any(row['name'].startswith(prefix) for row in remaining_plots.json())
    final_config = client.get('/admin/config'); final_config.raise_for_status()
    assert final_config.json() == config
    report['passed'] = True
finally:
    report['logout_status'] = client.post('/auth/logout').status_code
    (folder / 'cleanup-business.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
print('Owned detection/plot cleanup complete; config unchanged and control session revoked.', flush=True)
