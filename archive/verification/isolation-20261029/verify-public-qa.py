import json
from pathlib import Path
import re
from datetime import datetime,timezone
import httpx

folder=Path(__file__).resolve().parent
private=json.loads((folder/'qa-credentials.json').read_text(encoding='utf-8'))
local_preflight=json.loads((folder/'production-preflight.json').read_text(encoding='utf-8'))
admin_text=(folder.parents[1]/'.runtime/server-admin-access.txt').read_text(encoding='utf-8')
admin_username=re.search(r'^Username:\s*(.+)$',admin_text,re.M).group(1).strip()
admin_password=re.search(r'^Password:\s*(.+)$',admin_text,re.M).group(1).strip()
api='https://agriscan.ming-ai.top/agriscan/api'
report={'run_id':private['run_id'],'kind':'normal_dns_public_https_readonly',
        'base_url':api,'tls_verification':True,'hostname_verification':True,'dns_override':False,
        'started_at':datetime.now(timezone.utc).isoformat(),'checks':[],'fixtures':[]}
tokens={}
class Failure(RuntimeError):pass
def require(value,message):
    if not value:raise Failure(message)
    report['checks'].append(message)
with httpx.Client(trust_env=False,verify=True,timeout=40,follow_redirects=False) as client:
    def call(actor,path,expected=200,**kwargs):
        headers={'Authorization':'Bearer '+tokens[actor]} if actor else {}
        response=client.get(api+path,headers=headers,**kwargs)
        require(response.status_code==expected,f'{actor or "anonymous"} GET {path.split("?")[0]} returns {expected} over public verified HTTPS')
        require('no-store' in response.headers.get('cache-control',''),'private API response forbids shared caching at '+path.split('?')[0])
        require('authorization' in response.headers.get('vary','').lower(),'private API response varies by authorization at '+path.split('?')[0])
        return response
    def login(actor,username,password):
        response=client.post(api+'/auth/login',json={'username':username,'password':password})
        require(response.status_code==200,actor+' login works over ordinary DNS and trusted HTTPS')
        tokens[actor]=response.json()['access_token']
    try:
        health=call(None,'/health')
        require(health.json()=={'status':'ok','database':'connected','redis':'connected','mode':'production','model':'ready'},'public production health confirms MySQL Redis and actual model')
        stream=health.extensions.get('network_stream')
        ssl_object=stream.get_extra_info('ssl_object') if stream else None
        if ssl_object:
            certificate=ssl_object.getpeercert()
            report['tls']={'version':ssl_object.version(),'subject_alt_names':certificate.get('subjectAltName',()),'not_after':certificate.get('notAfter')}
            require(('DNS','agriscan.ming-ai.top') in certificate.get('subjectAltName',()),'trusted peer certificate covers the exact public domain')
        login('admin',admin_username,admin_password)
        admin_text=admin_username=admin_password=None
        config=call('admin','/admin/config').json()
        require(config['version']==6 and config['integrations']['llm_key_configured'],'public runtime config remains version 6 with write-only LLM key configured')
        for actor in ['a','b']:
            account=private['accounts'][actor]
            login(actor,account['username'],account['password'])
        for actor,other in [('a','b'),('b','a')]:
            account,foreign=private['accounts'][actor],private['accounts'][other]
            expected={row['id'] for row in account['detections']}
            own=call(actor,'/detections').json()
            require({row['id'] for row in own}==expected,actor+' public list contains exact retained own fixtures')
            searched=call(actor,'/detections',params={'search':private['run_id']}).json()
            require({row['id'] for row in searched}==expected,actor+' public search/export source contains exact own fixtures')
            require(call(actor,'/detections',params={'search':private['run_id']+'_'+other}).json()==[],actor+' public search cannot find foreign fixture names')
            for row in account['detections']:
                detail=call(actor,'/detections/'+row['id']).json()
                require(detail['crop']==row['crop'] and detail['result']==row['result'],actor+' public detection detail matches own stored fixture')
                image=call(actor,row['image_url'].removeprefix('/api'))
                require(image.headers.get('content-type','').startswith('image/'),actor+' public own photo has an image response')
            plots=call(actor,'/plots').json()
            require([plot['id'] for plot in plots]==[account['plot']['id']],actor+' public plots contain only own plot')
            cover=call(actor,account['plot']['cover_url'].removeprefix('/api'))
            require(cover.headers.get('content-type','').startswith('image/'),actor+' public own cover loads')
            for row in foreign['detections']:
                call(actor,'/detections/'+row['id'],expected=404)
                call(actor,row['image_url'].removeprefix('/api'),expected=404)
            call(actor,foreign['plot']['cover_url'].removeprefix('/api'),expected=404)
            call(actor,'/admin/detections',expected=403)
            for chat_id in foreign['conversations']:call(actor,'/assistant/conversations/'+chat_id,expected=404)
            report['fixtures'].append({'actor':actor,'username':account['username'],'detections':len(expected),'plots':1,'covers':1})
        for days in [7,30,7]:
            for actor in ['a','b','a']:
                expected={row['id'] for row in private['accounts'][actor]['detections']}
                data=call(actor,'/dashboard',params={'days':days}).json()
                require(data['stats']['total']==len(expected),'public '+actor+' warmed '+str(days)+' day count is private')
                require({row['id'] for row in data['recent']}==expected,'public '+actor+' recent ids remain private across alternating users')
                require(sum(row['total'] for row in data['trend'])==len(expected),'public '+actor+' trend contains only owned fixtures')
                require([(row['name'],row['value']) for row in data['distribution']]==[('苹果' if actor=='a' else '玉米',len(expected))],'public '+actor+' distribution contains only own crop')
        unassigned=call('admin','/admin/detections',params={'owner_id':'unassigned','page_size':100}).json()
        legacy_ids={row['id'] for row in unassigned['items']}
        require(len(legacy_ids)>=local_preflight['preserved_before']['detections']['count'],'admin console retains legacy unassigned detection rows')
        personal=call('admin','/detections').json()
        personal_ids={row['id'] for row in personal}
        require(not personal_ids&legacy_ids,'admin personal API does not expose unassigned legacy rows')
        for actor in ['a','b']:
            account=private['accounts'][actor]
            expected={row['id'] for row in account['detections']}
            rows=call('admin','/admin/detections',params={'owner_id':account['id']}).json()['items']
            require({row['id'] for row in rows}==expected,'public admin owner filter sees exact '+actor+' fixtures')
            require(not personal_ids&expected,'public admin personal workspace does not bypass '+actor+' ownership')
            for row in rows:
                require(row['owner_id']==account['id'],'public management serializer keeps explicit owner')
                call('admin','/admin/detections/'+row['id'])
                call('admin',row['image_url'].removeprefix('/api'))
                call(actor,row['image_url'].removeprefix('/api'),expected=403)
        unknown_chats={match.group(1) for message in local_preflight['checks'] if (match:=re.match(r'^admin GET /api/assistant/conversations/([0-9a-f]{32}) returns 404$',message))}
        visible={row['id'] for row in call('admin','/assistant/conversations').json()}
        require(not visible&unknown_chats,'legacy source-unverified discussions stay hidden in public admin personal history')
        for chat_id in unknown_chats:
            call('admin','/assistant/conversations/'+chat_id,expected=404)
            call('b','/assistant/conversations/'+chat_id,expected=404)
        for path in ['/detections','/dashboard','/plots',private['accounts']['a']['detections'][0]['image_url'].removeprefix('/api')]:call(None,path,expected=401)
        require(call('admin','/admin/config').json()['version']==6,'public read-only verification did not modify runtime configuration v6')
        report['business_mutations']=False
        report['status']='passed'
    except Exception as error:
        report['status']='failed';report['error_type']=type(error).__name__
        if isinstance(error,Failure):report['error']=str(error)
    finally:
        for actor,token in tokens.items():
            try:report.setdefault('revoked_sessions',{})[actor]=client.post(api+'/auth/logout',headers={'Authorization':'Bearer '+token}).status_code==200
            except Exception:report.setdefault('revoked_sessions',{})[actor]=False
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        (folder/'production-public.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'checks':len(report['checks']),'error':report.get('error'),
                  'error_type':report.get('error_type'),'report':str(folder/'production-public.json')}))
if report['status']!='passed':raise SystemExit(1)
