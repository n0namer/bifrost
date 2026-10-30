"""Existing canary switch, with immutable proof gates and shared rollback primitives.

Importing this module has no runtime effects. Rehearsal uses its own port/app/Popen.
"""
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import os
import re
import socket
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
REPO = BASE / 'bifrost-sparse'
APP = BASE / 'bifrost-canary-ocx-data'
GLOBAL_CFG = Path.home() / '.codex' / 'config.toml'
OLD_EXE = BASE / 'bifrost-patched-final.exe'
SOURCE = 'd45ee450b4a9ab1d49bb045ae1b1a8224f5be131'
OLD_HASH = 'bdd67f733e7deb5ffdc7ed77b00026ae94f974b287efb4828087ad8862dbe8f6'
CONFIG_HASH = '80413641ddde13a13f289548358a55ed51238aa9aac9a229ed21f59063e034e1'
GLOBAL_HASH = 'dccf8a88f8217191035ef9859cef7d73f3b71869b1556c03eaf0b92b4857a3dc'
FASTHTTP = 'v1.77.1-0.20261028061327-329917ed143c'
FASTHTTP_SUM = 'h1:QyWiyavtnN3H27uPp835jpoGenXdz4sQGgvf2jC0zUc='
OLD_PID, OLD_CREATION, OLD_PARENT, PARENT_CREATION = 95820, 1793347588217, 57032, 1793347587376
OCX_PID, OCX_CREATION, CANARY_PORT = 11352, 1793366439812, 15185
HELPERS = ('probe_transient_http_r14_live.py', 'activate_transient_http_r14.py', 'rehearse_transient_http_r17.py')
OPENER = build_opener(ProxyHandler({}))


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def utc():
    return datetime.now(timezone.utc).isoformat()


def helper_hashes():
    return {name: digest(BASE / name) for name in HELPERS}


def validate_proof_records(sha, qa, acceptance, build, fixture, review, hashes):
    require(sha == SOURCE, 'SOURCE_SHA_MISMATCH')
    require(qa.get('source_sha') == sha and qa.get('verdict') == 'QA_ACCEPT', 'SOURCE_QA_REJECTED')
    require(acceptance.get('source_sha') == sha and acceptance.get('verdict') == 'QA_ACCEPT', 'SOURCE_ACCEPTANCE_MISMATCH')
    require(hashes['qa'] == acceptance.get('qa_receipt_sha256'), 'SOURCE_QA_HASH_MISMATCH')
    require(hashes['report'] == qa.get('report_sha256') == acceptance.get('qa_report_sha256'), 'SOURCE_REPORT_HASH_MISMATCH')
    require(build.get('sourceCommit') == sha and build.get('exitCode') == 0
            and all(build.get(k) is True for k in ('pass', 'sourceStable', 'toolchainVerified', 'vcsRevisionVerified', 'dependencyVerified')), 'BUILD_PROOF_MISMATCH')
    metadata = build.get('goBuildMetadata', '')
    require('go1.27.3' in metadata and 'vcs.revision=' + sha in metadata
            and re.search(r'github.com/valyala/fasthttp\s+' + re.escape(FASTHTTP) + r'\s+' + re.escape(FASTHTTP_SUM), metadata), 'BUILD_METADATA_MISMATCH')
    require(build.get('binarySha256') == hashes['binary'], 'BINARY_HASH_MISMATCH')
    cases = fixture.get('cases', [])
    require(fixture.get('passRequiredContract') is True and len(cases) == 29
            and len({c.get('case') for c in cases}) == 29
            and all(c.get('passRequiredContract') is True and c.get('physicalSends', 0) >= 1 for c in cases)
            and fixture.get('realProviderCalls') == 0 and fixture.get('clientRetries') == 0
            and fixture.get('sha256') == hashes['binary']
            and fixture.get('harnessSha256') == hashes['harness'], 'FIXTURE_PROOF_MISMATCH')
    require(review.get('verdict') == 'QA_ACCEPT' and review.get('source_sha') == sha
            and review.get('helperHashes') == hashes['helpers'] and review.get('testsPass') is True
            and review.get('testReceiptSha256') == hashes['tests']
            and review.get('reviewerThread') and review.get('reviewerThread') != '01a18e3f-67ea-7851-9f67-38068920775d', 'HELPER_QA_PROOF_MISMATCH')


def verify_proofs(args):
    require(args.sha == SOURCE, 'SOURCE_SHA_MISMATCH')
    require(digest(args.source_qa) == args.source_qa_sha256, 'SOURCE_QA_INPUT_HASH_MISMATCH')
    require(digest(args.helper_qa) == args.helper_qa_sha256, 'HELPER_QA_INPUT_HASH_MISMATCH')
    acceptance = read_json(BASE / 'evidence' / 'transient-http-r17-source-acceptance.json')
    build = read_json(BASE / 'evidence' / f'transient-http-r14-build-{args.sha[:12]}.json')
    binary = BASE / f'bifrost-transient-r14-{args.sha[:12]}.exe'
    hashes = {'qa': digest(args.source_qa), 'report': digest(acceptance['qa_report']),
              'binary': digest(binary), 'harness': digest(BASE / 'verify_transient_http_r14.py'),
              'helpers': helper_hashes(), 'tests': digest(BASE / 'evidence' / 'transient-http-r17-runtime-helper-tests.json')}
    validate_proof_records(args.sha, read_json(args.source_qa), acceptance, build,
                           read_json(args.fixture), read_json(args.helper_qa), hashes)
    head = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True, timeout=20).strip()
    dirty = subprocess.check_output(['git', '-C', str(REPO), 'diff', '--name-only', 'HEAD'], text=True, timeout=20).strip()
    require(head == args.sha and not dirty, 'SOURCE_NOT_FROZEN')
    return {'sourceCommit': args.sha, 'candidate': str(binary), 'candidateSha256': hashes['binary'],
            'sourceQaSha256': hashes['qa'], 'helperQaSha256': args.helper_qa_sha256,
            'fixture': str(Path(args.fixture).resolve()), 'fixtureSha256': digest(args.fixture),
            'helperHashes': hashes['helpers'], 'testReceiptSha256': hashes['tests']}


def ps(script):
    prefix = "$ErrorActionPreference='Stop';[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', prefix + script],
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    require(result.returncode == 0, 'POWERSHELL_CHECK_FAILED')
    return json.loads(result.stdout) if result.stdout.strip() else None


def identity(pid):
    return ps("$p=Get-CimInstance Win32_Process -Filter 'ProcessId=" + str(int(pid)) + "';if($p){"
              "[pscustomobject]@{pid=$p.ProcessId;parent=$p.ParentProcessId;path=$p.ExecutablePath;"
              "creationMs=[long][math]::Floor(($p.CreationDate.ToUniversalTime()-[datetime]'1970-01-01').TotalMilliseconds);"
              "command=$p.CommandLine}|ConvertTo-Json -Compress}")


def connections(port):
    return ps("$r=@(Get-NetTCPConnection -LocalPort " + str(int(port)) + " -ErrorAction SilentlyContinue);"
              "[pscustomobject]@{listeners=@($r|Where-Object State -eq 'Listen'|Select-Object OwningProcess,LocalAddress,LocalPort);"
              "established=@($r|Where-Object State -eq 'Established'|Select-Object OwningProcess,LocalAddress,RemotePort)}|ConvertTo-Json -Depth 4 -Compress")


def require_listener(rows, pid):
    require(bool(rows) and all(r['OwningProcess'] == pid and r['LocalAddress'] == '127.0.0.1' for r in rows), 'LISTENER_IDENTITY_MISMATCH')


def http(url, timeout=5):
    with OPENER.open(Request(url, headers={'Connection': 'close'}), timeout=timeout) as response:
        return response.status, response.read(2 * 1024 * 1024)


def ready():
    status, body = http('http://127.0.0.1:10100/readyz')
    result = json.loads(body)
    require(status == 200 and result.get('pid') == OCX_PID and result.get('status') == 'ready', 'OPENCODEX_NOT_READY_OR_CHANGED')
    return {'pid': result['pid'], 'status': result['status'], 'version': result.get('version')}


def validate_idle_metrics(raw, required_methods):
    rows = [line for line in raw.splitlines() if line.startswith('bifrost_active_requests{')]
    methods = set()
    for row in rows:
        match = re.search(r'method="([^"]+)"', row)
        if match:
            methods.add(match.group(1))
        value = float(row.rsplit(' ', 1)[1])
        require(math.isfinite(value) and value == 0, 'CANARY_NOT_IDLE')
    require(set(required_methods) <= methods, 'ACTIVE_REQUEST_SERIES_MISSING')
    return rows


def idle_sample(port, pid, required_methods):
    status, raw = http(f'http://127.0.0.1:{port}/metrics')
    require(status == 200, 'METRICS_NOT_READY')
    metrics = validate_idle_metrics(raw.decode('utf-8'), required_methods)
    conns = connections(port)
    require_listener(conns['listeners'], pid)
    require(not conns['established'], 'CANARY_CLIENT_CONNECTED')
    return {'at': utc(), 'metrics': metrics, **conns}


def process_matches(who, pid, creation, executable):
    return bool(who and who['pid'] == pid and who['creationMs'] == creation
                and Path(who['path']).resolve() == Path(executable).resolve())


def unchanged_static(baseline=None):
    require(digest(OLD_EXE) == OLD_HASH and digest(APP / 'config.json') == CONFIG_HASH
            and digest(GLOBAL_CFG) == GLOBAL_HASH, 'BASELINE_CONFIG_OR_BINARY_CHANGED')
    ocx = identity(OCX_PID)
    require(ocx and ocx['creationMs'] == OCX_CREATION, 'OPENCODEX_PROCESS_CHANGED')
    if baseline:
        require(ocx['path'] == baseline['opencodex']['path'], 'OPENCODEX_PATH_CHANGED')
    return ready()


def runtime_baseline():
    readiness = unchanged_static()
    old, parent, ocx = identity(OLD_PID), identity(OLD_PARENT), identity(OCX_PID)
    require(process_matches(old, OLD_PID, OLD_CREATION, OLD_EXE), 'OLD_PROCESS_IDENTITY_CHANGED')
    require(old['parent'] == OLD_PARENT and str(APP).lower() in old['command'].lower(), 'OLD_PROCESS_APP_OR_PARENT_CHANGED')
    require(parent and parent['creationMs'] == PARENT_CREATION and '/c' in parent['command'].lower()
            and str(OLD_EXE).lower() in parent['command'].lower(), 'OLD_LAUNCH_PARENT_CHANGED')
    require_listener(connections(CANARY_PORT)['listeners'], OLD_PID)
    return {'canary': old, 'parent': parent, 'opencodex': ocx, 'ready': readiness,
            'oldBinarySha256': OLD_HASH, 'configSha256': CONFIG_HASH, 'globalConfigSha256': GLOBAL_HASH}


def verify_baseline_unchanged(baseline):
    current = runtime_baseline()
    for name in ('canary', 'parent', 'opencodex'):
        for field in ('pid', 'creationMs', 'path'):
            require(current[name][field] == baseline[name][field], 'PRODUCTION_BASELINE_CHANGED')
    return current


def wait_free(port):
    until = time.monotonic() + 15
    while True:
        if not connections(port)['listeners']:
            return
        require(time.monotonic() < until, 'GATEWAY_PORT_NOT_RELEASED')
        time.sleep(.25)


def launch(executable, port, app, out, label):
    require(1 <= port <= 65535, 'PORT_OUT_OF_RANGE')
    with (out / f'{label}.log').open('xb') as log:
        return subprocess.Popen([str(executable), '-host', '127.0.0.1', '-port', str(port), '-app-dir', str(app)],
                                cwd=str(BASE), stdout=log, stderr=subprocess.STDOUT)


def healthy(process, executable, port, app):
    deadline = time.monotonic() + 25
    while True:
        require(process.poll() is None, 'GATEWAY_EXITED')
        try:
            status, _ = http(f'http://127.0.0.1:{port}/metrics', timeout=2)
            if status == 200:
                break
        except OSError:
            pass
        require(time.monotonic() < deadline, 'GATEWAY_START_TIMEOUT')
        time.sleep(.25)
    who = identity(process.pid)
    require(who and Path(who['path']).resolve() == executable.resolve()
            and str(app).lower() in who['command'].lower(), 'EXECUTABLE_IDENTITY_MISMATCH')
    require_listener(connections(port)['listeners'], process.pid)
    return who


def stop_owned(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def live_probe(port, sentinel, expected_probe_hash):
    require(digest(BASE / HELPERS[0]) == expected_probe_hash, 'PROBE_CHANGED')
    result = subprocess.run([sys.executable, str(BASE / HELPERS[0]), '--port', str(port), '--sentinel', sentinel],
                            capture_output=True, text=True, encoding='utf-8', timeout=95)
    data = json.loads(result.stdout)
    require(result.returncode == 0 and data.get('pass') is True and data.get('port') == port
            and data.get('clientRetries') == 0 and data.get('completedCount') == 1
            and data.get('terminalStatus') == 'completed', 'LIVE_SSE_PROBE_FAILED')
    return data


def restore_old(owned, port, app, backup, out, probe_hash, sentinel):
    """Both real rollback and rehearsal use this exact path; ownership survives errors."""
    stop_owned(owned.get('process'))
    wait_free(port)
    config = app / 'config.json'
    require(hashlib.sha256(backup).hexdigest() == CONFIG_HASH, 'BACKUP_DIGEST_MISMATCH')
    if not config.exists() or config.read_bytes() != backup:
        config.write_bytes(backup)
    require(digest(OLD_EXE) == OLD_HASH, 'ROLLBACK_BINARY_CHANGED')
    owned['process'] = launch(OLD_EXE, port, app, out, 'rollback')
    who = healthy(owned['process'], OLD_EXE, port, app)
    result = live_probe(port, sentinel, probe_hash)
    require(digest(config) == CONFIG_HASH, 'ROLLBACK_CONFIG_MISMATCH')
    return {'process': who, 'realSSE': result, 'oldBinarySha256': digest(OLD_EXE), 'configSha256': digest(config)}


def save_receipt(path, data, **fields):
    data.update(fields, updatedAt=utc())
    temporary = path.with_suffix('.json.writing')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    temporary.replace(path)
    print(json.dumps(fields, ensure_ascii=False), flush=True)


def output_directory(label):
    out = BASE / 'evidence' / (label + '-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir()
    return out


def common_arguments(parser):
    parser.add_argument('--sha', required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--source-qa', type=Path, required=True)
    parser.add_argument('--source-qa-sha256', required=True)
    parser.add_argument('--helper-qa', type=Path, required=True)
    parser.add_argument('--helper-qa-sha256', required=True)


def validate_rehearsal(receipt, proofs):
    require(receipt.get('passRehearsal') is True and receipt.get('status') == 'REHEARSAL_PASSED'
            and receipt.get('cleanupVerified') is True and receipt.get('productionUnchanged') is True,
            'REHEARSAL_NOT_ACCEPTED')
    for field in ('sourceCommit', 'candidateSha256', 'sourceQaSha256', 'helperQaSha256', 'fixtureSha256', 'helperHashes', 'testReceiptSha256'):
        require(receipt.get(field) == proofs[field], 'REHEARSAL_PROOF_MISMATCH_' + field)
    require(receipt.get('oldBinarySha256') == OLD_HASH and receipt.get('configSha256') == CONFIG_HASH
            and receipt.get('globalConfigSha256') == GLOBAL_HASH, 'REHEARSAL_BASELINE_MISMATCH')


def stop_original():
    quoted = str(OLD_EXE).replace("'", "''")
    return ps(f"$p=Get-Process -Id {OLD_PID} -ErrorAction Stop;"
              f"if([long][math]::Floor(($p.StartTime.ToUniversalTime()-[datetime]'1970-01-01').TotalMilliseconds)-ne {OLD_CREATION}"
              f" -or $p.Path -ne '{quoted}'){{throw 'OLD_PROCESS_CHANGED'}};"
              "$p.Kill();if(-not $p.WaitForExit(10000)){throw 'OLD_PROCESS_DID_NOT_EXIT'};"
              "[pscustomobject]@{originalExited=$p.HasExited}|ConvertTo-Json -Compress")


def main():
    parser = argparse.ArgumentParser()
    common_arguments(parser)
    parser.add_argument('--rehearsal', type=Path, required=True)
    parser.add_argument('--rehearsal-sha256', required=True)
    args = parser.parse_args()
    proofs = verify_proofs(args)
    require(digest(args.rehearsal) == args.rehearsal_sha256, 'REHEARSAL_INPUT_HASH_MISMATCH')
    validate_rehearsal(read_json(args.rehearsal), proofs)
    out = output_directory('transient-http-r17-activation')
    receipt = out / 'summary.json'
    data = {**proofs, 'status': 'PREFLIGHT', 'passActivation': False, 'globalRouteChanged': False,
            'launcherPid': os.getpid(), 'rehearsalSha256': args.rehearsal_sha256}
    owned, stopped, backup, baseline = {'process': None}, False, None, None
    save = lambda **kw: save_receipt(receipt, data, **kw)
    try:
        baseline = runtime_baseline()
        backup = (APP / 'config.json').read_bytes()
        require(hashlib.sha256(backup).hexdigest() == CONFIG_HASH, 'BACKUP_DIGEST_MISMATCH')
        (out / 'config-before.json').write_bytes(backup)
        samples = []
        for _ in range(5):
            samples.append(idle_sample(CANARY_PORT, OLD_PID, ('passthrough', 'passthrough_stream')))
            time.sleep(1)
        verify_baseline_unchanged(baseline)
        save(status='GATES_PASSED', before=baseline, drainSamples=samples, drainVerified=True,
             backupSha256=hashlib.sha256(backup).hexdigest())
        final_sample = idle_sample(CANARY_PORT, OLD_PID, ('passthrough', 'passthrough_stream'))
        stopped = True
        stop_original()
        save(status='OLD_STOPPED', finalDrainSample=final_sample)
        wait_free(CANARY_PORT)
        executable = Path(proofs['candidate'])
        require(digest(executable) == proofs['candidateSha256'], 'CANDIDATE_CHANGED')
        owned['process'] = launch(executable, CANARY_PORT, APP, out, 'candidate')
        who = healthy(owned['process'], executable, CANARY_PORT, APP)
        result = live_probe(CANARY_PORT, 'R17_ACTIVE_OK', proofs['helperHashes'][HELPERS[0]])
        readiness = unchanged_static(baseline)
        after_idle = idle_sample(CANARY_PORT, owned['process'].pid, ('passthrough_stream',))
        require(helper_hashes() == proofs['helperHashes'] and digest(executable) == proofs['candidateSha256'], 'POST_ACTIVATION_PROOF_CHANGED')
        save(status='ACTIVE_VERIFIED', passActivation=True, newProcess=who, realSSE=result,
             afterReady=readiness, afterIdle=after_idle, configUnchanged=True,
             globalConfigUnchanged=True, rollbackAvailable=str(OLD_EXE), rollbackRehearsed=True)
    except Exception as exc:
        data.update(status='ACTIVATION_FAILED', passActivation=False, error=str(exc))
        if stopped:
            try:
                original = identity(OLD_PID)
                if process_matches(original, OLD_PID, OLD_CREATION, OLD_EXE):
                    require_listener(connections(CANARY_PORT)['listeners'], OLD_PID)
                    rollback = {'process': original, 'realSSE': live_probe(CANARY_PORT, 'R17_OLD_UNCHANGED_OK', proofs['helperHashes'][HELPERS[0]])}
                else:
                    rollback = restore_old(owned, CANARY_PORT, APP, backup, out,
                                           proofs['helperHashes'][HELPERS[0]], 'R17_ROLLBACK_OK')
                unchanged_static(baseline)
                data.update(status='ROLLED_BACK_VERIFIED', rollback=rollback)
            except Exception as rollback_error:
                data.update(status='ROLLBACK_BLOCKED', rollbackError=str(rollback_error))
        else:
            data['runtimeUnchanged'] = True
        try:
            save(**{k: v for k, v in data.items() if k != 'updatedAt'})
        except Exception:
            data['receiptWriteFailed'] = True
            print(json.dumps({'status': data['status'], 'passActivation': False, 'receiptWriteFailed': True}), flush=True)
    print(json.dumps({'activationReceipt': str(receipt), 'status': data['status'], 'passActivation': data['passActivation']}), flush=True)
    if owned['process'] is not None and owned['process'].poll() is None:
        owned['process'].wait()  # Preserve the existing live-canary launcher lifecycle.
    return 0 if data['passActivation'] and not data.get('receiptWriteFailed') else 2


if __name__ == '__main__':
    raise SystemExit(main())
