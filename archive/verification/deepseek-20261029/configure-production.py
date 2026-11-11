"""Test draft first, then store it through the administrator's encrypted DB API."""
from copy import deepcopy
import base64
import getpass
import json
from pathlib import Path
import re
import subprocess
import sys
import httpx

folder=Path('.runtime/deepseek-20261029')
report={'origin':'https://agriscan.ming-ai.top','configuration_saved':False,'checks':[]}
key=getpass.getpass('Private DeepSeek credential: ')
if not key:
    raise SystemExit('Credential input missing.')
def check(value,label):
    if not value:
        raise RuntimeError(label)
    report['checks'].append(label)
def database(backup=False,proof=False):
    program=(folder/'database-proof.py').read_text(encoding='utf-8')
    program=program.replace('BACKUP = False','BACKUP = '+repr(backup))
    if proof:
        program=program.replace('EXPECTED_KEY = None','EXPECTED_KEY = '+repr(key))
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15',
                           'tencent-server','/srv/agriscan/venv/bin/python -'],
                          input=program,text=True,capture_output=True,timeout=45,check=True)
    return json.loads(result.stdout)
def non_llm(config):
    value=deepcopy(config)
    value.pop('version',None)
    value['integrations']={name:item for name,item in value['integrations'].items() if not name.startswith('llm_')}
    return value
token=None
with httpx.Client(base_url='https://agriscan.ming-ai.top/agriscan/api/',trust_env=False,
                  verify=True,follow_redirects=False,timeout=80) as client:
    def request(method,path,**kwargs):
        headers={'Authorization':'Bearer '+token} if token else {}
        response=client.request(method,path,headers=headers,**kwargs)
        check(key not in response.text,'response omits private credential')
        response.raise_for_status()
        return response
    try:
        access=Path('.runtime/server-admin-access.txt').read_text(encoding='utf-8')
        username=re.search(r'^Username:\s*(.+)$',access,re.M).group(1).strip()
        password=re.search(r'^Password:\s*(.+)$',access,re.M).group(1).strip()
        login=request('POST','auth/login',json={'username':username,'password':password})
        access=username=password=None
        token=login.json()['access_token']
        me=request('GET','auth/me').json()
        check(me['role']=='admin','existing administrator authenticated at production origin')
        before=request('GET','admin/config').json()
        before_db=database(backup=True)
        conversations=request('GET','assistant/conversations').json()
        payload=token.split('.')[1]
        own_user_id=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))['sub']
        baseline={'user_id':own_user_id,'conversation_ids':[row['id'] for row in conversations],
                  'detection_ids':[row['id'] for row in request('GET','detections').json()]}
        (folder/'qa-baseline.json').write_text(json.dumps(baseline,indent=2),encoding='utf-8')
        body={'llm_base_url':'https://api.deepseek.com','llm_model':'deepseek-flash','llm_timeout':60,'llm_api_key':key}
        probe=request('POST','admin/config/llm/test',json=body).json()
        report['draft_probe']=probe
        check(probe['ok'] and probe['text']['ok'] and probe['vision']['ok']
              and probe['configuration_saved'] is False,'production draft passes text and real image test before any save')
        after_probe=request('GET','admin/config').json()
        check(after_probe==before,'connection test preserves configuration and revision')
        check(database()['row_sha256']==before_db['row_sha256'],'connection test leaves encrypted database row unchanged')
        body['llm_enabled']=True
        saved=request('PATCH','admin/config',json={'version':before['version'],'integrations':body}).json()
        report['configuration_saved']=True
        check(saved['integrations']['llm_enabled'] and saved['integrations']['llm_key_configured']
              and saved['integrations']['llm_model']=='deepseek-flash','DeepSeek enabled and secret configured through administrator API')
        check(non_llm(saved)==non_llm(before),'unrelated brand feature limit SMTP and registration settings preserved')
        proof=database(proof=True)
        check(all(proof.get(name) is True for name in ('credential_matches','plaintext_absent_from_json',
              'plaintext_absent_from_ciphertext','audit_contains_no_key')),'database credential decrypts correctly without plaintext storage or audit exposure')
        public=request('GET','client/config').json()
        check('integrations' not in public,'public client configuration contains no integrations or key')
        answer=request('POST','knowledge/ask',json={'question':'接入验收：请简短说明田间发现苹果叶斑点时，首先应该观察和记录什么？不要提供具体农药配方。'}).json()['answer']
        check(isinstance(answer,str) and len(answer.strip())>=20,'actual Xiaohe assistant completes a Chinese agriculture answer with saved configuration')
        report.update(status='passed',config_version=saved['version'],probe=probe,database_proof=proof,
                      actual_assistant_answer_length=len(answer),model='deepseek-flash')
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__)
        print(json.dumps({'status':'failed','error_type':type(error).__name__,
                          'configuration_saved':report['configuration_saved']}),flush=True)
        raise
    finally:
        if token:
            response=client.post('auth/logout',headers={'Authorization':'Bearer '+token})
            report['control_session_revoked']=response.status_code==200
        (folder/'production-configuration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        key=None
print(json.dumps({'status':report['status'],'config_version':report.get('config_version'),
                  'configuration_saved':report['configuration_saved'],'checks':len(report['checks']),
                  'database_encrypted':report.get('database_proof',{}).get('credential_matches')}),flush=True)
