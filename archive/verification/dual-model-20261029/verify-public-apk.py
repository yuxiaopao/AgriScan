"""Read-only public APK verification; require explicit post-activation invocation."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import monotonic
from urllib.parse import urljoin

import httpx

ROOT=Path(__file__).resolve().parent
OUTPUT=ROOT/'public-apk-verification-final.json'
BASE='https://agriscan.ming-ai.top/agriscan/'
EXPECTED={'status':'ready','version':'1.0.4','version_code':5,'package_id':'cn.agriscan.mobile',
          'size_bytes':24164454,'sha256':'6cbf093162521271ed4fca39aa8e6a3694286653bf13440d056443c210b98026',
          'api_base_url':'https://agriscan.ming-ai.top/agriscan'}


def save(report):
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


def require(condition,code):
    if not condition:
        raise RuntimeError(code)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--after-activation',action='store_true')
    parser.add_argument('--postcheck-only',action='store_true',help='Reuse a recorded complete SHA check and retry only metadata after a transient network failure.')
    args=parser.parse_args()
    if not args.after_activation:
        parser.error('Wait for the primary agent to confirm activation, then explicitly pass --after-activation.')
    if args.postcheck_only:
        report=json.loads(OUTPUT.read_text(encoding='utf-8'))
        require(report.get('complete_apk_verified') is True and report.get('sha256')==EXPECTED['sha256']
                and report.get('apk_bytes')==EXPECTED['size_bytes'],'no_complete_verification_to_reuse')
    else:
        report={'status':'running','started_at':datetime.now(timezone.utc).isoformat(),
                'tls_verification':True,'normal_dns':True,'dns_override':False,'authentication_sent':False,
                'server_mutations':False,'local_download_artifacts_changed':False,'checks':[],
                'transport_errors':[],'download_deadline_seconds':900,'complete_apk_verified':False}
    def checked(condition,label):
        require(condition,label)
        if label not in report['checks']:
            report['checks'].append(label)
    phase='release_metadata'
    try:
        with httpx.Client(trust_env=False,verify=True,follow_redirects=False,
                          timeout=httpx.Timeout(45,connect=15),
                          headers={'Cache-Control':'no-cache','Accept-Encoding':'identity'}) as client:
            def get(relative):
                for attempt in range(3):
                    try:
                        response=client.get(BASE+relative)
                        response.raise_for_status()
                        require(response.status_code==200,'public_http_status_not_200')
                        return response
                    except httpx.TransportError as error:
                        report['transport_errors'].append({'phase':phase,'type':type(error).__name__})
                        if attempt==2:
                            raise
            response=get('downloads/release.json')
            metadata=response.json()
            checked(all(metadata.get(key)==value for key,value in EXPECTED.items()),'ready metadata matches 1.0.4/code5 size SHA and default API')
            checked(urljoin(BASE,metadata.get('url',''))==BASE+'downloads/agriscan-test.apk','download URL stays on expected production path')
            report['release_metadata']=metadata
            if not args.postcheck_only:
                phase='checksum'
                checksum=get('downloads/agriscan-test.apk.sha256')
                checked(checksum.text.split()==[EXPECTED['sha256'],'agriscan-test.apk'],'public checksum file matches artifact')
                phase='complete_download'
                started=monotonic()
                digest,size,next_progress=hashlib.sha256(),0,8*1024*1024
                with client.stream('GET',BASE+'downloads/agriscan-test.apk') as download:
                    checked(download.status_code==200,'complete APK GET200')
                    checked(int(download.headers['content-length'])==EXPECTED['size_bytes'],'APK Content-Length matches final expected bytes')
                    report['content_type']=download.headers.get('content-type')
                    for chunk in download.iter_bytes(512*1024):
                        digest.update(chunk)
                        size+=len(chunk)
                        report['bytes_read']=size
                        report['elapsed_download_seconds']=round(monotonic()-started,2)
                        require(size<=EXPECTED['size_bytes'],'download_exceeded_expected_size')
                        require(monotonic()-started<=900,'local_900_second_verification_deadline')
                        if size>=next_progress:
                            print('READ_ONLY_DOWNLOAD '+str(size)+' bytes',flush=True)
                            next_progress+=8*1024*1024
                            save(report)
                checked(size==EXPECTED['size_bytes'],'complete downloaded byte count matches')
                checked(digest.hexdigest()==EXPECTED['sha256'],'complete downloaded SHA256 matches')
                elapsed=round(monotonic()-started,2)
                report.update(complete_apk_verified=True,apk_bytes=size,sha256=digest.hexdigest(),
                              elapsed_download_seconds=elapsed,average_bytes_per_second=round(size/elapsed,2),
                              average_kib_per_second=round(size/elapsed/1024,2),
                              download_method='single complete GET; streamed SHA256; no synthetic stitching')
                save(report)
            phase='post_download_metadata'
            after=get('downloads/release.json').json()
            checked(after==metadata,'release metadata unchanged after complete download')
            report.update(status='passed',post_download_metadata_rechecked=True,
                          finished_at=datetime.now(timezone.utc).isoformat())
    except Exception as error:
        report.update(status='incomplete_postcheck' if report.get('complete_apk_verified') else 'failed',
                      failure_phase=phase,error_type=type(error).__name__,
                      finished_at=datetime.now(timezone.utc).isoformat())
        save(report)
        print(json.dumps({'status':report['status'],'phase':phase,'error_type':type(error).__name__,'report':str(OUTPUT)}),flush=True)
        return 1
    save(report)
    print(json.dumps({key:report[key] for key in ('status','apk_bytes','sha256','elapsed_download_seconds','average_kib_per_second')}),flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
