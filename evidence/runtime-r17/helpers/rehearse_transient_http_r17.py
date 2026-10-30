"""Finite isolated candidate E2E and the same rollback routine used by activation."""
import argparse
import hashlib
import json
import socket
import tempfile
import shutil
from pathlib import Path
import activate_transient_http_r14 as rt


def main():
    parser = argparse.ArgumentParser()
    rt.common_arguments(parser)
    args = parser.parse_args()
    proofs = rt.verify_proofs(args)
    baseline = rt.runtime_baseline()
    backup = (rt.APP / 'config.json').read_bytes()
    rt.require(hashlib.sha256(backup).hexdigest() == rt.CONFIG_HASH, 'BACKUP_DIGEST_MISMATCH')
    config = json.loads(backup)
    rt.require(config.get('config_store', {}).get('enabled') is False
               and config.get('logs_store', {}).get('enabled') is False, 'SHARED_STORES_NOT_DISABLED')
    out = rt.output_directory('transient-http-r17-rehearsal')
    receipt = out / 'summary.json'
    data = {**proofs, 'status': 'PREFLIGHT', 'passRehearsal': False, 'before': baseline,
            'oldBinarySha256': rt.OLD_HASH, 'configSha256': rt.CONFIG_HASH,
            'globalConfigSha256': rt.GLOBAL_HASH, 'globalRouteChanged': False}
    owned, port = {'process': None}, None
    app = Path(tempfile.mkdtemp(prefix='bifrost-r17-rehearsal-'))
    try:
        (app / 'config.json').write_bytes(backup)
        with socket.socket() as selected:
            selected.bind(('127.0.0.1', 0))
            port = selected.getsockname()[1]
        rt.require(port != rt.CANARY_PORT, 'ISOLATED_PORT_REQUIRED')
        data.update(port=port, privateAppDir=str(app))
        rt.require(not rt.connections(port)['listeners'], 'ISOLATED_PORT_TAKEN')
        executable = Path(proofs['candidate'])
        owned['process'] = rt.launch(executable, port, app, out, 'candidate')
        data['candidateProcess'] = rt.healthy(owned['process'], executable, port, app)
        data['candidateSSE'] = rt.live_probe(port, 'R17_REHEARSAL_CANDIDATE_OK', proofs['helperHashes'][rt.HELPERS[0]])
        data['injectedFailure'] = 'CONTROLLED_CANDIDATE_STOP_AFTER_SUCCESSFUL_SSE'
        data['rollback'] = rt.restore_old(owned, port, app, backup, out,
                                          proofs['helperHashes'][rt.HELPERS[0]], 'R17_REHEARSAL_OLD_OK')
        rt.require(rt.digest(executable) == proofs['candidateSha256']
                   and rt.helper_hashes() == proofs['helperHashes'], 'REHEARSAL_PROOF_CHANGED')
        data['runtimeChecksPassed'] = True
    except Exception as exc:
        data['error'] = str(exc)
    finally:
        try:
            rt.stop_owned(owned['process'])
            if port is not None:
                rt.wait_free(port)
            shutil.rmtree(app)
            data['cleanupVerified'] = True
            data['privateDirectoryRemoved'] = True
        except Exception as exc:
            data['cleanupVerified'] = False
            data['cleanupError'] = str(exc)
        try:
            data['after'] = rt.verify_baseline_unchanged(baseline)
            data['productionUnchanged'] = True
        except Exception as exc:
            data['productionUnchanged'] = False
            data['productionCheckError'] = str(exc)
    passed = bool(data.get('runtimeChecksPassed') and data.get('cleanupVerified') and data.get('productionUnchanged'))
    rt.save_receipt(receipt, data, status='REHEARSAL_PASSED' if passed else 'REHEARSAL_FAILED', passRehearsal=passed)
    print(json.dumps({'rehearsalReceipt': str(receipt), 'passRehearsal': passed}), flush=True)
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
