"""One exact approved production QA cleanup. Default mode is read-only."""
import base64
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

import httpx
from sqlalchemy import MetaData, and_, create_engine, delete, inspect, select

PREFIX='2461a4520ca7'
NAME='qa-latest-server-apple.jpg'
NOTE='QA latest production 20261029 full-ui-131640 disposable'
RELEASE='release-20261029-full-ui-131640'
APPLY=sys.argv[1:]==['apply']
if sys.argv[1:] not in (['inspect'],['apply']):raise SystemExit('Use explicit inspect or apply mode.')
report={'status':'prepared','mode':'apply' if APPLY else 'read_only','qa_prefix':PREFIX,
        'started_at':datetime.now(timezone.utc).isoformat(),'mutations':[]}

class Refused(RuntimeError):pass
def require(condition,message):
    if not condition:raise Refused(message)
def encode(value):
    if isinstance(value,(datetime,)):return value.isoformat()
    if isinstance(value,Decimal):return str(value)
    if isinstance(value,bytes):return {'base64':base64.b64encode(value).decode()}
    raise TypeError(type(value).__name__)
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=encode).encode()
def digest(value):return hashlib.sha256(canonical(value)).hexdigest()
def rows(connection,table,condition=None,lock=False):
    query=select(table)
    if condition is not None:query=query.where(condition)
    if lock:query=query.with_for_update()
    return [dict(row) for row in connection.execute(query).mappings()]
def single(items,message):require(len(items)==1,message);return items[0]
def expired(value):return value is None or value.replace(tzinfo=None)<=datetime.now(timezone.utc).replace(tzinfo=None)

env={}
for line in Path('/srv/agriscan/shared/production.env').read_text(encoding='utf-8').splitlines():
    key,separator,value=line.partition('=')
    if separator and key in {'DATABASE_URL','ADMIN_USERNAME','ADMIN_PASSWORD','UPLOAD_DIR'}:env[key]=value.strip().strip('\"\'')
require(all(env.get(key) for key in ['DATABASE_URL','ADMIN_USERNAME','ADMIN_PASSWORD','UPLOAD_DIR']),'Required private environment fields unavailable.')
require(Path('/srv/agriscan/current').resolve().name==RELEASE,'Current release changed; cleanup scope not assumed.')
engine=create_engine(env['DATABASE_URL'],pool_pre_ping=True,echo=False)
metadata=MetaData();metadata.reflect(bind=engine)
tables=metadata.tables
required={'detections','detection_predictions','users','plots','plot_details','assistant_detection_discussions','assistant_conversations','assistant_messages','workspace_configuration','alembic_version','audit_logs','revoked_tokens'}
require(required<=set(tables),'Expected application schema unavailable.')
D=tables['detections'];DD=tables['assistant_detection_discussions'];C=tables['assistant_conversations'];M=tables['assistant_messages'];P=tables['detection_predictions'];U=tables['users']

def schema_state(connection):
    inspector=inspect(connection);schema={}
    for name in sorted(inspector.get_table_names()):
        columns=[{'name':column['name'],'type':str(column['type']),'nullable':column['nullable'],'default':str(column.get('default'))} for column in inspector.get_columns(name)]
        schema[name]={'columns':columns,'pk':inspector.get_pk_constraint(name),'foreign_keys':inspector.get_foreign_keys(name),'indexes':inspector.get_indexes(name)}
    revisions=[row['version_num'] for row in rows(connection,tables['alembic_version'])]
    require(revisions==['20261029_06'],'Schema is not the reviewed ownership revision.')
    configuration=single(rows(connection,tables['workspace_configuration']),'Expected one workspace configuration.')
    require(configuration['version']==6,'Workspace configuration is no longer v6; recheck before cleanup.')
    return {'revision':revisions[0],'schema_sha256':digest(schema),'config_version':6,'config_sha256':digest(configuration)}

def foreign_conversation_references(connection,conversation_id):
    for table in tables.values():
        for foreign in table.foreign_key_constraints:
            elements=list(foreign.elements)
            if not elements or elements[0].column.table.name!='assistant_conversations':continue
            require(len(elements)==1 and elements[0].column.name=='id','Unexpected composite conversation foreign key; refused.')
            column=elements[0].parent
            linked=rows(connection,table,column==conversation_id)
            if table.name not in {'assistant_messages','assistant_detection_discussions'}:
                require(not linked,'Conversation has an additional foreign reference; refused.')
            elif table.name=='assistant_detection_discussions':
                require(len(linked)==1 and linked[0]['user_id']==scope['owner_id'] and linked[0]['detection_id']==scope['id'],'Conversation is referenced by another detection or owner; refused.')

def qa_rows(connection,lock=False):
    detection=single(rows(connection,D,D.c.id==scope['id'],lock),'Exact QA detection missing or duplicated.')
    require(detection['id'].startswith(PREFIX) and detection['name']==NAME and detection['note']==NOTE and detection['owner_id']==scope['owner_id'] and not detection['is_demo'],'QA detection identity markers changed; refused.')
    require(detection['image_url']==scope['image_url'],'QA photo reference changed; refused.')
    discussions=rows(connection,DD,DD.c.detection_id==scope['id'],lock)
    discussion=single(discussions,'Expected exactly one dedicated QA discussion.')
    require(discussion['user_id']==scope['owner_id'] and discussion['conversation_id']==scope['conversation_id'],'QA discussion ownership changed; refused.')
    conversation=single(rows(connection,C,C.c.id==scope['conversation_id'],lock),'Dedicated QA conversation missing.')
    require(conversation['user_id']==scope['owner_id'] and expired(conversation['busy_until']),'QA conversation has another owner or an active reply; refused.')
    messages=sorted(rows(connection,M,M.c.conversation_id==scope['conversation_id'],lock),key=lambda item:item['id'])
    require(len(messages)>=2 and messages[0]['role']=='user' and NAME in messages[0]['content'] and NOTE in messages[0]['content'] and any(row['role']=='assistant' for row in messages),'Conversation does not carry the exact QA analysis markers; refused.')
    foreign_conversation_references(connection,scope['conversation_id'])
    return {'detections':[detection],'detection_predictions':rows(connection,P,P.c.detection_id==scope['id'],lock),
            'assistant_detection_discussions':discussions,'assistant_conversations':[conversation],'assistant_messages':messages}

def fingerprints(connection):
    state={}
    for name,table in tables.items():
        values=[]
        for row in rows(connection,table):
            if name=='detections' and row['id']==scope['id']:continue
            if name=='detection_predictions' and row['detection_id']==scope['id']:continue
            if name=='assistant_detection_discussions' and row['detection_id']==scope['id'] and row['user_id']==scope['owner_id']:continue
            if name=='assistant_conversations' and row['id']==scope['conversation_id']:continue
            if name=='assistant_messages' and row['conversation_id']==scope['conversation_id']:continue
            key=[row[column.name] for column in table.primary_key.columns]
            values.append((digest(key if key else row),digest(row)))
        state[name]=dict(values)
    return state
def business_hash(state):return digest({name:value for name,value in state.items() if name not in {'audit_logs','revoked_tokens'}})
def publish_summary(state):return {name:{'rows':len(value),'sha256':digest(value)} for name,value in state.items()}
def private_file(path,data):
    fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'wb') as output:output.write(data);output.flush();os.fsync(output.fileno())
    require(path.stat().st_mode&0o777==0o600,'Backup permissions are not private.')

token=None;scope=None
try:
    with engine.connect() as connection:
        detection=single(rows(connection,D,D.c.id.like(PREFIX+'%')),'QA ID prefix is not unique; refused.')
        owner=single(rows(connection,U,U.c.username==env['ADMIN_USERNAME']),'Bootstrap administrator identity unavailable.')
        require(owner['role']=='admin' and owner['is_active'] and detection['owner_id']==owner['id'],'QA owner is not the existing bootstrap administrator; refused.')
        require(re.fullmatch('[a-f0-9]{32}',detection['id']) is not None,'Unexpected detection ID format.')
        discussion=single(rows(connection,DD,DD.c.detection_id==detection['id']),'Expected one dedicated QA discussion.')
        image_url=detection['image_url'] or ''
        require(re.fullmatch(r'/api/uploads/[a-f0-9]{32}\.jpg',image_url) is not None,'Unexpected QA image route.')
        scope={'id':detection['id'],'owner_id':owner['id'],'conversation_id':discussion['conversation_id'],'image_url':image_url}
        require(not rows(connection,D,and_(D.c.image_url==image_url,D.c.id!=scope['id'])),'QA photo is referenced by another detection; refused.')
        details=tables['plot_details']
        require(not rows(connection,details,details.c.cover_filename==Path(image_url).name),'QA photo is referenced by a plot cover; refused.')
        owned=qa_rows(connection)
        before_schema=schema_state(connection)
        before=fingerprints(connection)
        require(len(before['detections'])==4,'Expected exactly four non-QA detections; refused.')
    folder=Path(env['UPLOAD_DIR']).resolve();photo=(folder/Path(image_url).name).resolve()
    require(photo.parent==folder and photo.is_file(),'Exact QA image file unavailable.')
    photo_bytes=photo.read_bytes()
    report.update({'detection_id':scope['id'],'conversation_id':scope['conversation_id'],'owner_id':scope['owner_id'],
                   'qa_row_counts':{name:len(value) for name,value in owned.items()},'qa_rows_sha256':digest(owned),
                   'schema_before':before_schema,'non_qa_tables_before':publish_summary(before),'non_qa_business_sha256_before':business_hash(before),
                   'photo_sha256':hashlib.sha256(photo_bytes).hexdigest(),'photo_bytes':len(photo_bytes)})
    if not APPLY:
        report['status']='prepared_read_only'
    else:
        backup_base=Path('/srv/agriscan/shared/backups').resolve()
        backup=backup_base/('qa-latest-full-ui-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
        require(backup_base in backup.resolve().parents,'Backup path escaped approved directory.')
        backup.mkdir(mode=0o700)
        private_file(backup/'qa-rows.json',canonical({'scope':scope,'qa_rows':owned,'schema_before':before_schema,'qa_rows_sha256':digest(owned)}))
        private_file(backup/'qa-original.jpg',photo_bytes)
        report['backup']=str(backup)
        report['mutations'].append('private backup of only exact QA rows and image')
        with httpx.Client(base_url='http://127.0.0.1:18000',trust_env=False,timeout=30) as client:
            login=client.post('/api/auth/login',json={'username':env['ADMIN_USERNAME'],'password':env['ADMIN_PASSWORD']})
            require(login.status_code==200,'Local administrator authentication failed.')
            token=login.json()['access_token'];headers={'Authorization':'Bearer '+token}
            payload=token.split('.')[1];claims=json.loads(base64.urlsafe_b64decode(payload+'='*((-len(payload))%4)))
            jti=claims['jti']
            try:
                me=client.get('/api/auth/me',headers=headers)
                require(me.status_code==200 and me.json()['username']==env['ADMIN_USERNAME'] and me.json()['role']=='admin','Control session is not the bootstrap administrator.')
                current=client.get('/api/detections/'+scope['id'],headers=headers)
                require(current.status_code==200 and current.json()['id']==scope['id'] and current.json()['name']==NAME and current.json()['note']==NOTE,'Local personal API did not confirm exact QA ownership/markers.')
                with engine.connect() as connection:
                    require(digest(qa_rows(connection))==digest(owned),'QA rows changed after backup; refused.')
                    require(schema_state(connection)==before_schema and business_hash(fingerprints(connection))==business_hash(before),'Non-QA data/configuration changed before cleanup; refused.')
                removed=client.delete('/api/detections/'+scope['id'],headers=headers)
                require(removed.status_code==200,'Normal owned detection DELETE API failed.')
                report['mutations'].append('normal owned detection DELETE API: exact QA detection, prediction, image/cache cleanup and appended audit')
                require(client.get('/api/detections/'+scope['id'],headers=headers).status_code==404,'QA detection still accessible.')
                require(client.get(scope['image_url'],headers=headers).status_code==404 and not photo.exists(),'QA image was not removed by normal API.')
                with engine.begin() as connection:
                    conversation=single(rows(connection,C,C.c.id==scope['conversation_id'],True),'QA conversation changed after API deletion.')
                    require(conversation['user_id']==scope['owner_id'] and expired(conversation['busy_until']),'QA conversation became busy or changed owner; stopped.')
                    foreign_conversation_references(connection,scope['conversation_id'])
                    for name,condition in [('assistant_detection_discussions',and_(DD.c.user_id==scope['owner_id'],DD.c.detection_id==scope['id'],DD.c.conversation_id==scope['conversation_id'])),('assistant_messages',M.c.conversation_id==scope['conversation_id']),('assistant_conversations',and_(C.c.id==scope['conversation_id'],C.c.user_id==scope['owner_id']))]:
                        current_rows=rows(connection,tables[name],condition,True)
                        require(digest(sorted(current_rows,key=canonical))==digest(sorted(owned[name],key=canonical)),'Exact QA conversation rows changed; transaction stopped.')
                        result=connection.execute(delete(tables[name]).where(condition))
                        require(result.rowcount==len(owned[name]),'Unexpected QA-only deletion rowcount; transaction stopped.')
                report['mutations'].append('transaction removed only exact same-owner QA discussion, its messages and exclusive conversation')
            finally:
                revoked=client.post('/api/auth/logout',headers=headers)
                report['control_session_revoked']=revoked.status_code==200
                token=None
        with engine.connect() as connection:
            after_schema=schema_state(connection);after=fingerprints(connection)
            require(after_schema==before_schema,'Schema or v6 configuration hash changed.')
            require(business_hash(after)==business_hash(before),'Non-QA business table hashes changed.')
            for name in ['audit_logs','revoked_tokens']:
                require(all(after[name].get(key)==value for key,value in before[name].items()),'A pre-existing audit/session row changed or disappeared.')
            audit=tables['audit_logs'];new_audits=[row for row in rows(connection,audit) if digest([row['id']]) not in before['audit_logs']]
            require(len(new_audits)==1 and new_audits[0]['actor_id']==scope['owner_id'] and new_audits[0]['resource_id']==scope['id'] and new_audits[0]['resource_type']=='detection' and new_audits[0]['action']=='delete','Unexpected append-only audit delta; original audit rows retained.')
            revoked=tables['revoked_tokens'];new_tokens=[row for row in rows(connection,revoked) if digest([row['jti']]) not in before['revoked_tokens']]
            require(len(new_tokens)==1 and new_tokens[0]['jti']==jti and report['control_session_revoked'],'Unexpected session revocation delta.')
            require(not rows(connection,D,D.c.id==scope['id']) and not rows(connection,P,P.c.detection_id==scope['id']) and not rows(connection,DD,DD.c.detection_id==scope['id']) and not rows(connection,C,C.c.id==scope['conversation_id']) and not rows(connection,M,M.c.conversation_id==scope['conversation_id']),'An exact QA row remains.')
        report.update({'status':'passed','schema_after':after_schema,'non_qa_tables_after':publish_summary(after),'non_qa_business_sha256_after':business_hash(after),
                       'preserved_detection_count':len(after['detections']),'non_qa_business_unchanged':True,'existing_audit_and_session_rows_unchanged':True,
                       'appended_normal_delete_audits':len(new_audits),'appended_own_session_revocations':len(new_tokens)})
        private_file(backup/'cleanup-report.json',canonical(report))
except Exception as error:
    report['status']='refused_or_incomplete'
    report['error']=str(error) if isinstance(error,Refused) else type(error).__name__
finally:
    report['finished_at']=datetime.now(timezone.utc).isoformat()
    engine.dispose()
print(json.dumps(report,ensure_ascii=False,default=encode))
if report['status']=='refused_or_incomplete':raise SystemExit(1)
