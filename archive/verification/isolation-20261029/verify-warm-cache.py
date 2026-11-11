import json
from pathlib import Path
import subprocess

folder=Path(__file__).resolve().parent
manifest=json.loads((folder/'qa-fixtures.json').read_text(encoding='utf-8'))
run_id='qa_iso_20261029_'+manifest['suffix']
source=r'''
import json,sys
from pathlib import Path
import httpx
from dotenv import dotenv_values
from sqlalchemy import create_engine,text
sys.path.insert(0,'/srv/agriscan/current/backend')
from app.cache import DashboardCache
run_id=RUN_ID
private=json.loads((Path('/srv/agriscan/shared/logs')/(run_id+'-credentials.json')).read_text())
environment=dotenv_values('/srv/agriscan/shared/production.env')
engine=create_engine(environment['DATABASE_URL'])
cache=DashboardCache(environment['REDIS_URL'])
report={'status':'running','run_id':run_id,'checks':[],'entries':[]}
tokens={}
try:
    assert cache.client is not None and cache.client.ping()
    with httpx.Client(base_url='http://127.0.0.1:18000',trust_env=False,timeout=30) as client:
        try:
            for actor in ['a','b']:
                account=private['accounts'][actor]
                response=client.post('/api/auth/login',json={'username':account['username'],'password':account['password']})
                assert response.status_code==200
                tokens[actor]=response.json()['access_token']
            for days in [7,30]:
                for actor in ['a','b','a']:
                    response=client.get('/api/dashboard',params={'days':days},headers={'Authorization':'Bearer '+tokens[actor]})
                    assert response.status_code==200
                    account=private['accounts'][actor]
                    key=cache.key(days,account['id'])
                    raw=cache.client.get(key)
                    assert raw is not None
                    saved=json.loads(raw)
                    with engine.connect() as connection:
                        owned=set(connection.execute(text('SELECT id FROM detections WHERE owner_id=:owner'),{'owner':account['id']}).scalars())
                    assert saved==response.json()
                    assert saved['stats']['total']==len(owned)
                    assert {row['id'] for row in saved['recent']}<=owned
                    assert sum(day['total'] for day in saved['trend'])==len(owned)
                    ttl=cache.client.ttl(key)
                    assert 0<ttl<=30
                    report['checks'].append(actor+' '+str(days)+' cache value matches own MySQL rows and API, TTL valid')
                    report['entries'].append({'actor':actor,'days':days,'key':key,'total':saved['stats']['total'],'ttl':ttl})
        finally:
            for actor,token in tokens.items():
                report.setdefault('revoked_sessions',{})[actor]=client.post('/api/auth/logout',headers={'Authorization':'Bearer '+token}).status_code==200
    assert len({entry['key'] for entry in report['entries']})==4
    report['checks'].append('two owners and two day periods use four different Redis keys')
    report['status']='passed'
except Exception as error:
    report['status']='failed';report['error_type']=type(error).__name__
finally:
    cache.close();engine.dispose()
print(json.dumps(report))
'''.replace('RUN_ID',repr(run_id))
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server',
                       '/srv/agriscan/venv/bin/python -'],input=source,text=True,capture_output=True,timeout=75)
if result.returncode:raise SystemExit('Cache verification transport failed; credentials were not printed.')
report=json.loads(result.stdout)
(folder/'production-cache.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'checks':len(report['checks']),'unique_cache_keys':len({entry['key'] for entry in report['entries']}),'report':str(folder/'production-cache.json')}))
if report['status']!='passed':raise SystemExit(1)
