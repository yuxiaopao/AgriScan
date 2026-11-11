from datetime import datetime, timezone
import hashlib
import json
from urllib.parse import urljoin
import httpx

base = 'https://agriscan.ming-ai.top/agriscan/'
expected = 'ab5ed73430cc0aea17b403377ede3f3d7e686cef2346b94aed1cc4d9e7d93f85'
report = {'source': 'Production-server ordinary DNS HTTPS requests with certificate verification; no APP or browser interaction',
          'origin': base, 'tlsVerification': True, 'dnsOverride': False, 'checkedAt': datetime.now(timezone.utc).isoformat()}
with httpx.Client(timeout=120, trust_env=False, follow_redirects=False) as client:
    response = client.get(urljoin(base, 'downloads/release.json'), headers={'Cache-Control': 'no-cache'})
    assert response.status_code == 200
    release = response.json()
    assert release['status'] == 'ready' and release['version'] == '1.0.1' and release['version_code'] == 2
    assert release['api_base_url'] == base.rstrip('/') and release['sha256'] == expected
    report['release'] = {'status': response.status_code, 'metadata': release}
    digest, count = hashlib.sha256(), 0
    with client.stream('GET', urljoin(base, release['url'])) as apk:
        assert apk.status_code == 200
        for block in apk.iter_bytes():
            digest.update(block)
            count += len(block)
        report['download'] = {'status': apk.status_code, 'bytes': count, 'sha256': digest.hexdigest(), 'contentType': apk.headers.get('content-type')}
    assert digest.hexdigest() == expected and count == release['size_bytes'] == 18744600
    checksum = client.get(urljoin(base, 'downloads/agriscan-test.apk.sha256'))
    assert checksum.status_code == 200 and checksum.text.split()[0] == expected
    report['checksum'] = {'status': checksum.status_code, 'matches': True}
    preflight = client.options(urljoin(base, 'api/auth/login'), headers={
        'Origin': 'https://localhost', 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'})
    assert preflight.status_code == 200 and preflight.headers.get('access-control-allow-origin') == 'https://localhost'
    report['capacitorOriginPreflight'] = {'status': preflight.status_code, 'origin': 'https://localhost',
                                        'allowOrigin': preflight.headers.get('access-control-allow-origin')}
    health = client.get(urljoin(base, 'api/health'), headers={'Origin': 'https://localhost'})
    assert health.status_code == 200 and health.headers.get('access-control-allow-origin') == 'https://localhost'
    assert health.json()['model'] == 'ready'
    report['apiHealth'] = {'status': health.status_code, 'data': health.json(), 'allowOrigin': health.headers.get('access-control-allow-origin')}
report['status'] = 'passed'
print(json.dumps(report, ensure_ascii=False))
