"""Synthetic form contract fixture only: no SMTP, real account or password persistence."""
import json,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
root=Path(__file__).resolve().parent
events=[]
status={'email':'legacy@example.test','verified':False}
user={'name':'本机表单验证','username':'qa_synthetic_auth','role':'member'}
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,data,code=200):
        raw=json.dumps(data,ensure_ascii=False).encode()
        try:
            self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    def do_GET(self):
        if self.path=='/api/auth/config':return self.reply({'registration_enabled':False,'email_verification_enabled':True,'password_reset_enabled':True})
        if self.path=='/api/client/config':return self.reply({'version':1,'features':{'assistant':False}})
        if self.path=='/api/auth/me':return self.reply(user)
        if self.path=='/api/auth/email':return self.reply(status)
        if self.path=='/api/models':return self.reply({'status':'awaiting_weights','active':None,'available_crops':['Apple'],'items':[]})
        if self.path in ['/api/detections','/api/plots','/api/knowledge','/api/detection-tasks']:return self.reply([])
        return self.reply({'detail':'Synthetic fixture route absent'},404)
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0')))or b'{}')
        events.append({'method':'POST','path':self.path,'fields':sorted(body),'synthetic_only':True})
        (root/'events.json').write_text(json.dumps(events,indent=2),encoding='utf-8')
        if self.path=='/api/auth/login':return self.reply({'access_token':'REDACTED_SECRET','user':user})
        if self.path=='/api/auth/logout':return self.reply({'message':'ok'})
        time.sleep(3)
        if self.path=='/api/auth/password-reset-code':return self.reply({'message':'如果该邮箱已验证并关联可用账户，验证码会发送至该邮箱，请稍后查收。'})
        if self.path=='/api/auth/email/verification-code':return self.reply({'message':'如果该邮箱可用于绑定，验证码将发送至该邮箱，请稍后查收。'})
        if self.path=='/api/auth/password-reset':
            if body.get('code')!='123456':return self.reply({'detail':'验证码无效或已过期。'},400)
            return self.reply({'message':'Synthetic success; no password or credential was stored.'})
        if self.path=='/api/auth/email/verify':
            if body.get('code')!='123456':return self.reply({'detail':'当前密码或验证码无效。'},400)
            status.update(email=body['email'].strip().lower(),verified=True)
            return self.reply({**status,'message':'邮箱已验证并绑定。'})
        return self.reply({'detail':'Synthetic fixture route absent'},404)
ThreadingHTTPServer(('127.0.0.1',18941),Handler).serve_forever()
