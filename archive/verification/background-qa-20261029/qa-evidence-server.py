"""Read only an exact authorized QA tag; never clean up or expose unrelated rows."""
import argparse,hashlib,io,json,re,sys
from datetime import datetime,timezone
from pathlib import Path
from dotenv import dotenv_values
from PIL import Image
from sqlalchemy import MetaData,and_,create_engine,func,or_,select,text

ROOT=Path('/srv/agriscan')
RUN_TAG='QA-BACKGROUND-20261029-1814'
ID=re.compile(r'[0-9a-f]{32}')
IMAGE=re.compile(r'[0-9a-f]{32}\.jpg')
class Refused(RuntimeError):pass
def require(condition,code):
    if not condition:raise Refused(code)
def row_list(connection,table,condition,columns=None):
    return [dict(row) for row in connection.execute(select(*(columns or [table])).where(condition)).mappings()]
def count(connection,table,condition):return connection.execute(select(func.count()).select_from(table).where(condition)).scalar_one()
def jpeg(folder,filename):
    require(isinstance(filename,str) and bool(IMAGE.fullmatch(filename)),'invalid_normalized_photo_name')
    path=folder/filename
    require(path.parent.resolve()==folder and path.is_file() and not path.is_symlink(),'normalized_photo_unavailable')
    with Image.open(path) as image:
        require(image.format=='JPEG','normalized_photo_not_jpeg');image.verify()
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return digest

def collect(connection,tables,owner_id,folder,run_tag=RUN_TAG):
    require(run_tag==RUN_TAG,'unexpected_run_tag');require(bool(ID.fullmatch(owner_id)),'owner_id_required')
    names={'users','detections','plots','plot_details','detection_predictions','assistant_detection_discussions','assistant_conversations','assistant_messages'}
    require(names<=set(tables),'expected_schema_unavailable')
    U,D,P,PD,DP,DD,C,M=(tables[name] for name in ('users','detections','plots','plot_details','detection_predictions','assistant_detection_discussions','assistant_conversations','assistant_messages'))
    owners=row_list(connection,U,U.c.id==owner_id,[U.c.id,U.c.role,U.c.is_active])
    require(len(owners)==1 and owners[0]['role']=='admin' and owners[0]['is_active'],'expected_active_admin_owner_required')
    detections=row_list(connection,D,or_(D.c.name.contains(run_tag,autoescape=True),D.c.note.contains(run_tag,autoescape=True)))
    plots=row_list(connection,P,or_(P.c.name.contains(run_tag,autoescape=True),P.c.location.contains(run_tag,autoescape=True)))
    require(0<len(detections)+len(plots)<=64,'qa_scope_empty_or_too_large')
    require(all(row['owner_id']==owner_id and not row['is_demo'] for row in detections),'foreign_or_demo_tagged_detection')
    require(all(row['owner_id']==owner_id for row in plots),'foreign_tagged_plot')
    det_ids={row['id'] for row in detections};plot_ids={row['id'] for row in plots}
    require(all(ID.fullmatch(value) for value in det_ids|plot_ids),'invalid_qa_id')
    require(all(row['plot_id'] is None or row['plot_id'] in plot_ids for row in detections),'qa_detection_uses_external_plot')
    require(not count(connection,D,and_(D.c.plot_id.in_(plot_ids),~D.c.id.in_(det_ids))),'qa_plot_has_external_detection')
    details=row_list(connection,PD,PD.c.plot_id.in_(plot_ids))
    require(len({row['plot_id'] for row in details})==len(details),'duplicate_plot_detail')
    covers={row['plot_id']:row['cover_filename'] for row in details}
    files={};det_plan=[];plot_plan=[];associations=[];compatibility=[]
    links=row_list(connection,DD,DD.c.detection_id.in_(det_ids))
    require(all(row['user_id']==owner_id for row in links),'foreign_discussion_on_qa_detection')
    conv_ids={row['conversation_id'] for row in links}
    require(len(conv_ids)==len(links) and all(ID.fullmatch(value) for value in conv_ids),'conversation_not_exclusive')
    require(len({row['detection_id'] for row in links})==len(links),'multiple_conversations_for_qa_detection')
    conv_by_det={row['detection_id']:row['conversation_id'] for row in links}
    require(not count(connection,DD,and_(DD.c.conversation_id.in_(conv_ids),or_(~DD.c.detection_id.in_(det_ids),DD.c.user_id!=owner_id))),'conversation_has_external_discussion')
    for row in detections:
        value=row['image_url'] or ''
        require(value.startswith('/api/uploads/'),'invalid_qa_image_url')
        filename=value.removeprefix('/api/uploads/');files[filename]=jpeg(folder,filename)
        conversation=conv_by_det.get(row['id'])
        if conversation:
            chats=row_list(connection,C,C.c.id==conversation,[C.c.id,C.c.user_id,C.c.busy_until])
            require(len(chats)==1 and chats[0]['user_id']==owner_id,'foreign_or_missing_qa_conversation')
            require(not count(connection,C,and_(C.c.id==conversation,C.c.title=='你好')),'protected_conversation_title')
            busy=chats[0]['busy_until'];require(busy is None or busy.replace(tzinfo=None)<datetime.now(timezone.utc).replace(tzinfo=None),'qa_conversation_busy')
            # Proof is evaluated inside SQL; no chat text is fetched or returned.
            proof=and_(M.c.conversation_id==conversation,M.c.role=='user',M.c.content.contains(run_tag,autoescape=True),M.c.content.contains(row['name'],autoescape=True))
            require(count(connection,M,proof)>0,'conversation_lacks_exact_qa_source_markers')
            associations.append({'detection_id':row['id'],'conversation_id':conversation,'owner_id':owner_id,'message_count':count(connection,M,M.c.conversation_id==conversation),'source_markers_verified_in_sql':True})
        if run_tag not in row['note']:compatibility.append({'detection_id':row['id'],'reason':'Existing cleanup helper requires tag in note; filename-only selection needs a separately reviewed cleanup plan.'})
        det_plan.append({key:row[key] for key in ('id','name','note','image_url') }|{'source_image_sha256':files[filename],'conversation_id':conversation})
    for row in plots:
        cover=covers.get(row['id']);digest=jpeg(folder,cover) if cover else None
        if cover:files[cover]=digest
        plot_plan.append({key:row[key] for key in ('id','name','crop','area','location','manager')}|{'cover_filename':cover,'cover_sha256':digest})
    for filename in files:
        require(not count(connection,D,and_(D.c.image_url=='/api/uploads/'+filename,~D.c.id.in_(det_ids))),'photo_used_by_external_detection')
        require(not count(connection,PD,and_(PD.c.cover_filename==filename,~PD.c.plot_id.in_(plot_ids))),'photo_used_by_external_cover')
    allowed={'detections':D.c.id.in_(det_ids),'plots':P.c.id.in_(plot_ids),'plot_details':PD.c.plot_id.in_(plot_ids),
      'detection_predictions':DP.c.detection_id.in_(det_ids),'assistant_detection_discussions':and_(DD.c.user_id==owner_id,DD.c.detection_id.in_(det_ids),DD.c.conversation_id.in_(conv_ids)),
      'assistant_conversations':C.c.id.in_(conv_ids),'assistant_messages':M.c.conversation_id.in_(conv_ids)}
    scopes={'detections':det_ids,'plots':plot_ids,'assistant_conversations':conv_ids}
    for table in tables.values():
        for constraint in table.foreign_key_constraints:
            elements=list(constraint.elements)
            if not elements or elements[0].column.table.name not in scopes:continue
            require(len(elements)==1 and elements[0].column.name=='id','unknown_composite_reference')
            condition=elements[0].parent.in_(scopes[elements[0].column.table.name])
            if table.name in allowed:condition=and_(condition,~allowed[table.name])
            require(not count(connection,table,condition),'external_or_unknown_foreign_reference')
    return {'detections':sorted(det_plan,key=lambda row:row['id']),'plots':sorted(plot_plan,key=lambda row:row['id']),
      'conversation_associations':associations,'owner_id':owner_id,'normalized_photo_sha256':files,
      'prediction_row_count':count(connection,DP,DP.c.detection_id.in_(det_ids)),
      'cleanup_helper_compatible':not compatibility,'cleanup_helper_review_notes':compatibility}

def private_environment():
    values={};pattern=re.compile(r'^\s*(?:export\s+)?(?:DATABASE_URL|UPLOAD_DIR)\s*=')
    with (ROOT/'shared/production.env').open(encoding='utf-8') as stream:
        for line in stream:
            if pattern.match(line):values.update(dotenv_values(stream=io.StringIO(line),interpolate=False))
    require(str(values.get('DATABASE_URL','')).startswith('mysql+pymysql://') and values.get('UPLOAD_DIR'),'mysql_upload_runtime_unavailable')
    return values
def execute(owner_id,run_tag):
    require(run_tag==RUN_TAG and bool(ID.fullmatch(owner_id)),'exact_tag_and_owner_required')
    release=str((ROOT/'current').resolve());require(bool(re.fullmatch(r'/srv/agriscan/releases/release-[a-z0-9-]{6,100}',release)),'unexpected_release_path')
    env=private_environment();folder=Path(env['UPLOAD_DIR']).resolve();require(folder.is_dir() and folder.is_relative_to((ROOT/'shared').resolve()),'unexpected_upload_root')
    engine=create_engine(env['DATABASE_URL'],echo=False,isolation_level='AUTOCOMMIT')
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
            try:
                metadata=MetaData();metadata.reflect(bind=connection)
                qa=collect(connection,metadata.tables,owner_id,folder,run_tag)
                state=connection.execute(text("SELECT version,SHA2(CONCAT_WS(CHAR(31),id,version,CAST(data AS CHAR),COALESCE(encrypted_secrets,''),COALESCE(updated_by,''),COALESCE(CAST(updated_at AS CHAR),'')),256) AS row_sha256 FROM workspace_configuration WHERE id='workspace'")).mappings().one()
                revision=connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
            finally:connection.exec_driver_sql('ROLLBACK')
        require(str((ROOT/'current').resolve())==release,'release_changed_during_read')
        plan={'run_tag':run_tag,'expected_current':release,'expected_configuration_version':int(state['version']),
          'expected_configuration_sha256':state['row_sha256'],'owner_id':owner_id,'detections':qa['detections'],'plots':qa['plots']}
        return {'status':'prepared_read_only','checked_at':datetime.now(timezone.utc).isoformat(),'run_tag':run_tag,
          'current_release':release,'schema':revision,'configuration':{'version':int(state['version']),'canonical_sql_row_sha256':state['row_sha256']},
          'cleanup_plan':plan,'evidence':qa,'selection':'Only literal exact run tag in detection name/note or plot name/location; explicit owner required',
          'normalized_photo_hash_method':'SHA256 of stored normalized JPEG bytes; no image returned or rewritten',
          'chat_content_returned':False,'non_qa_rows_returned':False,'production_mutations':False}
    finally:engine.dispose()
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-tag',required=True);parser.add_argument('--owner-id',required=True);args=parser.parse_args()
    try:report=execute(args.owner_id,args.run_tag)
    except Refused as error:report={'status':'refused','reason':str(error),'production_mutations':False}
    except Exception:report={'status':'refused','reason':'read_only_evidence_unavailable','production_mutations':False}
    print('RESULT '+json.dumps(report,ensure_ascii=False,default=str));return 0 if report['status']=='prepared_read_only' else 1
if __name__=='__main__':raise SystemExit(main())
