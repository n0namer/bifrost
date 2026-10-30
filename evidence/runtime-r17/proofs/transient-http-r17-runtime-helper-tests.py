"""Local fixtures only: proof rejection, SSE physical sends, rollback ownership."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import activate_transient_http_r14 as rt
import probe_transient_http_r14_live as probe
import rehearse_transient_http_r17  # Import must be free of runtime entrypoint effects.

PHYSICAL = []


def sse(status='completed', sentinel='TEST_OK'):
    return ('data: ' + json.dumps({'type': 'response.output_text.delta', 'delta': sentinel}) + '\n\n'
            + 'data: ' + json.dumps({'type': 'response.completed', 'response': {'status': status}}) + '\n\n')


def records():
    hashes = {'qa': 'a' * 64, 'report': 'b' * 64, 'binary': 'c' * 64,
              'harness': 'd' * 64, 'tests': 'e' * 64,
              'helpers': {name: 'f' * 64 for name in rt.HELPERS}}
    qa = {'source_sha': rt.SOURCE, 'verdict': 'QA_ACCEPT', 'report_sha256': hashes['report']}
    acceptance = {'source_sha': rt.SOURCE, 'verdict': 'QA_ACCEPT',
                  'qa_receipt_sha256': hashes['qa'], 'qa_report_sha256': hashes['report']}
    build = {k: True for k in ('pass', 'sourceStable', 'toolchainVerified', 'vcsRevisionVerified', 'dependencyVerified')}
    build.update(sourceCommit=rt.SOURCE, exitCode=0, binarySha256=hashes['binary'],
                 goBuildMetadata=f'go1.27.3\n\tdep\tgithub.com/valyala/fasthttp\t{rt.FASTHTTP}\t{rt.FASTHTTP_SUM}\n\tbuild\tvcs.revision={rt.SOURCE}')
    fixture = {'passRequiredContract': True, 'cases': [
        {'case': str(n), 'physicalSends': 1, 'passRequiredContract': True} for n in range(29)],
        'realProviderCalls': 0, 'clientRetries': 0, 'sha256': hashes['binary'], 'harnessSha256': hashes['harness']}
    review = {'source_sha': rt.SOURCE, 'verdict': 'QA_ACCEPT', 'helperHashes': hashes['helpers'].copy(),
              'testsPass': True, 'testReceiptSha256': hashes['tests'], 'reviewerThread': 'independent-fixture-reviewer'}
    return [rt.SOURCE, qa, acceptance, build, fixture, review, hashes]


class HelperContracts(unittest.TestCase):
    def test_valid_proof_contract(self):
        rt.validate_proof_records(*records())

    def test_invalid_proofs_fail_before_runtime(self):
        mutations = [
            ('source SHA', lambda r: r.__setitem__(0, '0' * 40)),
            ('QA verdict', lambda r: r[1].update(verdict='QA_REPAIR_REQUIRED')),
            ('QA SHA', lambda r: r[1].update(source_sha='0' * 40)),
            ('acceptance verdict', lambda r: r[2].update(verdict='PENDING')),
            ('QA receipt hash', lambda r: r[6].update(qa='0' * 64)),
            ('report hash', lambda r: r[6].update(report='0' * 64)),
            ('build failure', lambda r: r[3].update(exitCode=1)),
            ('build SHA', lambda r: r[3].update(sourceCommit='0' * 40)),
            ('toolchain', lambda r: r[3].update(toolchainVerified=False)),
            ('fasthttp', lambda r: r[3].update(goBuildMetadata=r[3]['goBuildMetadata'].replace(rt.FASTHTTP, 'v1.74.0'))),
            ('binary', lambda r: r[6].update(binary='0' * 64)),
            ('failed fixture case', lambda r: r[4]['cases'][0].update(passRequiredContract=False)),
            ('duplicate fixture cases', lambda r: r[4]['cases'][0].update(case='1')),
            ('missing physical send', lambda r: r[4]['cases'][0].update(physicalSends=0)),
            ('fixture client retry', lambda r: r[4].update(clientRetries=1)),
            ('fixture real provider', lambda r: r[4].update(realProviderCalls=1)),
            ('harness hash', lambda r: r[6].update(harness='0' * 64)),
            ('helper QA', lambda r: r[5].update(verdict='QA_REPAIR_REQUIRED')),
            ('helper hash', lambda r: r[5]['helperHashes'].update({rt.HELPERS[0]: '0' * 64})),
            ('test receipt', lambda r: r[6].update(tests='0' * 64)),
            ('self review', lambda r: r[5].update(reviewerThread='01a18e3f-67ea-7851-9f67-38068920775d')),
        ]
        for name, mutate in mutations:
            with self.subTest(name=name), patch.object(rt, 'launch') as launch, patch.object(rt, 'stop_original') as stop:
                candidate = records()
                mutate(candidate)
                with self.assertRaises(RuntimeError):
                    rt.validate_proof_records(*candidate)
                launch.assert_not_called()
                stop.assert_not_called()

    def test_terminal_status_and_malformed_sse_fail(self):
        self.assertTrue(probe.validate_sse(200, sse(), 'TEST_OK')['pass'])
        for raw in (sse('failed'), sse('incomplete'), sse().rstrip('\n'), sse() + sse(),
                    sse().replace('TEST_OK', 'OTHER'), sse() + 'data: []\n\n',
                    sse() + 'data: {"type":"error"}\n\n', 'data: {"type":'):
            with self.subTest(raw=raw[:45]):
                self.assertFalse(probe.validate_sse(200, raw, 'TEST_OK')['pass'])
        self.assertFalse(probe.validate_sse(502, sse(), 'TEST_OK')['pass'])

    def test_sse_comments_multiline_tool_events_and_crlf(self):
        raw = ': keepalive\r\n\r\ndata: {"type":"response.output_item.added",\r\ndata: "item":{"type":"function_call"}}\r\n\r\n'
        raw += sse().replace('\n', '\r\n')
        self.assertTrue(probe.validate_sse(200, raw, 'TEST_OK')['pass'])

    def test_no_client_retry_physical_posts(self):
        state = {'calls': 0, 'status': 200, 'terminal': 'completed'}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                state['calls'] += 1
                self.rfile.read(int(self.headers['Content-Length']))
                body = sse(state['terminal']).encode()
                self.send_response(state['status'])
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for http_status, terminal, expected in [(200, 'completed', True), (200, 'failed', False), (429, 'completed', False)]:
                state.update(calls=0, status=http_status, terminal=terminal)
                if http_status == 429:
                    with self.assertRaises(HTTPError):
                        probe.probe(server.server_port, 'TEST_OK', 2)
                else:
                    self.assertEqual(probe.probe(server.server_port, 'TEST_OK', 2)['pass'], expected)
                self.assertEqual(state['calls'], 1)
                PHYSICAL.append({'status': http_status, 'terminal': terminal, 'physicalPOSTs': state['calls']})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

    def test_invalid_probe_arguments_make_no_request(self):
        with patch.object(probe, 'build_opener') as opener:
            for port, sentinel, timeout in [(0, 'OK', 2), (65536, 'OK', 2), (1, 'bad sentinel', 2), (1, 'OK', 0)]:
                with self.assertRaises(ValueError):
                    probe.probe(port, sentinel, timeout)
            opener.assert_not_called()

    def test_drain_requires_expected_series_and_finite_zero(self):
        valid = 'bifrost_active_requests{method="passthrough"} 0\nbifrost_active_requests{method="passthrough_stream"} 0'
        self.assertEqual(len(rt.validate_idle_metrics(valid, ('passthrough', 'passthrough_stream'))), 2)
        for raw in ('', valid.splitlines()[0], valid.replace(' 0', ' 1', 1), valid.replace(' 0', ' NaN', 1)):
            with self.assertRaises(RuntimeError):
                rt.validate_idle_metrics(raw, ('passthrough', 'passthrough_stream'))

    def test_rollback_ownership_survives_failed_health(self):
        candidate, rollback = object(), object()
        owned = {'process': candidate}
        backup = b'{"config_store":{"enabled":false}}'
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory)
            (app / 'config.json').write_bytes(backup)
            with patch.object(rt, 'CONFIG_HASH', hashlib.sha256(backup).hexdigest()), \
                    patch.object(rt, 'digest', return_value=rt.OLD_HASH), \
                    patch.object(rt, 'stop_owned') as stop, patch.object(rt, 'wait_free') as free, \
                    patch.object(rt, 'launch', return_value=rollback) as launch, \
                    patch.object(rt, 'healthy', side_effect=RuntimeError('injected readiness failure')):
                with self.assertRaisesRegex(RuntimeError, 'injected'):
                    rt.restore_old(owned, 23456, app, backup, app, 'f' * 64, 'TEST_OK')
                self.assertIs(owned['process'], rollback)
                stop.assert_called_once_with(candidate)
                free.assert_called_once_with(23456)
                self.assertEqual(launch.call_args.args[1:3], (23456, app))

    def test_rehearsal_receipt_binds_same_helpers_and_binary(self):
        proof = {'sourceCommit': rt.SOURCE, 'candidateSha256': 'a' * 64, 'sourceQaSha256': 'b' * 64,
                 'helperQaSha256': 'c' * 64, 'fixtureSha256': 'd' * 64,
                 'helperHashes': {name: 'e' * 64 for name in rt.HELPERS}, 'testReceiptSha256': 'f' * 64}
        result = dict(proof, passRehearsal=True, status='REHEARSAL_PASSED', cleanupVerified=True,
                      productionUnchanged=True, oldBinarySha256=rt.OLD_HASH,
                      configSha256=rt.CONFIG_HASH, globalConfigSha256=rt.GLOBAL_HASH)
        rt.validate_rehearsal(result, proof)
        for field, bad in [('cleanupVerified', False), ('productionUnchanged', False),
                           ('candidateSha256', '0' * 64), ('helperHashes', {})]:
            with self.assertRaises(RuntimeError):
                rt.validate_rehearsal(dict(result, **{field: bad}), proof)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--read-only', action='store_true')
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(HelperContracts))
    report = {'sourceSha': rt.SOURCE, 'testsPass': result.wasSuccessful(), 'testsRun': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors),
              'physicalProbeCases': PHYSICAL, 'realProviderCalls': 0, 'bifrostProcessesStarted': 0,
              'helperHashes': rt.helper_hashes(), 'testCodeSha256': rt.digest(Path(__file__))}
    if not args.read_only:
        (BASE / 'evidence' / 'transient-http-r17-runtime-helper-tests.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
