import hashlib,json,re,subprocess,zipfile
from pathlib import Path
from urllib.parse import urljoin,urlsplit
from datetime import datetime,timezone
import httpx

folder=Path(__file__).resolve().parent
before=json.loads((folder/'readonly-runtime-before.json').read_text())
after=json.loads((folder/'readonly-runtime-after.json').read_text())
info=json.loads((folder/'release-info.json').read_text())
manifest=json.loads((folder/'payload-files.json').read_text())
report={'status':'running','checked_at':datetime.now(timezone.utc).isoformat(),'checks':[],
        'before':before,'after':after,'public_assets':[],'normal_dns':True,'tls_verification':True,
        'apk_body_downloaded':False,'business_records_read':False,'database_writes':False,'services_changed':False}
def require(value,label):
    if not value:raise RuntimeError(label)
    report['checks'].append(label)
try:
    require(after['release']=='/srv/agriscan/releases/'+info['release_id'],'current points at the exact frozen full UI release')
    for key in ['MainPID','NRestarts','ExecMainStartTimestamp','ActiveState','SubState']:
        require(after['api'][key]==before['api'][key],'API '+key+' is unchanged by static release')
    require(after['schema']==before['schema']=='20261029_06','schema remains ownership revision 06 without migration')
    require(after['configuration']==before['configuration'] and after['configuration']['version']==6,'configuration v6 entire row checksum remains unchanged')
    require(after['health']==before['health']=={'status':'ok','database':'connected','redis':'connected','mode':'production','model':'ready'},'production DB Redis and detector health remain ready')
    with httpx.Client(trust_env=False,verify=True,follow_redirects=True,timeout=35) as client:
        base='https://agriscan.ming-ai.top/agriscan/'
        font_urls=set()
        scripts=set(info['workspace_entries']+info['admin_entries'])
        for page in ['index.html','workspace/index.html','admin/index.html']:
            response=client.get(base+page)
            relative='public/'+page
            require(response.status_code==200,'normal DNS HTTPS '+page+' returns 200')
            require(hashlib.sha256(response.content).hexdigest()==manifest[relative],'public '+page+' bytes match the frozen payload')
            require('no-cache' in response.headers.get('cache-control',''),'public '+page+' requires cache revalidation')
            report['public_assets'].append({'url':str(response.url),'method':'GET','status':200,'sha256':hashlib.sha256(response.content).hexdigest(),'bytes':len(response.content)})
            assets=re.findall(r'(?:src|href)=[\'\"]([^\'\"]+)[\'\"]',response.text)
            for asset in assets:
                target=urljoin(str(response.url),asset)
                if not urlsplit(target).path.endswith('.css'):continue
                css=client.get(target)
                require(css.status_code==200,'public primary CSS '+urlsplit(target).path+' returns 200')
                member='public/'+urlsplit(target).path.removeprefix('/agriscan/')
                require(hashlib.sha256(css.content).hexdigest()==manifest[member],'public CSS '+member+' matches frozen payload SHA256')
                report['public_assets'].append({'url':target,'method':'GET','status':200,'sha256':hashlib.sha256(css.content).hexdigest(),'bytes':len(css.content)})
                for value in re.findall(r'url\(([^)]+)\)',css.text):
                    candidate=urljoin(target,value.strip().strip('\'\"'))
                    if urlsplit(candidate).path.endswith(('.woff2','.woff','.ttf')):font_urls.add(candidate)
        for entry in sorted(scripts):
            response=client.head('https://agriscan.ming-ai.top'+entry)
            require(response.status_code==200,'new compiled entry '+entry+' returns 200 by HEAD')
            report['public_assets'].append({'url':str(response.url),'method':'HEAD','status':200,'content_type':response.headers.get('content-type'),'content_length':response.headers.get('content-length')})
        if not font_urls:
            public_fonts=[name for name in manifest if name.endswith(('.woff2','.woff','.ttf','.otf'))]
            require(not public_fonts,'web payload declares no custom font resource requiring a public URL')
            ready=json.loads((folder/'web-ready.json').read_text())
            expected_font=ready['phone_font_and_ip_assets']['mobile/public/fonts/agriscan-sans-sc.woff2']
            with zipfile.ZipFile(folder/'apk/agriscan-test-1.0.3-code4.apk') as archive:
                font=archive.read('assets/public/fonts/agriscan-sans-sc.woff2')
            require(len(font)==expected_font['bytes'] and hashlib.sha256(font).hexdigest()==expected_font['sha256'],'mobile-only new font is present in the frozen local APK with matching SHA256')
            report['font_scope']={'web_font_http':'not applicable; no custom font in public payload',
                                  'mobile_apk_font':'assets/public/fonts/agriscan-sans-sc.woff2',
                                  'bytes':len(font),'sha256':expected_font['sha256'],'apk_body_downloaded':False}
        for target in sorted(font_urls):
            require(urlsplit(target).hostname=='agriscan.ming-ai.top','font asset stays on the official domain')
            response=client.head(target)
            require(response.status_code==200,'new font '+urlsplit(target).path+' returns 200 by HEAD')
            report['public_assets'].append({'url':target,'method':'HEAD','status':200,'content_type':response.headers.get('content-type'),'content_length':response.headers.get('content-length')})
        release=client.get(base+'downloads/release.json')
        require(release.status_code==200,'public download metadata returns 200')
        metadata=release.json()
        require(metadata['version']=='1.0.3' and metadata['version_code']==4,'public download metadata identifies latest APK 1.0.3 code4')
        require(metadata['sha256']==info['apk']['sha256'],'public APK metadata matches the frozen signed artifact SHA256')
        apk=client.head(base+'downloads/agriscan-test.apk')
        require(apk.status_code==200 and int(apk.headers['content-length'])==metadata['size_bytes'],'APK HEAD size matches latest metadata without downloading its body')
        report['download']={'version':metadata['version'],'version_code':metadata['version_code'],'sha256':metadata['sha256'],'bytes':metadata['size_bytes'],'apk_head_status':apk.status_code}
    remote=r'''
import hashlib,json,subprocess
from pathlib import Path
from urllib.request import urlopen,Request
report={'source':'production server ordinary DNS and verified TLS','config_sha256':hashlib.sha256(Path('/etc/nginx/conf.d/flowly-share.conf').read_bytes()).hexdigest()}
with urlopen('https://flowly-ai.top/',timeout=25) as response:
    body=response.read();report['root']={'status':response.status,'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
try:
    with urlopen(Request('https://flowly-ai.top/app.apk',method='HEAD'),timeout=25) as response:report['app_apk_head']={'status':response.status,'bytes':response.headers.get('Content-Length')}
except Exception as error:report['app_apk_head']={'checked':False,'error_type':type(error).__name__}
print(json.dumps(report))
'''
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','python3 -'],input=remote,text=True,capture_output=True,timeout=70)
    require(result.returncode==0,'old Flowly read-only origin metadata check completed')
    flowly=json.loads(result.stdout)
    old=json.loads((folder.parents[0]/'domain-migration-20261029/server.json').read_text())
    require(flowly['config_sha256']==old['preserved_after']['flowly_config_sha256'],'old Flowly virtual host file remains unchanged')
    require(flowly['root']['status']==200 and flowly['root']['sha256']==old['old_flowly_root_after']['body_sha256'],'old Flowly HTTPS root still serves its original page')
    require(flowly['app_apk_head'].get('status')==200,'old Flowly app.apk remains available by HEAD')
    report['old_flowly']=flowly
    report['status']='passed'
except Exception as error:
    report['status']='failed';report['error_type']=type(error).__name__
    if isinstance(error,RuntimeError):report['error']=str(error)
finally:
    (folder/'readonly-runtime-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'checks':len(report['checks']),'assets_checked':len(report['public_assets']),
                  'download':report.get('download'),'old_flowly':report.get('old_flowly'),
                  'error':report.get('error'),'error_type':report.get('error_type'),
                  'report':str(folder/'readonly-runtime-comparison.json')}))
if report['status']!='passed':raise SystemExit(1)
