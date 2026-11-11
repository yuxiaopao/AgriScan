"""Read-only public checks; run only after the primary agent confirms activation."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from time import monotonic
from urllib.parse import urljoin

import httpx

root = Path('E:/AgriScan/.runtime/server-latest-20261029')
output = root / 'public-apk-verification.json'
if output.exists():
    shutil.copy2(output,root/'public-apk-verification-attempt1.json')
base = 'https://agriscan.ming-ai.top/agriscan/'
apk_url = base + 'downloads/agriscan-test.apk'
expected = {
    'status': 'ready', 'version': '1.0.3', 'version_code': 4,
    'package_id': 'cn.agriscan.mobile', 'size_bytes': 24146402,
    'sha256': 'c2846e8cba8b8c257db9aa8df1fca70ae32f3e4b91b5b732ab19685dc2d778fa',
    'api_base_url': 'https://agriscan.ming-ai.top/agriscan',
}
report = {'status':'running','started_at':datetime.now(timezone.utc).isoformat(),
          'kind':'read_only_public_apk_verification','tls_verification':True,
          'normal_dns':True,'dns_override':False,'authentication_sent':False,
          'server_mutations':False,'local_download_artifacts_changed':False,'checks':[]}
def check(condition, label):
    if not condition:
        raise RuntimeError(label)
    report['checks'].append(label)

try:
    with httpx.Client(trust_env=False,verify=True,follow_redirects=False,
                      timeout=httpx.Timeout(45,connect=15),
                      headers={'Cache-Control':'no-cache','Accept-Encoding':'identity'}) as client:
        response = client.get(base+'downloads/release.json')
        check(response.status_code == 200,'release.json GET200')
        metadata = response.json()
        check(all(metadata.get(key) == value for key,value in expected.items()),'release metadata matches ready 1.0.3/code4 and verified artifact')
        check(urljoin(base,metadata.get('url','')) == apk_url,'download URL remains on the expected production domain')
        report['release_metadata'] = metadata
        checksum = client.get(base+'downloads/agriscan-test.apk.sha256')
        check(checksum.status_code == 200,'checksum GET200')
        check(checksum.text.split() == [expected['sha256'],'agriscan-test.apk'],'published checksum matches verified new artifact')
        started = monotonic()
        digest, size, next_progress = hashlib.sha256(), 0, 8*1024*1024
        with client.stream('GET',apk_url) as download:
            check(download.status_code == 200,'full APK GET200')
            check(int(download.headers['content-length']) == expected['size_bytes'],'APK Content-Length matches 24,146,402 bytes')
            report['content_type'] = download.headers.get('content-type')
            for chunk in download.iter_bytes(512*1024):
                digest.update(chunk)
                size += len(chunk)
                report['bytes_read'] = size
                report['elapsed_download_seconds'] = round(monotonic()-started,2)
                if size > expected['size_bytes'] or monotonic()-started > 900:
                    raise RuntimeError('Owned public download exceeded expected size or verification deadline.')
                if size >= next_progress:
                    print('Read-only download verified '+str(size)+' bytes',flush=True)
                    next_progress += 8*1024*1024
        check(size == expected['size_bytes'],'complete downloaded APK byte count matches')
        check(digest.hexdigest() == expected['sha256'],'complete downloaded APK SHA256 matches')
        report.update(status='passed',apk_bytes=size,sha256=digest.hexdigest(),
                      elapsed_download_seconds=round(monotonic()-started,2),
                      finished_at=datetime.now(timezone.utc).isoformat())
except Exception as error:
    report.update(status='failed',error_type=type(error).__name__,
                  finished_at=datetime.now(timezone.utc).isoformat())
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    raise
output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:report[key] for key in ('status','apk_bytes','sha256','elapsed_download_seconds')}))
