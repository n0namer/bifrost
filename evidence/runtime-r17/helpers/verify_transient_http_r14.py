#!/usr/bin/env python3
"""Finite same-binary contract probe; loopback fixture and dummy credentials only."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
from threading import Thread, Lock
from pathlib import Path
import subprocess, socket, json, time, hashlib, os, sys
from http.client import IncompleteRead
BASE=Path(__file__).resolve().parent
BIN=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else BASE/'bifrost-patched-final.exe'
ROOT=BASE/'evidence'/('transient-http-r14-binary-'+time.strftime('%Y%m%d-%H%M%S'))
ROOT.mkdir()
lock=Lock(); events=[]
def rawjson(x): return json.dumps(x,separators=(',',':')).encode()
class Fixture(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def log_message(self,*a): pass
 def reply(self,status,raw,headers=None,split=False):
  self.send_response(status)
  self.send_header('Content-Type','application/json')
  self.send_header('Content-Length',str(len(raw)))
  self.send_header('Connection','close')
  for k,v in (headers or {}).items(): self.send_header(k,v)
  self.end_headers()
  try:
   if split:
    cut=raw.find(b'replay_refused')+4
    self.wfile.write(raw[:cut]); self.wfile.flush(); time.sleep(.08)
    self.wfile.write(raw[cut:])
   else: self.wfile.write(raw)
  except (BrokenPipeError,ConnectionResetError): pass
  self.close_connection=True
 def do_GET(self): self.reply(200,rawjson({'object':'list','data':[]}))
 def do_POST(self):
  data=self.rfile.read(int(self.headers.get('Content-Length','0')))
  body=json.loads(data); case=body['metadata']['test_case']
  with lock:
   attempt=1+sum(x['case']==case for x in events)
   events.append({'case':case,'attempt':attempt,'at':time.monotonic(),'bodySha256':hashlib.sha256(data).hexdigest()})
  refusal=rawjson({'error':{'code':'upstream_reset_replay_refused','message':'synthetic'}})
  if case=='429-no-retry': return self.reply(429,rawjson({'error':{'code':'rate_limit_exceeded'}}),{'X-Should-Retry':'false'})
  if case=='429-split-refusal': return self.reply(429,refusal,split=True)
  if case=='429-quota': return self.reply(429,rawjson({'error':{'code':'insufficient_quota'}}))
  if case=='429-exhausted': return self.reply(429,rawjson({'error':{'code':'rate_limit_exceeded'}}))
  if case in ['429-once','429-stream-once'] and attempt==1:
   return self.reply(429,rawjson({'error':{'code':'rate_limit_exceeded'}}),{'Retry-After':'1'})
  if case in ['500-once','500-unary-once','502-once','502-unary-once','503-once','504-once','509-once','509-unary-once','529-once'] and attempt==1:
   return self.reply(int(case[:3]),rawjson({'error':{'code':'synthetic_'+case[:3]}}),{'Retry-After':'1'} if case=='509-once' else None)
  if case=='509-no-retry': return self.reply(509,rawjson({'error':{'code':'synthetic_509'}}),{'X-Should-Retry':'false'})
  if case in ['509-split-refusal','502-split-refusal']: return self.reply(int(case[:3]),refusal,split=True)
  if case=='509-quota': return self.reply(509,rawjson({'error':{'code':'insufficient_quota'}}))
  if case=='509-exhausted': return self.reply(509,rawjson({'error':{'code':'synthetic_509'}}))
  if case in ['501-once','505-once','401-once']: return self.reply(int(case[:3]),rawjson({'error':{'code':'synthetic_nonretry'}}))
  if case=='509-overflow': return self.reply(509,b'x'*(1048576+1)+b'upstream_reset_replay_refused')
  if case=='509-overflow-clear': return self.reply(509,b'x'*(1048576+64))
  if case=='509-chunked-truncated' or (case=='509-chunked-once' and attempt==1):
   raw=rawjson({'error':{'code':'synthetic_509'}})
   self.send_response(509); self.send_header('Content-Type','application/json'); self.send_header('Transfer-Encoding','chunked'); self.send_header('Connection','close'); self.end_headers()
   self.wfile.write(('%x\r\n'%len(raw)).encode()+raw+b'\r\n')
   if case=='509-chunked-once': self.wfile.write(b'0\r\n\r\n')
   self.wfile.flush(); self.close_connection=True; return
  if case in ['509-incomplete','200-partial']:
   raw=b'{"error":{"code":"synthetic_509"}}' if case=='509-incomplete' else b'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"fixture"}\n\n'
   self.send_response(509 if case=='509-incomplete' else 200)
   self.send_header('Content-Type','application/json' if case=='509-incomplete' else 'text/event-stream')
   self.send_header('Content-Length',str(len(raw)+64)); self.send_header('Connection','close'); self.end_headers()
   self.wfile.write(raw); self.wfile.flush(); self.close_connection=True; return
  if body.get('stream'):
   raw=b'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"FIXTURE_SUCCESS"}\n\nevent: response.completed\ndata: {"type":"response.completed","response":{"id":"resp_fixture","status":"completed"}}\n\n'
   self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Content-Length',str(len(raw))); self.send_header('Connection','close'); self.end_headers(); self.wfile.write(raw); self.close_connection=True
  else: self.reply(200,rawjson({'id':'resp_fixture','object':'response','status':'completed'}))
server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
fixtureport=server.server_address[1]
thread=Thread(target=server.serve_forever,daemon=True); thread.start()
with socket.socket() as s:
 s.bind(('127.0.0.1',0)); gatewayport=s.getsockname()[1]
config={'client':{'drop_excess_requests':False},'providers':{'openai':{'keys':[{'name':'isolated-fixture','value':'synthetic-no-provider-key','models':['*'],'weight':1}],'concurrency_and_buffer_size':{'concurrency':1,'buffer_size':16},'network_config':{'base_url':f'http://127.0.0.1:{fixtureport}','allow_private_network':True,'max_retries':2,'retry_backoff_initial':100,'retry_backoff_max':400,'default_request_timeout_in_seconds':10}}},'config_store':{'enabled':False},'logs_store':{'enabled':False}}
(ROOT/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
digest=hashlib.sha256(BIN.read_bytes()).hexdigest()
log=(ROOT/'gateway.log').open('w',encoding='utf-8')
proc=None; results=[]; error=None
opener=build_opener(ProxyHandler({}))
cases=[('429-once',False,200,2),('429-stream-once',True,200,2),('429-no-retry',True,429,1),('429-split-refusal',True,429,1),('429-quota',False,429,1),('429-exhausted',False,429,3),
 ('500-once',True,200,2),('500-unary-once',False,200,2),('502-once',True,200,2),('502-unary-once',False,200,2),('503-once',True,200,2),('504-once',True,200,2),('509-once',True,200,2),('509-unary-once',False,200,2),('529-once',True,200,2),
 ('509-no-retry',True,509,1),('509-split-refusal',True,509,1),('502-split-refusal',True,502,1),('509-quota',True,509,1),('509-exhausted',True,509,3),
 ('501-once',True,501,1),('505-once',True,505,1),('401-once',True,401,1),('509-overflow',True,509,1),('509-overflow-clear',True,509,1),('509-incomplete',True,509,1),('200-partial',True,200,1),('509-chunked-once',True,200,2),('509-chunked-truncated',True,509,1)]
try:
 proc=subprocess.Popen([str(BIN),'-host','127.0.0.1','-port',str(gatewayport),'-app-dir',str(ROOT),'-log-level','warn'],cwd=str(ROOT),stdout=log,stderr=subprocess.STDOUT)
 deadline=time.monotonic()+20
 while True:
  if proc.poll() is not None: raise RuntimeError('isolated gateway exited '+str(proc.returncode))
  try:
   with socket.create_connection(('127.0.0.1',gatewayport),timeout=.5): break
  except OSError:
   if time.monotonic()>deadline: raise RuntimeError('isolated gateway startup timeout')
   time.sleep(.1)
 for case,stream,expected_status,expected_sends in cases:
  data=rawjson({'model':'gpt-6-luna','input':'fixture-only','store':False,'stream':stream,'metadata':{'test_case':case}})
  req=Request(f'http://127.0.0.1:{gatewayport}/openai_passthrough/v1/responses',data=data,headers={'Content-Type':'application/json','Authorization':'Bearer synthetic-client'},method='POST')
  started=time.monotonic()
  incomplete=False
  try:
   response=opener.open(req,timeout=15)
  except HTTPError as e: response=e
  with response as r:
   status=r.status; headers=dict(r.headers)
   try: raw=r.read()
   except IncompleteRead as e: raw=e.partial; incomplete=True
  ev=[x for x in events if x['case']==case]
  delay=ev[1]['at']-ev[0]['at'] if len(ev)>1 else None
  passed=status==expected_status and len(ev)==expected_sends
  if case in ['429-once','429-stream-once','509-once']: passed=passed and delay is not None and delay>=.95
  if stream and status==200:
   passed=passed and raw.count(b'event: response.completed')==(0 if case=='200-partial' else 1)
  if status==200 and case!='200-partial':
   passed=passed and (b'"delta":"FIXTURE_SUCCESS"' in raw if stream else json.loads(raw)=={'id':'resp_fixture','object':'response','status':'completed'})
   passed=passed and b'rate_limit_exceeded' not in raw and b'synthetic_5' not in raw
  if case=='200-partial': passed=passed and b'"delta":"fixture"' in raw
  if case=='509-overflow': passed=passed and raw==b'x'*(1048576+1)+b'upstream_reset_replay_refused'
  if case=='509-overflow-clear': passed=passed and raw==b'x'*(1048576+64)
  if case in ['429-split-refusal','509-split-refusal','502-split-refusal']: passed=passed and raw==rawjson({'error':{'code':'upstream_reset_replay_refused','message':'synthetic'}})
  if case in ['429-quota','509-quota']: passed=passed and raw==rawjson({'error':{'code':'insufficient_quota'}})
  if case in ['429-no-retry','509-no-retry']:
   normalized={k.lower():v for k,v in headers.items()}
   passed=passed and normalized.get('x-should-retry')=='false'
  if case=='509-exhausted': passed=passed and raw==rawjson({'error':{'code':'synthetic_509'}})
  if case=='509-chunked-truncated': passed=passed and rawjson({'error':{'code':'synthetic_509'}}) in raw
  passed=passed and all(x['bodySha256']==hashlib.sha256(data).hexdigest() for x in ev)
  row={'case':case,'stream':stream,'status':status,'physicalSends':len(ev),'retryGapSeconds':delay,'elapsedSeconds':time.monotonic()-started,'responseBytes':len(raw),'incompleteRead':incomplete,'bodyPreservedEverySend':all(x['bodySha256']==hashlib.sha256(data).hexdigest() for x in ev),'passRequiredContract':passed}
  results.append(row); print(json.dumps(row),flush=True)
except Exception as e: error=type(e).__name__+': '+str(e)
finally:
 if proc is not None and proc.poll() is None:
  proc.terminate()
  try: proc.wait(timeout=5)
  except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
 server.shutdown(); server.server_close(); log.close()
 out={'harnessSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'binary':str(BIN),'sha256':digest,'isolatedPid':proc.pid if proc else None,'fixturePort':fixtureport,'gatewayPort':gatewayport,'productionProcessesModified':False,'realProviderCalls':0,'clientRetries':0,'maxRetries':2,'cases':results,'error':error,'passRequiredContract':error is None and len(results)==len(cases) and all(x['passRequiredContract'] for x in results),'notes':['Required new bounded retry contract; old binary is expected to fail positive5xx/509 cases.','This checks the executable file, not a source-revision provenance claim.']}
 (ROOT/'summary.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
 print(json.dumps({'summary':str(ROOT/'summary.json'),'passRequiredContract':out['passRequiredContract'],'error':error}),flush=True)
sys.exit(0 if out['passRequiredContract'] else 2)
