"""Finite MVP delivery check of the already accepted executable; coordinator owns execution."""
from pathlib import Path
import hashlib,json,shutil,socket,subprocess,sys,tempfile
BASE=Path(__file__).resolve().parents[1];E=BASE/'evidence'
sys.path.insert(0,str(BASE))
import activate_transient_http_r14 as rt
SOURCE='d45ee450b4a9ab1d49bb045ae1b1a8224f5be131'
BINARY_SHA='e69e9a679b19070ced7783b28ae63174adca50aaa99537a5a475abdb10b6db23'
SOURCE_QA_SHA='d8f77132b584bcefced43dda71812d9bb052fa24fe9fd017ca52a56f21163a51'
PROBE_SHA='7f7c46dbb8553a8fc4c467387e3cc33c606db97760607acad2099bbc049e58c7'
def accepted_binary():
 binary=BASE/'bifrost-transient-r14-d45ee450b4a9.exe'
 qa=E/'transient-http-r17-independent-qa-d45ee450b4a9.json'
 build=rt.read_json(E/'transient-http-r14-build-d45ee450b4a9.json')
 fixture_path=E/'transient-http-r14-binary-20261030-214419'/'summary.json';fixture=rt.read_json(fixture_path)
 rt.require(rt.digest(qa)==SOURCE_QA_SHA and rt.read_json(qa)['verdict']=='QA_ACCEPT' and rt.read_json(qa)['source_sha']==SOURCE,'SOURCE_QA_MISMATCH')
 rt.require(rt.digest(binary)==BINARY_SHA and build['pass'] and build['sourceCommit']==SOURCE and build['binarySha256']==BINARY_SHA and build['vcsRevisionVerified'] and build['dependencyVerified'],'BUILD_MISMATCH')
 rt.require(fixture['passRequiredContract'] and len(fixture['cases'])==29 and all(c['passRequiredContract'] for c in fixture['cases']) and fixture['sha256']==BINARY_SHA,'FIXTURE_MISMATCH')
 rt.require(rt.digest(BASE/'probe_transient_http_r14_live.py')==PROBE_SHA,'PROBE_CHANGED')
 rt.require(rt.digest(BASE/'activate_transient_http_r14.py')=='c4b73a8f8c4d04b565c9cb544193c860c4c60cc553a479faf1296756b6e6408f','RUNTIME_PRIMITIVES_CHANGED')
 green=rt.read_json(E/'transient-http-r17-probe-negatives-green.json')
 rt.require(green['testsPass'] and green['probeSha256']==PROBE_SHA,'PROBE_TESTS_FAILED')
 rt.require(subprocess.check_output(['git','-C',str(rt.REPO),'rev-parse','HEAD'],text=True).strip()==SOURCE and not subprocess.check_output(['git','-C',str(rt.REPO),'diff','--name-only','HEAD'],text=True).strip(),'SOURCE_NOT_FROZEN')
 return binary,{'sourceCommit':SOURCE,'candidateSha256':BINARY_SHA,'sourceQaSha256':SOURCE_QA_SHA,'fixtureSha256':rt.digest(fixture_path),'probeSha256':PROBE_SHA}
def main():
 receipt=E/'transient-http-r17-mvp-rehearsal.json'
 rt.require(not receipt.exists(),'EXISTING_REHEARSAL_RECONCILE')
 binary,proof=accepted_binary();baseline=rt.runtime_baseline()
 backup=(rt.APP/'config.json').read_bytes();config=json.loads(backup)
 rt.require(config.get('config_store',{}).get('enabled') is False and config.get('logs_store',{}).get('enabled') is False,'SHARED_STORE_ENABLED')
 out=rt.output_directory('transient-http-r17-mvp-rehearsal')
 app=Path(tempfile.mkdtemp(prefix='bifrost-r17-mvp-'));owned={'process':None};port=None
 data={**proof,'status':'STARTING_ISOLATED_E2E','passRehearsal':False,'before':baseline,'oldBinarySha256':rt.OLD_HASH,'configSha256':rt.CONFIG_HASH,'globalConfigSha256':rt.GLOBAL_HASH,'sourceQaAccepted':True,'supplementalHelperQaAccepted':False,'authorization':'User MVP rescope; accepted Bifrost source/binary, coordinator-controlled finite test','logs':str(out)}
 rt.save_receipt(receipt,data)
 try:
  (app/'config.json').write_bytes(backup)
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  rt.require(port!=rt.CANARY_PORT and not rt.connections(port)['listeners'],'PRIVATE_PORT_NOT_FREE')
  owned['process']=rt.launch(binary,port,app,out,'candidate')
  data['candidateProcess']=rt.healthy(owned['process'],binary,port,app)
  rt.save_receipt(receipt,data,status='CANDIDATE_READY',isolatedPort=port)
  data['candidateSSE']=rt.live_probe(port,'R17_MVP_CANDIDATE_OK',PROBE_SHA)
  rt.save_receipt(receipt,data,status='CANDIDATE_REAL_SSE_PASSED')
  data['rollback']=rt.restore_old(owned,port,app,backup,out,PROBE_SHA,'R17_MVP_OLD_OK')
  data['runtimeChecksPassed']=True
 except Exception as exc:data['error']=str(exc)
 finally:
  try:
   rt.stop_owned(owned['process'])
   if port is not None:rt.wait_free(port)
   shutil.rmtree(app);data['cleanupVerified']=True
  except Exception as exc:data.update(cleanupVerified=False,cleanupError=str(exc))
  try:data['after']=rt.verify_baseline_unchanged(baseline);data['productionUnchanged']=True
  except Exception as exc:data.update(productionUnchanged=False,productionError=str(exc))
 passed=bool(data.get('runtimeChecksPassed') and data.get('cleanupVerified') and data.get('productionUnchanged'))
 rt.save_receipt(receipt,data,status='REHEARSAL_PASSED' if passed else 'REHEARSAL_FAILED',passRehearsal=passed)
 print(json.dumps({'receipt':str(receipt),'passRehearsal':passed,'status':data['status'],'error':data.get('error')}),flush=True)
 return 0 if passed else 2
if __name__=='__main__':raise SystemExit(main())
