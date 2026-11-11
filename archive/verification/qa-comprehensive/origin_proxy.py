"""Loopback-only QA transport to the deployed origin via an authenticated SSH tunnel."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import ssl

DOMAIN = 'flowly-ai.top'
CONTEXT = ssl.create_default_context()
CONTEXT.set_alpn_protocols(['http/1.1'])


class Connection(http.client.HTTPSConnection):
    def connect(self):
        raw = socket.create_connection(('127.0.0.1', 18843), timeout=30)
        self.sock = CONTEXT.wrap_socket(raw, server_hostname=DOMAIN)


class Proxy(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass  # Never log request bodies, credentials or Authorization headers.

    def forward(self):
        if not self.path.startswith('/agriscan/') and self.path != '/agriscan':
            self.send_error(404)
            return
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        headers = {key: value for key, value in self.headers.items()
                   if key.lower() not in {'host', 'connection', 'accept-encoding'}}
        headers['Host'] = DOMAIN
        headers['Connection'] = 'close'
        try:
            upstream = Connection(DOMAIN, timeout=180)
            upstream.request(self.command, self.path, body=body or None, headers=headers)
            response = upstream.getresponse()
            payload = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() in {'content-length', 'transfer-encoding', 'connection'}:
                    continue
                if key.lower() == 'location' and value.startswith('https://' + DOMAIN):
                    value = value.replace('https://' + DOMAIN, 'http://127.0.0.1:5180', 1)
                self.send_header(key, value)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Connection', 'close')
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(payload)
            upstream.close()
        except (OSError, http.client.HTTPException) as error:
            self.send_error(502, type(error).__name__)

    do_GET = do_HEAD = do_POST = do_PATCH = do_DELETE = do_OPTIONS = forward


print('QA origin transport on http://127.0.0.1:5180/agriscan/ (TLS verification enabled)', flush=True)
ThreadingHTTPServer(('127.0.0.1', 5180), Proxy).serve_forever()
