import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime'))
from proxy import make_server


class Echo(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Length', '2')
        self.end_headers()
        self.wfile.write(b'ok')

    def do_PUT(self):
        size = int(self.headers['Content-Length'])
        data = self.rfile.read(size)
        self.send_response(200)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = 'ab' * 32
        cls.upstream = ThreadingHTTPServer(('127.0.0.1', 0), Echo)
        cls.proxy = make_server(cls.token, port=0, upstream=cls.upstream.server_port, bind='127.0.0.1')
        for server in (cls.upstream, cls.proxy):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.host = '127.0.0.1:' + str(cls.proxy.server_port)

    @classmethod
    def tearDownClass(cls):
        for server in (cls.proxy, cls.upstream):
            server.shutdown()
            server.server_close()

    def request(self, path='/', method='GET', auth=False, body=None, extra=None):
        headers = {'Host': self.host}
        if auth:
            headers['Cookie'] = 'wings_session=' + self.token
        headers.update(extra or {})
        c = http.client.HTTPConnection('127.0.0.1', self.proxy.server_port, timeout=5)
        c.request(method, path, body, headers)
        r = c.getresponse()
        result = r.status, dict(r.getheaders()), r.read()
        c.close()
        return result

    def test_unauthenticated_api_is_denied(self):
        self.assertEqual(self.request('/api/runs')[0], 401)

    def test_session_redirect_and_cookie(self):
        status, headers, _ = self.request('/desktop/session?token=' + self.token)
        self.assertEqual(status, 303)
        self.assertEqual(headers['Location'], '/run.html?new=1')
        self.assertIn('HttpOnly; SameSite=Strict', headers['Set-Cookie'])
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')

    def test_wrong_token_denied(self):
        self.assertEqual(self.request('/desktop/session?token=wrong')[0], 403)

    def test_host_rebinding_denied(self):
        self.assertEqual(self.request(auth=True, extra={'Host': 'evil.example'})[0], 403)

    def test_cross_origin_write_denied(self):
        self.assertEqual(self.request(method='PUT', auth=True, body=b'a',
            extra={'Origin': 'https://evil.example'})[0], 403)

    def test_missing_origin_write_denied(self):
        self.assertEqual(self.request(method='PUT', auth=True, body=b'a')[0], 403)

    def test_multiblock_upload_and_response_preserved(self):
        data = bytes(range(256)) * 12000
        status, _, body = self.request('/api/files', method='PUT', auth=True, body=data,
            extra={'Origin': 'http://' + self.host})
        self.assertEqual(status, 200)
        self.assertEqual(data, body)

    def test_health_is_minimal(self):
        status, _, body = self.request('/desktop/health')
        self.assertEqual(status, 200)
        self.assertEqual(body, b'{"service": "wings-desktop", "ready": true}')

    def test_authenticated_read(self):
        self.assertEqual(self.request('/api/runs', auth=True)[2], b'ok')

    def test_bad_startup_token(self):
        with self.assertRaises(ValueError):
            make_server('guessable', port=0)


if __name__ == '__main__':
    unittest.main()
