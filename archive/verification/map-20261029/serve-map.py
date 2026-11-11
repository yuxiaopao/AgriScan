from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse,parse_qs
import time
import urllib.request

root=Path(__file__).resolve().parent
fixture=root/'osm-fixture.png'
if not fixture.exists():
    request=urllib.request.Request('https://tile.openstreetmap.org/4/12/6.png',headers={'User-Agent':'AgriScan QA (+https://agriscan.ming-ai.top/agriscan/)'})
    fixture.write_bytes(urllib.request.urlopen(request,timeout=20).read())
mode='ready'
counter=0
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(root/'harness-build'),**kwargs)
    def do_GET(self):
        global mode,counter
        parsed=urlparse(self.path)
        if parsed.path=='/mode':
            mode=parse_qs(parsed.query).get('value',['ready'])[0];counter=0
            self.send_response(200);self.end_headers();self.wfile.write(mode.encode());return
        if parsed.path.startswith('/tiles/'):
            counter+=1;number=counter;requested_mode=mode
            if requested_mode=='slow':time.sleep(40)
            if requested_mode=='fail' or requested_mode=='partial' and number%2==0:
                self.send_response(503);self.send_header('Cache-Control','no-store');self.end_headers();return
            body=fixture.read_bytes();self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('Cache-Control','no-store');self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
            return
        super().do_GET()
    def log_message(self,*args):pass
ThreadingHTTPServer(('127.0.0.1',6186),Handler).serve_forever()
