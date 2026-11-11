import hashlib
import json
from pathlib import Path
from time import monotonic

import httpx

folder = Path('E:/AgriScan/.runtime/isolation-20261029/apk')
report_path = folder / 'server-publish.json'
report = json.loads(report_path.read_text(encoding='utf-8'))
manifest = json.loads((folder / 'upload-manifest.json').read_text(encoding='utf-8'))
expected = manifest['release']
base = 'https://agriscan.ming-ai.top/agriscan/downloads/'
checked = {'tls_verification':True,'normal_dns':True,'dns_override':False,'origin':base,
           'version':expected['version'],'version_code':expected['version_code']}
with httpx.Client(trust_env=False, verify=True, follow_redirects=False,
                  timeout=httpx.Timeout(45, connect=15), headers={'Cache-Control':'no-cache'}) as client:
    response = client.get(base+'release.json')
    response.raise_for_status()
    assert response.json() == expected
    checked['release_metadata_status'] = response.status_code
    checksum = client.get(base+'agriscan-test.apk.sha256')
    checksum.raise_for_status()
    assert checksum.text.split() == [expected['sha256'],'agriscan-test.apk']
    checked['checksum_status'] = checksum.status_code
    started = monotonic()
    digest = hashlib.sha256()
    size, milestone = 0, 4 * 1024 * 1024
    with client.stream('GET',base+'agriscan-test.apk') as download:
        download.raise_for_status()
        checked['apk_status'] = download.status_code
        checked['content_type'] = download.headers.get('content-type')
        assert int(download.headers['content-length']) == expected['size_bytes']
        for chunk in download.iter_bytes(512 * 1024):
            digest.update(chunk)
            size += len(chunk)
            assert size <= expected['size_bytes']
            assert monotonic() - started < 300, 'Owned download verification exceeded its deadline.'
            if size >= milestone:
                print('Verified download progress: '+str(size)+' bytes',flush=True)
                milestone += 4 * 1024 * 1024
    assert size == expected['size_bytes'] and digest.hexdigest() == expected['sha256']
    checked.update(status='passed',apk_bytes=size,sha256=digest.hexdigest(),
                   download_elapsed_seconds=round(monotonic()-started,2))
for name in ('agriscan-test.apk','agriscan-test.apk.sha256','release.json'):
    assert (folder/'publish-files'/name).read_bytes() == (Path('E:/AgriScan/website/downloads')/name).read_bytes()
report['public_https_verification'] = checked
report['local_downloads_updated'] = True
report['version'] = expected['version']
report['version_code'] = expected['version_code']
report['signer_sha256'] = 'f6229ce48e05aaed0c8889f04f0909c7da7de085ff2b5f98792d6d3a27f710b7'
report['native_runtime_tested'] = False
report['status'] = 'passed'
report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checked))
