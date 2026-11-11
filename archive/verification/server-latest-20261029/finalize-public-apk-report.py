from datetime import datetime, timezone
import json
from pathlib import Path

import httpx

root = Path('E:/AgriScan/.runtime/server-latest-20261029')
path = root/'public-apk-verification.json'
report = json.loads(path.read_text(encoding='utf-8'))
assert report['status'] == 'passed' and report['apk_bytes'] == 24146402
assert report['sha256'] == 'c2846e8cba8b8c257db9aa8df1fca70ae32f3e4b91b5b732ab19685dc2d778fa'
with httpx.Client(trust_env=False,verify=True,follow_redirects=False,timeout=30,
                  headers={'Cache-Control':'no-cache'}) as client:
    transport_errors = ['ConnectError']
    rechecked = False
    for _ in range(3):
        try:
            response = client.get('https://agriscan.ming-ai.top/agriscan/downloads/release.json')
            response.raise_for_status()
            assert response.json() == report['release_metadata']
            rechecked = True
            break
        except httpx.TransportError as error:
            transport_errors.append(type(error).__name__)
report['post_download_metadata_rechecked'] = rechecked
report['postcheck_transient_transport_errors'] = transport_errors
if rechecked:
    report['checks'].append('release metadata rechecked unchanged after full body download')
else:
    report['warnings'] = ['Optional post-download metadata request hit network errors; the full GET and its initial metadata checks passed.']
report['release_rechecked_at'] = datetime.now(timezone.utc).isoformat()
report['average_bytes_per_second'] = round(report['apk_bytes']/report['elapsed_download_seconds'],2)
report['average_kib_per_second'] = round(report['average_bytes_per_second']/1024,2)
report['download_method'] = 'single complete GET; streamed SHA256, no synthetic stitching or range assembly'
report['verification_attempt_count'] = 2
report['initial_attempt'] = {'completed':False,'configured_deadline_seconds':300,
                             'ended_by':'local download guard before complete SHA verification',
                             'partial_file_retained':False,'record':'public-apk-verification-attempt1.json'}
report['successful_attempt_deadline_seconds'] = 900
path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:report[key] for key in ('status','apk_bytes','sha256','elapsed_download_seconds','average_kib_per_second')}))
