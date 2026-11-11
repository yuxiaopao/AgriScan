"""Remove only explicitly approved disposable QA identities after browser sign-off."""
import hashlib,json,os
from pathlib import Path
from datetime import datetime,timezone
from dotenv import dotenv_values
import httpx
from sqlalchemy import create_engine,text

RUN_ID=__QA_RUN_ID__
ALLOWLIST=__QA_CLEANUP_ALLOWLIST__
FIXTURES=__QA_FIXTURES__
private_path=Path('/srv/agriscan/shared/logs')/(RUN_ID+'-credentials.json')
private=json.loads(private_path.read_text(encoding='utf-8'))
environment=dotenv_values('/srv/agriscan/shared/production.env')
engine=create_engine(environment['DATABASE_URL'],pool_pre_ping=True)
report={'run_id':RUN_ID,'started_at':datetime.now(timezone.utc).isoformat(),'checks':[],'deleted':{}}
class Failure(RuntimeError):pass
def require(value,label):
    if not value:raise Failure(label)
    report['checks'].append(label)
def rows_for(table):
    with engine.connect() as connection:return [dict(row) for row in connection.execute(text(f'SELECT * FROM `{table}`')).mappings()]
def digest(rows):return hashlib.sha256(json.dumps(sorted(rows,key=lambda row:json.dumps(row,sort_keys=True,default=str)),sort_keys=True,default=str).encode()).hexdigest()
def key(row,fields):return tuple(row[field] for field in fields)
token=None
member_tokens={}
with httpx.Client(base_url='http://127.0.0.1:18000',trust_env=False,timeout=40,follow_redirects=False) as client:
    def call(method,path,expected=200,**kwargs):
        response=client.request(method,path,headers={'Authorization':'Bearer '+token},**kwargs)
        require(response.status_code==expected,method+' '+path+' returns '+str(expected))
        return response
    try:
        require(private['run_id']==RUN_ID,'private checkpoint identifies the exact QA run')
        users=rows_for('users')
        qa_ids={account['id'] for account in private['accounts'].values()}
        require(len(qa_ids)==2,'two exact disposable QA account IDs are known')
        for actor,account in private['accounts'].items():
            match=next((row for row in users if row['id']==account['id']),None)
            require(match is not None and match['username']==RUN_ID+'_'+actor and match['role']=='member','exact '+actor+' account id username and member role verified')
        allowed_detections={row['id'] for account in private['accounts'].values() for row in account['detections']}|set(ALLOWLIST.get('detections',[]))
        allowed_plots={account['plot']['id'] for account in private['accounts'].values()}|set(ALLOWLIST.get('plots',[]))
        detections=[row for row in rows_for('detections') if row.get('owner_id') in qa_ids]
        plots=[row for row in rows_for('plots') if row.get('owner_id') in qa_ids]
        unexpected_detections={row['id'] for row in detections}-allowed_detections
        unexpected_plots={row['id'] for row in plots}-allowed_plots
        report['unexpected_owned_detection_ids']=sorted(unexpected_detections)
        report['unexpected_owned_plot_ids']=sorted(unexpected_plots)
        require(not unexpected_detections and not unexpected_plots,'all owned records and plots are on the explicit ID allowlist')
        detection_ids={row['id'] for row in detections}
        plot_ids={row['id'] for row in plots}
        all_detections=rows_for('detections')
        require(not any(row.get('plot_id') in plot_ids and row['id'] not in detection_ids for row in all_detections),'no foreign business record is associated with a disposable QA plot')
        conversations=[row for row in rows_for('assistant_conversations') if row['user_id'] in qa_ids]
        conversation_ids={row['id'] for row in conversations}
        now=datetime.now(timezone.utc).replace(tzinfo=None)
        require(not any(row['busy_until']>now for row in conversations),'QA conversations have no in-flight message lease')
        discussions=rows_for('assistant_detection_discussions')
        require(not any(row['conversation_id'] in conversation_ids and row['user_id'] not in qa_ids for row in discussions),'no foreign discussion references a disposable QA conversation')
        table_keys={'users':('id',),'plots':('id',),'plot_details':('plot_id',),'detections':('id',),
                    'detection_predictions':('detection_id',),'assistant_conversations':('id',),
                    'assistant_messages':('id',),'assistant_detection_discussions':('user_id','detection_id'),
                    'workspace_configuration':('id',),'user_emails':('email',)}
        def owned(table,row):
            if table=='users':return row['id'] in qa_ids
            if table=='plots':return row['id'] in plot_ids
            if table=='plot_details':return row['plot_id'] in plot_ids
            if table=='detections':return row['id'] in detection_ids
            if table=='detection_predictions':return row['detection_id'] in detection_ids
            if table=='assistant_conversations':return row['id'] in conversation_ids
            if table=='assistant_messages':return row['conversation_id'] in conversation_ids
            if table in {'assistant_detection_discussions','user_emails'}:return row['user_id'] in qa_ids
            return False
        protected={table:[row for row in rows_for(table) if not owned(table,row)] for table in table_keys}
        report['protected_before']={table:{'count':len(rows),'sha256':digest(rows)} for table,rows in protected.items()}
        configuration=protected['workspace_configuration']
        require(len(configuration)==1 and configuration[0]['version']==6,'runtime configuration v6 is snapshotted without modification')
        uploads=Path(environment['UPLOAD_DIR']).resolve()
        filenames={Path(row['image_url']).name for row in detections if row.get('image_url')}
        filenames|={row['cover_filename'] for row in rows_for('plot_details') if row['plot_id'] in plot_ids and row.get('cover_filename')}
        require(all((uploads/name).resolve().parent==uploads for name in filenames),'all disposable media paths resolve directly inside owned uploads directory')
        response=client.post('/api/auth/login',json={'username':environment['ADMIN_USERNAME'],'password':environment['ADMIN_PASSWORD']})
        require(response.status_code==200,'dedicated cleanup control session authenticated')
        token=response.json()['access_token']
        for actor,account in private['accounts'].items():
            response=client.post('/api/auth/login',json={'username':account['username'],'password':account['password']})
            require(response.status_code==200,'exact '+actor+' disposable identity authenticates before cleanup')
            member_tokens[actor]=response.json()['access_token']
            response=client.post('/api/auth/logout',headers={'Authorization':'Bearer '+member_tokens[actor]})
            require(response.status_code==200,actor+' cleanup member session is explicitly revoked before account deletion')
        for user_id in qa_ids:call('PATCH','/api/admin/users/'+user_id,json={'is_active':False})
        report['deactivated_accounts']=sorted(qa_ids)
        # These exact user IDs were created by this run, not selected by date/name.
        parameters={'a':private['accounts']['a']['id'],'b':private['accounts']['b']['id']}
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM assistant_detection_discussions WHERE user_id IN (:a,:b)'),parameters)
            connection.execute(text('DELETE FROM assistant_messages WHERE conversation_id IN (SELECT id FROM assistant_conversations WHERE user_id IN (:a,:b))'),parameters)
            result=connection.execute(text('DELETE FROM assistant_conversations WHERE user_id IN (:a,:b)'),parameters)
            report['deleted']['conversations']=result.rowcount
        for row in detections:
            current=call('GET','/api/admin/detections/'+row['id']).json()
            require(current['owner_id'] in qa_ids and current['id'] in allowed_detections,'disposable detection identity rechecked immediately before deletion')
            call('DELETE','/api/admin/detections/'+row['id'])
        for row in plots:
            current=call('GET','/api/admin/plots/'+row['id']).json()
            require(current['owner_id'] in qa_ids and current['id'] in allowed_plots,'disposable plot identity rechecked immediately before deletion')
            call('DELETE','/api/admin/plots/'+row['id'])
        require(not any(row.get('owner_id') in qa_ids for row in rows_for('detections')),'no QA detections remain before deleting test identities')
        require(not any(row.get('owner_id') in qa_ids for row in rows_for('plots')),'no QA plots remain before deleting test identities')
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM user_emails WHERE user_id IN (:a,:b)'),parameters)
            result=connection.execute(text('DELETE FROM users WHERE id IN (:a,:b)'),parameters)
            require(result.rowcount==2,'exactly the two disposable QA users were deleted')
        require(all(not (uploads/name).exists() for name in filenames),'only known QA detection and cover files have been removed')
        for actor,account in private['accounts'].items():
            response=client.get('/api/auth/me',headers={'Authorization':'Bearer '+member_tokens[actor]})
            require(response.status_code==401,actor+' revoked session is unauthorized after its exact user ID is deleted')
            response=client.post('/api/auth/login',json={'username':account['username'],'password':account['password']})
            require(response.status_code==401,actor+' removed disposable identity can no longer log in')
        for table,fields in table_keys.items():
            identities={key(row,fields) for row in protected[table]}
            after=[row for row in rows_for(table) if key(row,fields) in identities]
            require(len(after)==len(protected[table]),'all pre-cleanup non-QA '+table+' primary keys remain present')
            require(digest(after)==digest(protected[table]),'pre-cleanup non-QA '+table+' rows retain the same hash')
        report['deleted'].update({'accounts':2,'detections':len(detections),'plots':len(plots),'media_files':len(filenames)})
        report['deleted_ids']={'users':sorted(qa_ids),'detections':sorted(detection_ids),'plots':sorted(plot_ids),'conversations':sorted(conversation_ids)}
        removed_bootstrap=[]
        for item in FIXTURES.values():
            target=Path(item['remote'])
            require(not target.is_symlink() and target.resolve().parent==Path('/srv/agriscan/bootstrap').resolve(),'exact disposable bootstrap path stays within bootstrap')
            if target.exists():
                require(target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256'],'exact bootstrap fixture digest matches the uploaded test artifact')
                target.unlink();removed_bootstrap.append(str(target))
        report['removed_bootstrap_fixtures']=removed_bootstrap
        report['deleted']['bootstrap_fixtures']=len(removed_bootstrap)
        report['status']='passed'
    except Exception as error:
        report['status']='failed';report['error_type']=type(error).__name__
        if isinstance(error,Failure):report['error']=str(error)
    finally:
        if token:
            try:report['cleanup_session_revoked']=client.post('/api/auth/logout',headers={'Authorization':'Bearer '+token}).status_code==200
            except Exception:report['cleanup_session_revoked']=False
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        output=Path('/srv/agriscan/shared/logs')/(RUN_ID+'-cleanup.json')
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');output.chmod(0o600)
        if report['status']=='passed':private_path.unlink()
        engine.dispose()
print(json.dumps(report,ensure_ascii=False))
