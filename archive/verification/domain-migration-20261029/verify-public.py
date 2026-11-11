import hashlib
import json
from pathlib import Path
import re
from datetime import datetime, timezone
import httpx

origin = 'https://agriscan.ming-ai.top'
prefix = origin + '/agriscan'
report = {'domain': 'agriscan.ming-ai.top', 'started_at': datetime.now(timezone.utc).isoformat(),
          'tls_verification': True, 'normal_dns': True, 'checks': []}
target = Path('.runtime/domain-migration-20261029/public.json')
def check(condition, label):
    if not condition:
        raise RuntimeError(label)
    report['checks'].append(label)
def save():
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

token = None
with httpx.Client(trust_env=False, timeout=45, follow_redirects=False) as client:
    def call(method, path, authenticated=True, **kwargs):
        headers = {'Authorization': 'Bearer ' + token} if authenticated and token else {}
        return client.request(method, prefix + path, headers=headers, **kwargs)
    try:
        root = client.get(origin + '/')
        check(root.status_code == 302 and root.headers['location'].endswith('/agriscan/'), 'HTTPS root redirects to official website')
        website = client.get(prefix + '/')
        check(website.status_code == 200 and '<link rel="canonical" href="'+prefix+'/' in website.text, 'public website serves current canonical domain')
        check(call('GET', '/api/health', False).json() == {'status':'ok','database':'connected','redis':'connected','mode':'production','model':'ready'}, 'public production health has database Redis and real model ready')
        check(call('GET', '/api/auth/me', False).status_code == 401, 'anonymous account data remains protected')
        release = client.get(prefix + '/downloads/release.json').json()
        check(release['version'] == '1.0.1' and release['version_code'] == 2 and release['api_base_url'] == prefix, 'public release metadata has new domain and version')
        apk = client.get(prefix + '/downloads/agriscan-test.apk')
        check(apk.status_code == 200 and len(apk.content) == release['size_bytes']
              and hashlib.sha256(apk.content).hexdigest() == release['sha256'], 'full APK HTTPS download matches published size and SHA256')
        report['apk'] = {key:release[key] for key in ('version','version_code','size_bytes','sha256')}
        private = Path('.runtime/server-admin-access.txt').read_text(encoding='utf-8')
        username = re.search(r'^Username:\s*(.+)$', private, re.M).group(1).strip()
        password = re.search(r'^Password:\s*(.+)$', private, re.M).group(1).strip()
        login = call('POST', '/api/auth/login', False, json={'username':username,'password':password})
        private = username = password = None
        check(login.status_code == 200, 'production login works at new public origin')
        token = login.json()['access_token']
        check(call('GET','/api/auth/me').json()['role'] == 'admin', 'authenticated session role retained')
        model = call('GET','/api/models').json()
        check(model['status'] == 'ready' and model['active']['task'] == 'detect'
              and model['active']['onnx_sha256'] == 'ff623c94555ade8c08a425caee3fe6fba5465ebc61ebd81ee502376bca8d4773', 'public authenticated API uses unchanged real detector')
        expected_note = 'domain-migration-20261029-browser-apple'
        rows = call('GET','/api/detections').json()
        owned = [row for row in rows if row.get('note') == expected_note]
        check(len(owned) == 1, 'exact single browser-created migration record found')
        row = owned[0]
        record_path = '/api/detections/' + row['id']
        stored = call('GET', record_path).json()
        check(stored['id'].startswith('6511b82fce2c') and stored['note'] == expected_note
              and stored['crop'] == '苹果' and len(stored['boxes']) == 1, 'browser upload persisted as apple with one real target box')
        image_path = stored['image_url']
        check(image_path.startswith('/api/'), 'owned image uses authenticated API route')
        image = call('GET', image_path)
        check(image.status_code == 200 and image.headers.get('content-type','').startswith('image/'), 'saved detection photo accessible with new origin session')
        check(call('GET',image_path,False).status_code == 401, 'detection photo rejects anonymous access')
        # Only our uniquely named, already inspected browser test record is removed.
        latest = call('GET', record_path).json()
        check(latest['note'] == expected_note and latest['id'] == stored['id'], 'owned test identity rechecked immediately before cleanup')
        check(call('DELETE',record_path).status_code in (200,204), 'owned migration record deleted')
        check(call('GET',record_path).status_code == 404 and call('GET',image_path).status_code == 404, 'owned record and its image removed after verification')
        remaining = call('GET','/api/detections').json()
        check(not any(row.get('note') == expected_note for row in remaining), 'no migration fixture left among business records')
        report['owned_record_id'] = stored['id']
        report['retained_record_count'] = len(remaining)
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error_type'] = type(error).__name__
        save()
        raise
    finally:
        if token:
            response = call('POST','/api/auth/logout')
            report['control_session_revoked'] = response.status_code == 200
        save()
print(json.dumps({'status':report['status'],'checks':len(report['checks']),
                  'control_session_revoked':report.get('control_session_revoked'),
                  'report':str(target)}))
