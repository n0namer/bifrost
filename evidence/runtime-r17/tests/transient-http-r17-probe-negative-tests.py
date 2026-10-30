"""Regression proofs for the probe: no redirects, strict text, named SSE errors."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import probe_transient_http_r14_live as probe

PHYSICAL = []


def sse(delta='TEST_OK'):
    return ('data: ' + json.dumps({'type': 'response.output_text.delta', 'delta': delta}) + '\n\n'
            + 'data: {"type":"response.completed","response":{"status":"completed"}}\n\n')


class ProbeNegatives(unittest.TestCase):
    def test_valid_text_control(self):
        self.assertTrue(probe.validate_sse(200, sse(), 'TEST_OK')['pass'])

    def test_non_string_delta_cannot_prove_text(self):
        for delta in ({'value': 'TEST_OK'}, ['TEST_OK'], None, 42):
            with self.subTest(delta=delta):
                self.assertFalse(probe.validate_sse(200, sse(delta), 'TEST_OK')['pass'])

    def test_named_error_event_rejects_completed(self):
        for name in ('error', 'response.failed', 'response.incomplete', 'response.cancelled'):
            with self.subTest(event=name):
                raw = sse() + 'event: ' + name + '\ndata: {"error":{"message":"late failure"}}\n\n'
                self.assertFalse(probe.validate_sse(200, raw, 'TEST_OK')['pass'])

    def test_redirect_never_reaches_other_endpoint(self):
        state = {'posts': 0, 'target': 0, 'status': 302}

        class Target(BaseHTTPRequestHandler):
            def do_GET(self):
                state['target'] += 1
                body = sse().encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', '0')))
                self.do_GET()

            def log_message(self, *args):
                pass

        target = ThreadingHTTPServer(('127.0.0.1', 0), Target)

        class Source(BaseHTTPRequestHandler):
            def do_POST(self):
                state['posts'] += 1
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(state['status'])
                self.send_header('Location', f'http://127.0.0.1:{target.server_port}/redirected')
                self.send_header('Content-Length', '0')
                self.end_headers()

            def log_message(self, *args):
                pass

        source = ThreadingHTTPServer(('127.0.0.1', 0), Source)
        servers = (source, target)
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
        for thread in threads:
            thread.start()
        try:
            for status in (301, 302, 303, 307, 308):
                with self.subTest(status=status):
                    state.update(posts=0, target=0, status=status)
                    accepted, error = False, None
                    try:
                        accepted = probe.probe(source.server_port, 'TEST_OK', 2)['pass']
                    except HTTPError as exc:
                        error = exc.code
                    PHYSICAL.append({'status': status, 'sourcePOSTs': state['posts'],
                                     'redirectTargetRequests': state['target'], 'accepted': accepted,
                                     'httpError': error})
                    self.assertEqual(state['posts'], 1)
                    self.assertEqual(state['target'], 0)
                    self.assertFalse(accepted)
                    self.assertEqual(error, status)
        finally:
            for server in servers:
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join(timeout=3)
                self.assertFalse(thread.is_alive())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--receipt', required=True, type=Path)
    args = parser.parse_args()
    if args.receipt.exists():
        raise RuntimeError('RECEIPT_EXISTS_RECONCILE')
    before = hashlib.sha256((BASE / 'probe_transient_http_r14_live.py').read_bytes()).hexdigest()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProbeNegatives))
    after = hashlib.sha256((BASE / 'probe_transient_http_r14_live.py').read_bytes()).hexdigest()
    report = {'testsPass': result.wasSuccessful(), 'testsRun': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'physicalCases': PHYSICAL,
              'probeSha256': before, 'probeUnchanged': before == after, 'realProviderCalls': 0,
              'bifrostProcessesStarted': 0, 'testCodeSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with args.receipt.open('x', encoding='utf-8') as output:
        output.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if result.wasSuccessful() and before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
