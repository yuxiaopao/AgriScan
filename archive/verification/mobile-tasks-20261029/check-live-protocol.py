"""Exercise local real HTTP task ownership and cancellation; no production calls."""
import json,time
from pathlib import Path
from uuid import uuid4
from urllib.request import Request,urlopen
from urllib.error import HTTPError

folder=Path(__file__).resolve().parent;base='http://127.0.0.1:18931/api';checks=[]
def request(path,method='GET',body=None,token=None,raw=False):
    headers={}
    if token:headers['Authorization']='Bearer '+token
    if body is not None:headers['Content-Type']='application/octet-stream' if raw else 'application/json'
    data=body if raw else json.dumps(body).encode() if body is not None else None
    with urlopen(Request(base+path,data=data,method=method,headers=headers),timeout=20) as reply:return json.load(reply)
def check(condition,label):
    assert condition,label
    checks.append(label)
def rejected(path,token,expected):
    try:request(path,token=token)
    except HTTPError as error:return error.code==expected
    return False
login={'username':'qa_mobile_local','password':'REDACTED_SECRET'}
token=request('/auth/login','POST',login)['access_token'];second=None
try:
    plots=request('/plots',token=token);plot=next(row for row in plots if row['name']=='本机任务验证果园')
    image=(folder/'fixture.png').read_bytes()
    bodies=[{'client_request_id':str(uuid4()),'kind':'image','filename':f'qa-frame-{index}.png','content_type':'application/octet-stream','size_bytes':len(image),'crop':'苹果','plot_id':plot['id'],'note':'提交时固定的采样备注'} for index in range(2)]
    one=request('/detection-tasks','POST',bodies[0],token);two=request('/detection-tasks','POST',bodies[1],token)
    check(request('/detection-tasks','POST',bodies[0],token)['id']==one['id'],'same client UUID reserves one server task')
    request('/detection-tasks/'+one['id']+'/file','PUT',image,token,True)
    request('/detection-tasks/'+two['id']+'/file','PUT',image,token,True)
    cancelled=request('/detection-tasks/'+two['id'],'DELETE',token=token)
    check(cancelled['status'] in ['cancelling','cancelled'],'cancellation follows server state instead of claiming immediate success')
    deadline=time.monotonic()+25
    while time.monotonic()<deadline:
        first=request('/detection-tasks/'+one['id'],token=token);other=request('/detection-tasks/'+two['id'],token=token)
        if first['status']=='completed' and other['status']=='cancelled':break
        time.sleep(.1)
    check(first['status']=='completed' and other['status']=='cancelled','uploaded task completes while cancelled task reaches confirmed cancelled')
    check(first['received_bytes']==len(image),'GET task confirms uploaded bytes after an ignored PUT response')
    check(len(first['result_ids'])==1 and not other['result_ids'],'cancelled task saves no observation')
    row=request('/detections/'+first['result_ids'][0],token=token)
    check(row['status']=='awaiting_model' and row['confidence'] is None and not row['boxes'],'model-free image task saves a sample without inventing inference')
    check(row['plot_id']==plot['id'] and row['note']==bodies[0]['note'],'fixed plot and note round-trip through real background task')
    second=request('/auth/login','POST',login)['access_token']
    check(rejected('/detection-tasks/'+one['id'],second,404),'same account new JWT session cannot read old task IDs')
    check(request('/detections/'+row['id'],token=second)['id']==row['id'],'same account keeps its saved observations after a new login')
    check(request('/detection-tasks/'+one['id'],'DELETE',token=token)['status']=='completed','cancelling a completed task retains the saved observation')
finally:
    request('/auth/logout','POST',{},token)
    if second:request('/auth/logout','POST',{},second)
report={'status':'passed','checks':checks,'count':len(checks),'source':'actual local HTTP API with disposable SQLite; inference provider retains AwaitingWeights behavior after a QA-only delay','production_contacted':False,'browser_upload_exercised':False,'native_app_tested':False,'tokens_printed_or_saved':False}
(folder/'live-protocol-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','count':len(checks),'owned_sessions_logged_out':True}))
