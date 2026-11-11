"""Exercise trial edge routing locally, without ACME or public listeners."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.flags.optimize:
        raise RuntimeError('Run smoke checks with Python assertions enabled')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--caddy', required=True)
    args = parser.parse_args()

    class Backend(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers.get('Forwarded') is None
            assert self.headers.get('X-Real-IP') is None
            assert self.headers.get('X-Forwarded-For') is None
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'backend reached')

        def log_message(self, *args):
            pass

    backend = ThreadingHTTPServer(('127.0.0.1', 0), Backend)
    thread = threading.Thread(target=backend.serve_forever, daemon=True)
    thread.start()
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with tempfile.TemporaryDirectory(prefix='trial-edge-smoke-') as tmp:
            env = {**os.environ, 'TRIAL_DOMAIN': 'trial.invalid',
                   'TRIAL_CLIENT_IP': '127.0.0.1', 'XDG_DATA_HOME': tmp,
                   'XDG_CONFIG_HOME': tmp}
            subprocess.run([args.caddy, 'adapt', '--config', str(ROOT / 'deploy/trial-https/Caddyfile'),
                            '--adapter', 'caddyfile'], env=env, check=True,
                           stdout=subprocess.DEVNULL)
            source = (ROOT / 'deploy/trial-https/Caddyfile').read_text()
            source = source.replace('/srv/backup-info',str(ROOT / 'deploy/backup-info'))
            source = source.replace('http://{$TRIAL_DOMAIN}:8080 {\n\trespond 404\n}', '')
            for allowed, expected in [('127.0.0.1', 200), ('192.0.2.1', 403)]:
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0))
                    port = sock.getsockname()[1]
                # Exercise the same directives with local HTTP instead of ACME.
                config = source.replace('{$TRIAL_DOMAIN} {', f'http://127.0.0.1:{port} {{')
                config = config.replace('api:8000', f'127.0.0.1:{backend.server_port}')
                path = Path(tmp) / 'Caddyfile'
                path.write_text(config)
                env['TRIAL_CLIENT_IP'] = allowed
                with (Path(tmp) / 'caddy.log').open('w') as log:
                    process = subprocess.Popen([args.caddy, 'run', '--config', str(path),
                                                '--adapter', 'caddyfile'], env=env,
                                               stdout=log, stderr=log)
                    try:
                        def request(route, method='GET'):
                            req = urllib.request.Request(f'http://127.0.0.1:{port}{route}',
                                method=method,
                                headers={'Forwarded': 'for=192.0.2.1', 'X-Real-IP': '192.0.2.1',
                                         'X-Forwarded-For': '192.0.2.1'})
                            try:
                                return client.open(req, timeout=2)
                            except urllib.error.HTTPError as exc:
                                return exc
                        deadline = time.monotonic() + 10
                        while True:
                            if process.poll() is not None:
                                raise RuntimeError('Caddy exited during startup')
                            try:
                                response = request('/ready')
                                break
                            except urllib.error.URLError:
                                if time.monotonic() >= deadline:
                                    raise RuntimeError('Caddy did not become ready')
                                time.sleep(.1)
                        with response:
                            assert response.status == expected, (allowed, response.status, response.read())
                            if expected == 200:
                                assert response.read() == b'backend reached'
                                assert response.headers['Cache-Control'] == 'no-store'
                        for route in ('/docs', '/openapi.json', '/v1/traces', '/private-ops/test', '/unknown'):
                            with request(route) as response:
                                assert response.status == (404 if expected == 200 else 403)
                        with request('/api/v1/styles') as response:
                            assert response.status == expected
                        for route in ('/backup-info','/backup-privacy'):
                            with request(route) as response:
                                body=response.read()
                                assert response.status==200 and b'NextPhase Backups' in body
                                assert response.headers.get_content_type()=='text/html'
                                assert "default-src 'none'" in response.headers['Content-Security-Policy']
                                assert 'Set-Cookie' not in response.headers
                                assert b'backend reached' not in body and b'<script' not in body
                            with request(route,'HEAD') as response:
                                assert response.status==200 and response.read()==b''
                            with request(route,'POST') as response:
                                assert response.status==(404 if expected==200 else 403)
                        for route in ('/index.html','/privacy.html','/backup-info/','/backup-info/private'):
                            with request(route) as response:
                                assert response.status==(404 if expected==200 else 403),(route,response.status)
                        # Caddy can normalize these to the API route. A denied
                        # socket peer must still get 403; a public-page prefix
                        # cannot carry its access exemption through traversal.
                        for route in ('/backup-info/../api/v1/jobs','/backup-info%2f..%2fapi%2fv1%2fjobs'):
                            with request(route) as response:
                                assert response.status in ((200,404) if expected==200 else (403,)),(route,response.status)
                                if response.status==200:assert response.read()==b'backend reached'
                    finally:
                        process.terminate()
                        process.wait(timeout=10)
        print('Passed: config adaptation, allowed API, denied peer, forged headers, private routes, public static information only.')
    finally:
        backend.shutdown()
        backend.server_close()


if __name__ == '__main__':
    main()
