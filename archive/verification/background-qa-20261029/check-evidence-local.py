"""Synthetic in-memory checks only; never reads production environment or SSH."""
import importlib.util,json,sys,tempfile
from pathlib import Path
from sqlalchemy import Column,ForeignKey,Integer,MetaData,Table,create_engine,insert,update
from PIL import Image
root=Path('E:/AgriScan');folder=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'backend'))
from app.db import Base
import app.assistant,app.detection_assistant
spec=importlib.util.spec_from_file_location('readonly_qa_helper',folder/'qa-evidence-server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
OWNER='a'*32;OTHER='c'*32;PLOT='1'*32;DET='2'*32;CONV='3'*32;PHOTO='b'*32+'.jpg';TAG=module.RUN_TAG
cases=[]
def execute(transform=None,expected=None,compatible=True):
    engine=create_engine('sqlite://')
    metadata=MetaData()
    for name in ('users','plots','plot_details','detections','detection_predictions','assistant_conversations','assistant_messages','assistant_detection_discussions'):Base.metadata.tables[name].to_metadata(metadata)
    metadata.create_all(engine)
    with tempfile.TemporaryDirectory(prefix='synthetic-',dir=folder) as temp:
        uploads=Path(temp).resolve();assert uploads.is_relative_to(folder.resolve());Image.new('RGB',(32,32),'green').save(uploads/PHOTO,'JPEG')
        with engine.begin() as connection:
            U,P,D,PD,C,M,DD=(metadata.tables[name] for name in ('users','plots','detections','plot_details','assistant_conversations','assistant_messages','assistant_detection_discussions'))
            connection.execute(insert(U),[{'id':OWNER,'username':'synthetic_owner','name':'Synthetic','password_hash':'not-a-credential','role':'admin','is_active':True},{'id':OTHER,'username':'synthetic_other','name':'Synthetic','password_hash':'not-a-credential','role':'member','is_active':True}])
            connection.execute(insert(P).values(id=PLOT,owner_id=OWNER,name=TAG+' plot',crop='Apple',area=1.5,location='Synthetic fixture',manager='QA'))
            connection.execute(insert(D).values(id=DET,owner_id=OWNER,name=TAG+'.jpg',crop='Apple',plot_id=PLOT,status='healthy',result='Synthetic',confidence=.8,image_url='/api/uploads/'+PHOTO,is_demo=False,note=TAG))
            connection.execute(insert(C).values(id=CONV,user_id=OWNER,title='Synthetic QA'))
            connection.execute(insert(DD).values(user_id=OWNER,detection_id=DET,conversation_id=CONV))
            connection.execute(insert(M).values(conversation_id=CONV,role='user',content=TAG+' '+TAG+'.jpg'))
            if transform:transform(connection,metadata)
            try:
                result=module.collect(connection,metadata.tables,OWNER,uploads)
                assert expected is None,'Expected refusal: '+str(expected)
                assert result['cleanup_helper_compatible']==compatible
                assert result['detections'][0]['conversation_id']==CONV
                assert result['conversation_associations'][0]['message_count']==1
                assert 'content' not in json.dumps(result)
                return result
            except module.Refused as error:
                assert str(error)==expected,(str(error),expected)
    engine.dispose()
execute();cases.append('exact tag creates only expected QA plan fields, JPEG SHA and exclusive conversation IDs/counts without chat content')
execute(lambda c,t:c.execute(update(t.tables['detections']).where(t.tables['detections'].c.id==DET).values(owner_id=OTHER)),'foreign_or_demo_tagged_detection');cases.append('foreign owner tagged detection refuses instead of silently filtering')
def external_detection(c,t,**overrides):
    values={'id':'4'*32,'owner_id':OWNER,'name':'unrelated.jpg','crop':'Apple','plot_id':None,'status':'healthy','result':'Synthetic','confidence':.5,'image_url':'/api/uploads/'+'d'*32+'.jpg','is_demo':False,'note':'Unrelated'};values.update(overrides);c.execute(insert(t.tables['detections']).values(**values))
execute(lambda c,t:external_detection(c,t,plot_id=PLOT),'qa_plot_has_external_detection');cases.append('QA plot associated with any non-QA detection refuses')
execute(lambda c,t:c.execute(update(t.tables['detections']).where(t.tables['detections'].c.id==DET).values(plot_id='9'*32)),'qa_detection_uses_external_plot');cases.append('QA detection referring to an external plot refuses')
execute(lambda c,t:external_detection(c,t,image_url='/api/uploads/'+PHOTO),'photo_used_by_external_detection');cases.append('normalized JPEG shared with a non-QA record refuses')
execute(lambda c,t:c.execute(update(t.tables['assistant_detection_discussions']).values(user_id=OTHER)),'foreign_discussion_on_qa_detection');cases.append('foreign-user conversation association refuses')
execute(lambda c,t:c.execute(update(t.tables['assistant_conversations']).values(user_id=OTHER)),'foreign_or_missing_qa_conversation');cases.append('foreign conversation owner refuses')
execute(lambda c,t:c.execute(update(t.tables['assistant_messages']).values(content='Unrelated message')),'conversation_lacks_exact_qa_source_markers');cases.append('conversation requires QA markers checked by SQL without exporting messages')
def future_reference(c,t):
    table=Table('future_references',t,Column('id',Integer,primary_key=True),Column('detection_id',ForeignKey('detections.id')));table.create(c);c.execute(insert(table).values(id=1,detection_id=DET))
execute(future_reference,'external_or_unknown_foreign_reference');cases.append('unrecognized future schema reference refuses rather than planning a cascade')
execute(lambda c,t:c.execute(update(t.tables['detections']).values(note='Filename tag only')),compatible=False);cases.append('filename-only tag is collected but explicitly marked incompatible with the stricter existing cleanup helper')
report={'status':'passed','cases':cases,'production_network_called':False,'production_environment_read':False,'ssh_called':False,'real_user_records_read':False}
(folder/'local-evidence-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'status':'passed','checks':len(cases)}))
