from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime,timezone
import json,time,uuid

root=Path(__file__).resolve().parent
workspace=root.parent.parent
tasks={};records={}
def now():return datetime.now(timezone.utc).isoformat()
def update():
    for task in tasks.values():
        if task['status'] in ['queued','processing']:
            age=time.monotonic()-task['_start']
            task['status']='processing' if age<20 else 'completed'
            if task['status']=='completed' and not task['result_ids']:
                record_id='fixture-'+task['id'];task['result_ids']=[record_id]
                records[record_id]={'id':record_id,'name':task['filename'],'crop':'苹果','plot_id':None,'plot_name':'','status':'attention','result':'苹果黑星病','confidence':.84,'created_at':now(),'image_url':'/api/uploads/fixture.png','is_demo':False,'note':task.get('note',''),'candidates':[],'boxes':[],'prediction_model':{'name':'本机测试检测器','task':'detect','onnx_sha256':'a'*64}}
def public(task):return {k:v for k,v in task.items() if not k.startswith('_')}
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(root/'frontend/dist'),**kwargs)
    def reply(self,data,status=200):
        raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        path=urlparse(self.path).path;path=path[len('/agriscan'):] if path.startswith('/agriscan/api') else path;update()
        if path in ['/','/agriscan/workspace/']:
            source=(root/'frontend/dist/index.html').read_text(encoding='utf-8').replace('<head>','<head><script>sessionStorage.setItem("agriscan-token","local-task-fixture");localStorage.setItem("agriscan-crop-theme","番茄");if(!location.hash)location.hash="detect";</script>')
            source=source.replace('<div id="root">','<button id="qa-file" style="position:fixed;right:12px;bottom:12px;z-index:10000;background:white;padding:12px;border:1px solid" onclick="fetch(\'/agriscan/api/uploads/fixture.png\').then(r=>r.blob()).then(blob=>{const input=document.querySelector(\'input[type=file]\');const transfer=new DataTransfer();transfer.items.add(new File([blob],\'qa-navigation.png\',{type:\'image/png\'}));input.files=transfer.files;input.dispatchEvent(new Event(\'change\',{bubbles:true}))})">选择固定测试图片</button><div id="root">')
            body=source.encode();self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(body);return
        if path=='/api/auth/me':return self.reply({'username':'local-task-qa','name':'本机任务验收','role':'member'})
        if path=='/api/health':return self.reply({'status':'ok','database':'ok','redis':'ok','mode':'fixture','model':'ready'})
        if path=='/api/client/config':return self.reply({'brand':{'app_name':'禾观 本机任务验收','tagline':'固定测试服务','announcement':'独立本机测试，无生产数据'},'features':{'image_detection':True,'video_detection':True,'live_detection':True,'assistant':False,'knowledge':True,'plots':True},'limits':{'image_max_mb':10,'video_max_mb':50,'video_max_seconds':60,'video_max_frames':8,'frame_interval_ms':750},'version':1})
        if path=='/api/models':return self.reply({'status':'ready','message':'本机测试','available_crops':['苹果','番茄'],'supported_crops':['苹果','番茄'],'items':[],'active':{'name':'本机测试检测器','task':'detect','class_count':2,'test_top1':None,'test_macro_f1':None,'scope':'fixture'}})
        if path=='/api/dashboard':return self.reply({'stats':{'total':len(records),'healthy':0,'attention':len(records),'pending':0},'trend':[],'distribution':[],'recent':list(records.values())})
        if path=='/api/detection-tasks':return self.reply([public(task) for task in tasks.values()])
        if path.startswith('/api/detection-tasks/'):
            task=tasks.get(path.split('/')[-1]);return self.reply(public(task)) if task else self.reply({},404)
        if path=='/api/detections':return self.reply(list(records.values()))
        if path.startswith('/api/detections/'):
            record=records.get(path.split('/')[-1]);return self.reply(record) if record else self.reply({},404)
        if path in ['/api/plots','/api/knowledge','/api/assistant/conversations']:return self.reply([])
        if path=='/api/uploads/fixture.png':
            data=(workspace/'.runtime/map-20261029/osm-fixture.png').read_bytes();self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data);return
        if self.path.startswith('/agriscan/workspace/'):self.path=self.path[len('/agriscan/workspace'):]
        super().do_GET()
    def do_POST(self):
        path=urlparse(self.path).path;path=path[len('/agriscan'):] if path.startswith('/agriscan/api') else path
        if path=='/api/detection-tasks':
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))));task={**body,'id':uuid.uuid4().hex,'status':'awaiting_upload','received_bytes':0,'total_bytes':body['size_bytes'],'created_at':now(),'updated_at':now(),'error':None,'result_ids':[]};tasks[task['id']]=task;return self.reply(public(task),201)
        if path=='/api/auth/logout':return self.reply({})
        return self.reply({},404)
    def do_PUT(self):
        task=tasks.get(urlparse(self.path).path.split('/')[-2])
        if not task:return self.reply({},404)
        data=self.rfile.read(int(self.headers.get('Content-Length','0')));task.update(status='queued',received_bytes=len(data),_start=time.monotonic());return self.reply(public(task),202)
    def do_DELETE(self):
        task=tasks.get(urlparse(self.path).path.split('/')[-1]);update()
        if not task:return self.reply({},404)
        if task['status']!='completed':task['status']='cancelled'
        return self.reply(public(task))
    def log_message(self,*args):pass
ThreadingHTTPServer(('127.0.0.1',6190),Handler).serve_forever()
