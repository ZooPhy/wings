"""Loopback-published gateway for the unmodified localhost WINGS runner.

The daemon port is only published on host 127.0.0.1. Authentication protects
localhost APIs from other browser origins. No patient/sample data are logged.
"""
import hmac
import http.client
import json
import re
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HOP = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
       'te', 'trailer', 'transfer-encoding', 'upgrade'}


def make_server(token, port=8766, upstream=8765, bind='0.0.0.0'):
    if not re.fullmatch(r'[a-f0-9]{64}', token):
        raise ValueError('Session token must contain 32 random bytes in hex')

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def log_message(self, *_):
            pass  # URLs may contain a session token or sample identifiers.

        def reply(self, status, body=b'', headers=()):
            self.send_response(status)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def dispatch(self):
            host = self.headers.get('Host', '')
            if not re.fullmatch(r'127\.0\.0\.1:\d{1,5}', host):
                return self.reply(403, b'Localhost access only')
            url = urlsplit(self.path)
            if url.scheme or url.netloc or not self.path.startswith('/'):
                return self.reply(400)
            if self.command == 'GET' and url.path == '/desktop/health':
                try:
                    connection = http.client.HTTPConnection('127.0.0.1', upstream, timeout=2)
                    connection.request('GET', '/api/health')
                    ready = connection.getresponse().status == 200
                    connection.close()
                except OSError:
                    ready = False
                return self.reply(200 if ready else 503, json.dumps({
                    'service': 'wings-desktop', 'ready': ready}).encode(),
                    [('Content-Type', 'application/json')])
            if self.command == 'GET' and url.path == '/desktop/session':
                supplied = parse_qs(url.query).get('token', [''])[0]
                if not hmac.compare_digest(supplied, token):
                    return self.reply(403, b'Open WINGS from the desktop app')
                return self.reply(303, headers=[('Location', '/run.html?new=1'),
                    ('Set-Cookie', 'wings_session=' + token + '; HttpOnly; SameSite=Strict; Path=/')])
            cookies = SimpleCookie()
            try:
                cookies.load(self.headers.get('Cookie', ''))
                supplied = cookies['wings_session'].value if 'wings_session' in cookies else ''
            except Exception:
                supplied = ''
            if not hmac.compare_digest(supplied, token):
                return self.reply(401, b'Open WINGS from the desktop app to start a session')
            if self.command not in ('GET', 'HEAD'):
                if self.headers.get('Origin') != 'http://' + host:
                    return self.reply(403, b'Invalid request origin')
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) > 1:
                return self.reply(400, b'Use a single Content-Length')
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 0:
                    raise ValueError()
            except ValueError:
                return self.reply(400)
            connection = http.client.HTTPConnection('127.0.0.1', upstream, timeout=300)
            try:
                connection.putrequest(self.command, self.path, skip_host=True, skip_accept_encoding=True)
                for key, value in self.headers.items():
                    if key.lower() not in HOP | {'cookie'}:
                        connection.putheader(key, value)
                connection.putheader('Connection', 'close')
                connection.endheaders()
                remaining = length
                while remaining:
                    block = self.rfile.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ConnectionError('Truncated request body')
                    connection.send(block)
                    remaining -= len(block)
                response = connection.getresponse()
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in HOP | {'server', 'date', 'set-cookie'}:
                        self.send_header(key, value)
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                if self.command != 'HEAD':
                    while block := response.read(1024 * 1024):
                        self.wfile.write(block)
            except (OSError, http.client.HTTPException):
                self.close_connection = True
            finally:
                connection.close()

        do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = do_OPTIONS = dispatch

    return ThreadingHTTPServer((bind, port), Handler)
