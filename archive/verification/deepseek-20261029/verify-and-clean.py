"""Verify only our browser fixture, then remove its exact row/conversation IDs."""
import json
from pathlib import Path
import re
import subprocess
import httpx

folder=Path('.runtime/deepseek-20261029')
baseline=json.loads((folder/'qa-baseline.json').read_text(encoding='utf-8'))
configuration=json.loads((folder/'production-configuration.json').read_text(encoding='utf-8'))
note='qa_deepseek_20261029_browser_leaf'
question='接入验收20261029：请把下一步巡田记录整理成三条简短清单。'
report={'status':'running','checks':[]}
def check(value,label):
    if not value: raise RuntimeError(label)
    report['checks'].append(label)
token=None
with httpx.Client(base_url='https://agriscan.ming-ai.top/agriscan/api/',
                  trust_env=False,verify=True,timeout=75) as client:
    def call(method,path,**kwargs):
        response=client.request(method,path,headers={'Authorization':'Bearer '+token} if token else {},**kwargs)
        response.raise_for_status()
        return response
    try:
        access=Path('.runtime/server-admin-access.txt').read_text(encoding='utf-8')
        login=call('POST','auth/login',json={'username':re.search(r'^Username:\s*(.+)$',access,re.M).group(1).strip(),
                'password':re.search(r'^Password:\s*(.+)$',access,re.M).group(1).strip()})
        access=None
        token=login.json()['access_token']
        config=call('GET','admin/config').json()
        check(config['version']==6 and config['integrations']['llm_enabled'] and config['integrations']['llm_key_configured'],
              'enabled encrypted configuration survives browser test and independent login')
        proof_program=(folder/'database-proof.py').read_text(encoding='utf-8')
        proof_result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server',
                    '/srv/agriscan/venv/bin/python -'],input=proof_program,text=True,encoding='utf-8',capture_output=True,timeout=45,check=True)
        proof=json.loads(proof_result.stdout)
        check(proof['row_sha256']==configuration['database_proof']['row_sha256'],
              'browser connection test did not modify saved encrypted configuration')
        rows=call('GET','detections').json()
        owned=[row for row in rows if row.get('note')==note]
        check(len(owned)==1,'exact single owned browser detection found')
        row=owned[0]
        check(row['id'].startswith('210f9a8ef072') and row['id'] not in baseline['detection_ids']
              and row['crop']=='苹果' and len(row['boxes'])==1,'fixture identity and real detector output match browser evidence')
        detail=call('POST','assistant/detections/'+row['id']+'/analysis').json()
        messages=detail['messages']
        check(len(messages)==4 and [m['role'] for m in messages]==['user','assistant','user','assistant'],
              'image interpretation and follow-up are persisted in the same conversation')
        check(note in messages[0]['content'] and messages[2]['content']==question,
              'persisted conversation belongs to this exact browser QA fixture')
        check(all(label in messages[1]['content'] for label in ('检测结果解读','叶片可见异常','虫害线索','现在可以做什么','复拍与复检建议','何时联系农技人员')),
              'actual image analysis contains all six requested sections')
        check(len(messages[3]['content'])>60,'saved follow-up contains a substantive real response')
        conversation_id=detail['conversation']['id']
        check(conversation_id not in baseline['conversation_ids'],'owned conversation was not a pre-existing conversation')
        # Exact parameterized IDs; inspect ownership and expected messages inside transaction.
        program='''import json
from dotenv import dotenv_values
from sqlalchemy import create_engine,text
engine=create_engine(dotenv_values('/srv/agriscan/shared/production.env')['DATABASE_URL'])
with engine.begin() as db:
    chat=db.execute(text('SELECT user_id FROM assistant_conversations WHERE id=:id FOR UPDATE'),{'id':CHAT}).mappings().one()
    assert chat['user_id']==USER
    links=db.execute(text('SELECT user_id,detection_id FROM assistant_detection_discussions WHERE conversation_id=:id'),{'id':CHAT}).mappings().all()
    assert len(links)==1 and links[0]['user_id']==USER and links[0]['detection_id']==DETECTION
    messages=db.execute(text('SELECT role,content FROM assistant_messages WHERE conversation_id=:id ORDER BY id'),{'id':CHAT}).mappings().all()
    assert len(messages)==4 and NOTE in messages[0]['content'] and messages[2]['content']==QUESTION
    db.execute(text('DELETE FROM assistant_detection_discussions WHERE conversation_id=:id AND user_id=:user'),{'id':CHAT,'user':USER})
    deleted_messages=db.execute(text('DELETE FROM assistant_messages WHERE conversation_id=:id'),{'id':CHAT}).rowcount
    deleted_chats=db.execute(text('DELETE FROM assistant_conversations WHERE id=:id AND user_id=:user'),{'id':CHAT,'user':USER}).rowcount
    assert deleted_messages==4 and deleted_chats==1
print(json.dumps({'deleted_conversations':deleted_chats,'deleted_messages':deleted_messages}))
'''
        for name,value in {'CHAT':conversation_id,'USER':baseline['user_id'],'DETECTION':row['id'],'NOTE':note,'QUESTION':question}.items():
            program=program.replace(name,repr(value))
        result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server',
                               '/srv/agriscan/venv/bin/python -'],input=program,text=True,encoding='utf-8',capture_output=True,timeout=45,check=True)
        cleanup=json.loads(result.stdout)
        check(cleanup=={'deleted_conversations':1,'deleted_messages':4},'only exact owned conversation and four messages removed')
        latest=call('GET','detections/'+row['id']).json()
        check(latest['note']==note,'owned detection identity rechecked immediately before removal')
        call('DELETE','detections/'+row['id'])
        headers={'Authorization':'Bearer '+token}
        check(client.get('detections/'+row['id'],headers=headers).status_code==404,'owned test detection no longer exists')
        check(client.get(row['image_url'].replace('/api/','',1),headers=headers).status_code==404,'owned image file removed')
        remaining=call('GET','detections').json()
        check(set(baseline['detection_ids']).issubset({item['id'] for item in remaining})
              and not any(item.get('note')==note for item in remaining),'all pre-existing business detections retained')
        chats=call('GET','assistant/conversations').json()
        check(set(baseline['conversation_ids']).issubset({item['id'] for item in chats})
              and conversation_id not in {item['id'] for item in chats},'all pre-existing conversations retained')
        report.update(status='passed',owned_detection_id=row['id'],owned_conversation_id=conversation_id,
                      retained_detections=len(remaining),analysis_characters=len(messages[1]['content']),
                      followup_characters=len(messages[3]['content']),cleanup=cleanup,config_version=config['version'])
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__)
        raise
    finally:
        if token:
            report['control_session_revoked']=client.post('auth/logout',headers={'Authorization':'Bearer '+token}).status_code==200
        (folder/'final-production.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'checks':len(report['checks']),'cleanup':report.get('cleanup'),
                  'retained_detections':report.get('retained_detections'),'config_version':report.get('config_version')}))
