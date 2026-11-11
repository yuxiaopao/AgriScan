"""Only stubbed HTTP/SQL; asserts private metadata and bodies never escape reports."""
import importlib.util,io,json
from pathlib import Path
folder=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('readonly_boundary',folder/'boundary-probe-server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
cases=[];owner='a'*32;foreign='b'*32;photo='c'*32+'.jpg'
class Response(io.BytesIO):
    def __init__(self,code,body=b'',forbid_read=False):super().__init__(body);self.code=code;self.headers={'Cache-Control':'private, no-store','Vary':'Authorization'};self.forbid_read=forbid_read
    def read(self,*args):
        assert not self.forbid_read,'Foreign response body was read'
        return super().read(*args)
def run(detail=404,image=404,exists=True,login_status=200):
    calls=[]
    def request(path,token=None,payload=None):
        calls.append(path)
        if path=='/auth/login':return Response(login_status,json.dumps({'access_token':'REDACTED_SECRET','user':{'username':'SyntheticAdmin','role':'admin'}}).encode(),forbid_read=login_status!=200)
        if path=='/auth/logout':return Response(200,b'{}',True)
        return Response(detail if path.startswith('/detections/') else image,b'PRIVATE BODY MUST NEVER BE READ',True)
    module.request=request
    module.mysql=lambda sql:[owner] if 'FROM users' in sql else [foreign+'\t/api/uploads/'+photo] if exists else []
    report=module.execute({'username':'SyntheticAdmin','password':'REDACTED_SECRET'})
    serialized=json.dumps(report)
    for value in (owner,foreign,photo,'SyntheticPassword','SyntheticToken','SyntheticAdmin','PRIVATE BODY'):assert value not in serialized
    return report,calls
report,calls=run();assert report['status']=='passed' and report['checks']['personal_record_detail']['status_code']==404 and report['checks']['personal_record_image']['status_code']==404;assert calls[-1]=='/auth/logout';cases.append('two forbidden GETs require 404, record only cache headers and never read foreign bodies or expose IDs/filenames')
report,calls=run(detail=200);assert report['status']=='failed';cases.append('unexpected personal detail access is a failure without reading the exposed body')
report,calls=run(image=200);assert report['status']=='failed';cases.append('unexpected private image access is a failure without consuming the image')
report,calls=run(exists=False);assert report['status']=='skipped' and all(path.startswith('/auth/') for path in calls);cases.append('absence of foreign owned records skips without fabricating accounts or data')
report,calls=run(login_status=401);assert report['status']=='refused' and calls==['/auth/login'];cases.append('failed private admin login stops immediately and reads no error body')
report={'status':'passed','cases':cases,'production_network_called':False,'real_credentials_read':False,'foreign_rows_read':False}
(folder/'local-boundary-checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({'status':'passed','checks':len(cases)}))
