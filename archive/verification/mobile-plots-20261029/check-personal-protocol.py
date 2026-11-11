"""Local isolated HTTP protocol checks for the mobile form; no production access."""
import io,json,os,secrets,sys
from pathlib import Path
from tempfile import TemporaryDirectory

root=Path('E:/AgriScan');folder=Path(__file__).resolve().parent
os.environ.update(MODEL_MANIFEST='',CLASSIFICATION_MODEL_MANIFEST='',LLM_ENABLED='false',REDIS_URL='',DATABASE_URL='sqlite://',DEMO_MODE='true')
sys.path.insert(0,str(root/'backend'))
from fastapi.testclient import TestClient
from PIL import Image
from app.config import Settings
from app.main import create_app

checks=[]
def check(value,label):
    assert value,label
    checks.append(label)

with TemporaryDirectory(prefix='protocol-',dir=folder) as temporary:
    password=secrets.token_urlsafe(24)
    settings=Settings(database_url=f"sqlite:///{Path(temporary)/'qa.db'}",upload_dir=Path(temporary)/'uploads',redis_url='',model_manifest='',classification_model_manifest='',demo_mode=True,admin_username='local_plot_qa',admin_password=password,registration_enabled=True,email_verification_enabled=False,llm_enabled=False,max_upload_bytes=100)
    with TestClient(create_app(settings)) as client:
        response=client.post('/api/auth/login',json={'username':'local_plot_qa','password':password})
        headers={'Authorization':'Bearer '+response.json()['access_token']}
        body=json.loads((folder/'draft-checks.json').read_text(encoding='utf-8'))['request_body']
        body['latitude'],body['longitude']=0,121
        created=client.post('/api/plots',json=body,headers=headers)
        check(created.status_code==201,'personal create accepts actual mobile draft body')
        plot=created.json();plot_id=plot['id']
        check(plot['name']==body['name'] and plot['area']==2.5 and plot['latitude']==0,'created fields and zero coordinate are preserved')
        check(len(client.get('/api/plots',headers=headers).json())==1,'new account sees only its newly created plot')
        check(client.patch('/api/plots/'+plot_id,json={'latitude':5},headers=headers).status_code==422,'unpaired coordinates are rejected by real API')
        cleared=client.patch('/api/plots/'+plot_id,json={**body,'name':'已编辑果园','latitude':None,'longitude':None},headers=headers)
        check(cleared.status_code==200 and cleared.json()['latitude'] is None and cleared.json()['longitude'] is None,'edit and paired coordinate removal round-trip')
        failed=client.post('/api/plots/'+plot_id+'/cover',headers=headers,files={'file':('unreadable.png',b'invalid image bytes','image/png')})
        check(failed.status_code==422,'cover can fail independently after successful plot creation')
        image=io.BytesIO();Image.new('RGB',(1,1),'green').save(image,format='PNG')
        covered=client.post('/api/plots/'+plot_id+'/cover',headers=headers,files={'file':('small.png',image.getvalue(),'image/png')})
        check(covered.status_code==200 and bool(covered.json()['cover_url']),'cover retry updates the existing plot ID')
        rows=client.get('/api/plots',headers=headers).json()
        check(len(rows)==1 and rows[0]['id']==plot_id,'retrying only cover does not create another plot')
        check(client.get(covered.json()['cover_url'],headers=headers).status_code==200,'owner can read uploaded cover through personal protected image endpoint')
        observation=client.post('/api/detections',headers=headers,data={'crop':'苹果','plot_id':plot_id},files={'file':('leaf.png',image.getvalue(),'image/png')})
        check(observation.status_code==201 and observation.json()['plot_id']==plot_id,'personal observation can be linked to the created plot')
        check(any(row['id']==observation.json()['id'] and row['plot_id']==plot_id for row in client.get('/api/detections',headers=headers).json()),'personal records retain the plot association for the mobile detail view')
        check(client.patch('/api/plots/'+plot_id,json={'crop':'玉米'},headers=headers).status_code==409,'a plot with observations cannot silently change its crop')
        check(client.post('/api/plots',headers=headers,json={**body,'owner_id':'other'}).status_code==422,'personal route refuses owner assignment')
        check(client.get('/api/plots').status_code==200 and all(row['id']!=plot_id for row in client.get('/api/plots').json()),'anonymous demo cannot see the owned plot')
        client.post('/api/auth/logout',headers=headers)
report={'status':'passed','checks':checks,'count':len(checks),'scope':'temporary local SQLite TestClient and generated image bytes','production_contacted':False,'actual_ui_clicked':False,'native_app_tested':False}
(folder/'protocol-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','count':len(checks),'temporary_data_removed':True}))
