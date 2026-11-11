from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def reply(self, value):
        payload=json.dumps(value).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
    def do_GET(self):
        if self.path=='/api/auth/me': self.reply({'name':'QA temporary member','username':'qa_member','role':'member'})
        else: self.send_error(404)
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length','0')))
        if self.path=='/api/auth/login': self.reply({'access_token':'REDACTED_SECRET','user':{'name':'QA temporary member','username':'qa_member','role':'member'}})
        else: self.send_error(404)
ThreadingHTTPServer(('127.0.0.1',18002),Handler).serve_forever()
