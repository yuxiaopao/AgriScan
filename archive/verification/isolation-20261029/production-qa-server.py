"""Owned production fixtures only. Stdout is privately captured by the launcher."""
import hashlib
import json
import os
from pathlib import Path
import secrets
from datetime import datetime,timezone

from dotenv import dotenv_values
import httpx
from sqlalchemy import create_engine,text

MANIFEST = __QA_FIXTURE_MANIFEST__
run_id='qa_iso_20261029_'+MANIFEST['suffix']
private_path=Path('/srv/agriscan/shared/logs')/(run_id+'-credentials.json')
report_path=Path('/srv/agriscan/shared/logs')/(run_id+'-preflight.json')
private={'run_id':run_id,'base_url':'https://agriscan.ming-ai.top/agriscan','accounts':{}}
report={'run_id':run_id,'kind':'production_localhost_actual_mysql_redis',
        'started_at':datetime.now(timezone.utc).isoformat(),'checks':[],'fixtures':[]}
tokens={}
class QAFailure(RuntimeError):pass
def require(value,message):
    if not value:raise QAFailure(message)
    report['checks'].append(message)
def save_private():
    fd=os.open(private_path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as output:json.dump(private,output,ensure_ascii=False,indent=2)
    private_path.chmod(0o600)
def save_report():
    fd=os.open(report_path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as output:json.dump(report,output,ensure_ascii=False,indent=2)

environment=dotenv_values('/srv/agriscan/shared/production.env')
engine=create_engine(environment['DATABASE_URL'],pool_pre_ping=True)
table_keys={'users':('id',),'plots':('id',),'plot_details':('plot_id',),'detections':('id',),
            'detection_predictions':('detection_id',),'assistant_conversations':('id',),
            'assistant_messages':('id',),'assistant_detection_discussions':('user_id','detection_id'),
            'workspace_configuration':('id',)}
def rows_for(table):
    with engine.connect() as connection:return [dict(row) for row in connection.execute(text(f'SELECT * FROM `{table}`')).mappings()]
def identity(row,fields):return tuple(row[field] for field in fields)
def digest(rows):return hashlib.sha256(json.dumps(sorted(rows,key=lambda row:json.dumps(row,sort_keys=True,default=str)),sort_keys=True,default=str).encode()).hexdigest()
baseline={table:rows_for(table) for table in table_keys}
report['preserved_before']={table:{'count':len(rows),'sha256':digest(rows)} for table,rows in baseline.items()}
report['configuration_version']=baseline['workspace_configuration'][0]['version']
require(report['configuration_version']==6,'initial runtime configuration remains version 6')
require(not private_path.exists(),'unique QA credential file does not already exist')
save_private()

with httpx.Client(base_url='http://127.0.0.1:18000',trust_env=False,timeout=135,follow_redirects=False) as client:
    def call(actor,method,path,expected=200,**kwargs):
        headers={'Authorization':'Bearer '+tokens[actor]} if actor else {}
        response=client.request(method,path,headers=headers,**kwargs)
        require(response.status_code==expected,f'{actor or "anonymous"} {method} {path.split("?")[0]} returns {expected}')
        return response
    def login(actor,username,password):
        response=call(None,'POST','/api/auth/login',json={'username':username,'password':password})
        tokens[actor]=response.json()['access_token']
        return call(actor,'GET','/api/auth/me').json()
    def fixture_bytes(key):
        item=MANIFEST['fixtures'][key]
        path=Path(item['remote'])
        require(path.is_relative_to(Path('/srv/agriscan/bootstrap')) and path.is_file(),'owned '+key+' fixture path exists inside bootstrap')
        data=path.read_bytes()
        require(len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],'owned '+key+' fixture hash verified')
        return data
    def create_detection(actor,key,plot_id):
        name=run_id+'_'+actor+'_'+key+'.jpg'
        response=call(actor,'POST','/api/detections',expected=201,
                      data={'plot_id':plot_id,'note':run_id+' '+actor+' '+key},
                      files={'file':(name,fixture_bytes(key),'image/jpeg')})
        row=response.json()
        require(row['crop']==('苹果' if actor=='a' else '玉米'),'real '+actor+' crop recognized correctly from fixture')
        require(row.get('boxes') and row.get('prediction_model',{}).get('task')=='detect','real '+actor+' image has actual model target boxes')
        private['accounts'][actor]['detections'].append(row)
        save_private()
        return row
    try:
        health=call(None,'GET','/api/health').json()
        require(health=={'status':'ok','database':'connected','redis':'connected','mode':'production','model':'ready'},'production MySQL Redis and real detector are ready')
        login('admin',environment['ADMIN_USERNAME'],environment['ADMIN_PASSWORD'])
        administrator=call('admin','GET','/api/admin/users').json()
        admin_id=next(row['id'] for row in administrator['items'] if row['username']==environment['ADMIN_USERNAME'])
        for actor,crop in [('a','苹果'),('b','玉米')]:
            username=run_id+'_'+actor
            password=secrets.token_urlsafe(30)
            name='隔离验收'+actor.upper()+'·'+crop+'_'+MANIFEST['suffix']
            account=call('admin','POST','/api/admin/users',expected=201,
                         json={'username':username,'name':name,'password':password,'role':'member','is_active':True}).json()
            private['accounts'][actor]={'id':account['id'],'username':username,'password':password,'name':name,'detections':[],'conversations':[]}
            save_private()
            login(actor,username,password)
            require(call(actor,'GET','/api/detections').json()==[],'new '+actor+' personal detection list starts empty')
            require(call(actor,'GET','/api/plots').json()==[],'new '+actor+' personal plot list starts empty')
            plot=call(actor,'POST','/api/plots',expected=201,json={'name':run_id+'_'+actor+'_'+crop+'地块','crop':crop,'area':1.5,'location':'隔离验收测试地块','manager':name}).json()
            private['accounts'][actor]['plot']=plot
            save_private()
            cover=call(actor,'POST','/api/plots/'+plot['id']+'/cover',files={'file':(run_id+'_'+actor+'_cover.jpg',fixture_bytes('apple' if actor=='a' else 'corn_rust'),'image/jpeg')}).json()
            private['accounts'][actor]['plot']=cover
            save_private()
            for key in (['apple'] if actor=='a' else ['corn_rust','corn_healthy']):create_detection(actor,key,plot['id'])

        all_ids={row['id'] for account in private['accounts'].values() for row in account['detections']}
        for days in [7,30,7]:
            for actor in ['a','b','a']:
                account=private['accounts'][actor]
                expected={row['id'] for row in account['detections']}
                dashboard=call(actor,'GET','/api/dashboard',params={'days':days}).json()
                require(dashboard['stats']['total']==len(expected),'warmed '+actor+' '+str(days)+' day dashboard total is personal')
                require({row['id'] for row in dashboard['recent']}==expected,'warmed '+actor+' recent records contain only owned fixtures')
                require(sum(day['total'] for day in dashboard['trend'])==len(expected),'warmed '+actor+' trend contains only owned fixtures')
                require([(row['name'],row['value']) for row in dashboard['distribution']]==[('苹果' if actor=='a' else '玉米',len(expected))],'warmed '+actor+' crop distribution remains private')
        for actor,other in [('a','b'),('b','a')]:
            account,foreign=private['accounts'][actor],private['accounts'][other]
            owned_ids={row['id'] for row in account['detections']}
            rows=call(actor,'GET','/api/detections').json()
            require({row['id'] for row in rows}==owned_ids,actor+' personal list contains exact owned ids')
            own_search=call(actor,'GET','/api/detections',params={'search':run_id}).json()
            require({row['id'] for row in own_search}==owned_ids,actor+' search/export source remains private')
            require(call(actor,'GET','/api/detections',params={'search':run_id+'_'+other}).json()==[],actor+' cannot search foreign fixture names')
            plots=call(actor,'GET','/api/plots').json()
            require([row['id'] for row in plots]==[account['plot']['id']],actor+' personal plots contain only owned plot')
            for row in account['detections']:
                call(actor,'GET','/api/detections/'+row['id'])
                image=call(actor,'GET',row['image_url'])
                require('no-store' in image.headers.get('cache-control',''),actor+' own image forbids shared caching')
            call(actor,'GET',account['plot']['cover_url'])
            for row in foreign['detections']:
                call(actor,'GET','/api/detections/'+row['id'],expected=404)
                call(actor,'GET',row['image_url'],expected=404)
                call(actor,'DELETE','/api/detections/'+row['id'],expected=404)
            call(actor,'GET',foreign['plot']['cover_url'],expected=404)
            call(actor,'PATCH','/api/plots/'+foreign['plot']['id'],expected=404,json={'name':'must never persist'})
            call(actor,'DELETE','/api/plots/'+foreign['plot']['id'],expected=404)
            before_files={path.name for path in Path(environment['UPLOAD_DIR']).iterdir() if path.is_file()}
            before_ids={row['id'] for row in rows_for('detections')}
            call(actor,'POST','/api/detections',expected=404,data={'plot_id':foreign['plot']['id'],'note':run_id+' forbidden association'},
                 files={'file':('forbidden.jpg',fixture_bytes('apple'),'image/jpeg')})
            require(before_ids=={row['id'] for row in rows_for('detections')},actor+' denied association creates no database rows')
            require(before_files=={path.name for path in Path(environment['UPLOAD_DIR']).iterdir() if path.is_file()},actor+' denied association leaves no upload files')

        before_chat=digest(rows_for('assistant_conversations'))
        before_messages=digest(rows_for('assistant_messages'))
        call('b','POST','/api/assistant/detections/'+private['accounts']['a']['detections'][0]['id']+'/analysis',expected=404)
        require(before_chat==digest(rows_for('assistant_conversations')) and before_messages==digest(rows_for('assistant_messages')),'forbidden B image analysis does not create conversations or messages')
        unsafe_legacy={link['conversation_id'] for link in baseline['assistant_detection_discussions']}
        admin_visible={row['id'] for row in call('admin','GET','/api/assistant/conversations').json()}
        require(not unsafe_legacy & admin_visible,'legacy unassigned linked snapshots are hidden from personal admin history')
        for chat_id in unsafe_legacy:
            call('admin','GET','/api/assistant/conversations/'+chat_id,expected=404)
            call('admin','POST','/api/assistant/conversations/'+chat_id+'/messages',expected=404,json={'question':'禁止的隔离验收访问'})
            call('b','GET','/api/assistant/conversations/'+chat_id,expected=404)
        ordinary=call('a','POST','/api/assistant/conversations',expected=201).json()
        private['accounts']['a']['conversations'].append(ordinary['id']);save_private()
        message=call('a','POST','/api/assistant/conversations/'+ordinary['id']+'/messages',json={'question':'隔离验收：请只回复“收到，记录田间观察”。'}).json()
        require(len(message['messages'])==2 and message['messages'][-1]['role']=='assistant' and bool(message['messages'][-1]['content'].strip()),'own independent text chat receives a real model reply')
        call('b','GET','/api/assistant/conversations/'+ordinary['id'],expected=404)
        require(ordinary['id'] not in {row['id'] for row in call('b','GET','/api/assistant/conversations').json()},'B cannot see A independent chat in history')

        for actor in ['a','b']:
            account=private['accounts'][actor]
            rows=call('admin','GET','/api/admin/detections',params={'owner_id':account['id']}).json()['items']
            require({row['id'] for row in rows}=={row['id'] for row in account['detections']},'admin owner filter returns exact '+actor+' fixtures')
            for row in rows:
                require(row['owner_id']==account['id'] and row['owner_username']==account['username'],'admin serializer identifies '+actor+' ownership')
                require(row['image_url'].startswith('/api/admin/uploads/'),'admin image uses independent management route')
                call('admin','GET',row['image_url'])
                call(actor,'GET',row['image_url'],expected=403)
                call('admin','GET','/api/detections/'+row['id'],expected=404)
            exported=call('admin','GET','/api/admin/detections/export.csv',params={'owner_id':account['id']})
            require(all(row['name'] in exported.text for row in account['detections']),'admin scoped CSV includes '+actor+' fixtures')
            foreign=private['accounts']['b' if actor=='a' else 'a']
            require(not any(row['name'] in exported.text for row in foreign['detections']),'admin scoped CSV excludes other owner')
        personal_admin=call('admin','GET','/api/detections').json()
        require(not all_ids & {row['id'] for row in personal_admin},'admin personal workspace does not bypass A/B ownership')
        for path in ['/api/detections','/api/plots','/api/dashboard',private['accounts']['a']['detections'][0]['image_url']]:call(None,'GET',path,expected=401)

        for table,fields in table_keys.items():
            keys={identity(row,fields) for row in baseline[table]}
            remaining=[row for row in rows_for(table) if identity(row,fields) in keys]
            require(digest(remaining)==digest(baseline[table]),'pre-existing '+table+' rows preserved byte-equivalently')
        require(rows_for('workspace_configuration')[0]['version']==6,'runtime configuration version remains 6 after QA')
        with engine.connect() as connection:
            require(connection.scalar(text("SELECT version_num FROM alembic_version"))=='20261029_06','real production database schema is ownership revision 06')
        report['fixtures']=[{'key':actor,'user_id':account['id'],'username':account['username'],'name':account['name'],
                             'plot_id':account['plot']['id'],'plot_name':account['plot']['name'],'cover_url':account['plot']['cover_url'],
                             'detections':[{key:row[key] for key in ['id','name','crop','result','confidence','image_url']} for row in account['detections']],
                             'conversation_ids':account['conversations']} for actor,account in private['accounts'].items()]
        report['retained_owned_fixtures']={'accounts':2,'plots':2,'detections':3,'covers':2}
        report['status']='passed'
    except Exception as error:
        report['status']='failed'
        report['error_type']=type(error).__name__
        if isinstance(error,QAFailure):report['error']=str(error)
    finally:
        for actor in list(tokens):
            try:
                response=client.post('/api/auth/logout',headers={'Authorization':'Bearer '+tokens[actor]})
                report.setdefault('revoked_control_sessions',{})[actor]=response.status_code==200
            except Exception:report.setdefault('revoked_control_sessions',{})[actor]=False
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        save_private();save_report()
        engine.dispose()

# The local wrapper must capture this envelope, save credentials privately,
# and output only the safe report summary. Never run this script interactively.
print(json.dumps({'private_credentials':private,'report':report},ensure_ascii=False))
