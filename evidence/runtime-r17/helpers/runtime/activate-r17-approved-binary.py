"""One coordinator-controlled switch of the existing isolated canary."""
from pathlib import Path
import json,os,runpy,time
BASE=Path(__file__).resolve().parents[1];E=BASE/'evidence'
check=runpy.run_path(str(E/'run-r17-approved-binary-e2e.py'))
rt=check['rt']
def main():
 receipt=E/'transient-http-r17-mvp-activation.json'
 rt.require(not receipt.exists(),'EXISTING_ACTIVATION_RECONCILE')
 binary,proof=check['accepted_binary']()
 rehearsal_path=E/'transient-http-r17-mvp-rehearsal.json';rehearsal=rt.read_json(rehearsal_path)
 rt.require(rehearsal.get('passRehearsal') is True and rehearsal.get('cleanupVerified') is True and rehearsal.get('productionUnchanged') is True,'REHEARSAL_NOT_PASSED')
 for key,value in proof.items():rt.require(rehearsal.get(key)==value,'REHEARSAL_BINDING_'+key)
 rt.require(rehearsal.get('oldBinarySha256')==rt.OLD_HASH and rehearsal.get('configSha256')==rt.CONFIG_HASH and rehearsal.get('globalConfigSha256')==rt.GLOBAL_HASH,'REHEARSAL_BASELINE_CHANGED')
 out=rt.output_directory('transient-http-r17-mvp-activation')
 data={**proof,'status':'PREFLIGHT','passActivation':False,'launcherPid':os.getpid(),'rehearsalSha256':rt.digest(rehearsal_path),'logs':str(out),'globalRouteChanged':False,'sourceQaAccepted':True,'supplementalHelperQaAccepted':False}
 owned={'process':None};stopped=False;baseline=None;backup=None
 rt.save_receipt(receipt,data)
 try:
  baseline=rt.runtime_baseline();backup=(rt.APP/'config.json').read_bytes()
  rt.require(rt.digest(rt.APP/'config.json')==rt.CONFIG_HASH,'CONFIG_CHANGED')
  (out/'config-before.json').write_bytes(backup)
  samples=[]
  for _ in range(5):
   samples.append(rt.idle_sample(rt.CANARY_PORT,rt.OLD_PID,('passthrough','passthrough_stream')));time.sleep(1)
  rt.verify_baseline_unchanged(baseline)
  rt.save_receipt(receipt,data,status='DRAIN_VERIFIED',before=baseline,drainSamples=samples,backupSha256=rt.digest(out/'config-before.json'))
  final=rt.idle_sample(rt.CANARY_PORT,rt.OLD_PID,('passthrough','passthrough_stream'))
  stopped=True;rt.stop_original();rt.wait_free(rt.CANARY_PORT)
  rt.require(rt.digest(binary)==check['BINARY_SHA'],'BINARY_CHANGED')
  owned['process']=rt.launch(binary,rt.CANARY_PORT,rt.APP,out,'candidate')
  who=rt.healthy(owned['process'],binary,rt.CANARY_PORT,rt.APP)
  rt.save_receipt(receipt,data,status='CANDIDATE_LISTENING',newProcess=who,finalDrainSample=final)
  sse=rt.live_probe(rt.CANARY_PORT,'R17_MVP_ACTIVE_OK',check['PROBE_SHA'])
  readiness=rt.unchanged_static(baseline)
  idle=rt.idle_sample(rt.CANARY_PORT,owned['process'].pid,('passthrough_stream',))
  rt.require(rt.digest(binary)==check['BINARY_SHA'] and rt.digest(BASE/'probe_transient_http_r14_live.py')==check['PROBE_SHA'],'POST_SWITCH_HASH_CHANGED')
  rt.save_receipt(receipt,data,status='ACTIVE_VERIFIED',passActivation=True,realSSE=sse,afterReady=readiness,afterIdle=idle,configUnchanged=True,globalConfigUnchanged=True,rollbackAvailable=str(rt.OLD_EXE),rollbackRehearsed=True)
 except Exception as exc:
  data.update(status='ACTIVATION_FAILED',error=str(exc),passActivation=False)
  if stopped:
   try:
    original=rt.identity(rt.OLD_PID)
    if rt.process_matches(original,rt.OLD_PID,rt.OLD_CREATION,rt.OLD_EXE):
     rt.require_listener(rt.connections(rt.CANARY_PORT)['listeners'],rt.OLD_PID)
     data.update(status='ORIGINAL_UNCHANGED',original=original)
    else:
     data['rollback']=rt.restore_old(owned,rt.CANARY_PORT,rt.APP,backup,out,check['PROBE_SHA'],'R17_MVP_ROLLBACK_OK')
     rt.unchanged_static(baseline);data['status']='ROLLED_BACK_VERIFIED'
   except Exception as failure:data.update(status='ROLLBACK_BLOCKED',rollbackError=str(failure))
  else:data['runtimeUnchanged']=True
  rt.save_receipt(receipt,data)
 print(json.dumps({'receipt':str(receipt),'status':data['status'],'passActivation':data['passActivation'],'newPid':data.get('newProcess',{}).get('pid')}),flush=True)
 if owned['process'] is not None and owned['process'].poll() is None:owned['process'].wait()
 return 0 if data['passActivation'] else 2
if __name__=='__main__':raise SystemExit(main())
