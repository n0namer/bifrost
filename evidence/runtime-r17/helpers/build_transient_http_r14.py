"""Build a frozen candidate; no runtime/service changes."""
from pathlib import Path
import hashlib, subprocess, json, os, sys, time
base=Path(__file__).resolve().parent
repo=base/'bifrost-sparse'
sha=sys.argv[1] if len(sys.argv)>1 else ''
if len(sha)!=40 or any(x not in '0123456789abcdef' for x in sha): raise SystemExit('EXACT_SHA_REQUIRED')
def git(*args):
 r=subprocess.run(['git','-C',str(repo),*args],capture_output=True,text=True,encoding='utf-8',check=True)
 return r.stdout.strip()
if git('rev-parse','HEAD')!=sha or git('status','--porcelain','--untracked-files=no'): raise SystemExit('SOURCE_NOT_FROZEN')
exe=base/('bifrost-transient-r14-'+sha[:12]+'.exe')
if exe.exists(): raise SystemExit('CANDIDATE_FILE_ALREADY_EXISTS_RECONCILE')
prefix=base/'evidence'/('transient-http-r14-build-'+sha[:12])
names=git('diff','--name-only','a9d130d3fc39b8ddc907586ec1eb5a7ce470df91',sha).splitlines()
def hashes(): return {n:hashlib.sha256((repo/n).read_bytes()).hexdigest() for n in names if (repo/n).is_file()}
before=hashes()
go=Path(r'C:\Users\Рафик\go\pkg\mod\golang.org\toolchain@v0.0.1-go1.27.3.windows-amd64\bin\go.exe')
env={**os.environ,'GOPROXY':'off','GOSUMDB':'off','GOMAXPROCS':'2','GOTOOLCHAIN':'local','GOFLAGS':'','GOWORK':str(repo/'go.work') if (repo/'go.work').exists() else 'off','PATH':str(go.parent)+os.pathsep+os.environ.get('PATH','')}
version=subprocess.run([str(go),'version'],env=env,capture_output=True,text=True,check=True).stdout.strip()
if version!='go version go1.27.3 windows/amd64':raise SystemExit('UNEXPECTED_GO_TOOLCHAIN')
if (repo/'go.work').exists():
 workspace=json.loads(subprocess.run([str(go),'work','edit','-json',str(repo/'go.work')],env=env,capture_output=True,text=True,check=True).stdout)
 if any(not (repo/u['DiskPath']).resolve().is_relative_to(repo.resolve()) for u in workspace.get('Use',[])):raise SystemExit('WORKSPACE_OUTSIDE_FROZEN_REPOSITORY')
fixed_version='v1.77.1-0.20261028061327-329917ed143c'
fixed_sum='h1:QyWiyavtnN3H27uPp835jpoGenXdz4sQGgvf2jC0zUc='
resolved=subprocess.run([str(go),'list','-mod=readonly','-m','-json','github.com/valyala/fasthttp'],cwd=str(repo),env=env,capture_output=True,text=True,encoding='utf-8',check=True)
module=json.loads(resolved.stdout)
if module.get('Version')!=fixed_version or module.get('Replace'):raise SystemExit('DEPENDENCY_PIN_NOT_VERIFIED')
work=repo/'go.work'; work_before=hashlib.sha256(work.read_bytes()).hexdigest() if work.exists() else None
command=[str(go),'build','-buildvcs=true','-mod=readonly','-p','2','-o',str(exe),'./transports/bifrost-http']
start=time.monotonic(); error=None
with prefix.with_suffix('.log').open('w',encoding='utf-8') as log:
 p=subprocess.Popen(command,cwd=str(repo),env=env,stdout=log,stderr=subprocess.STDOUT)
 print(json.dumps({'event':'BUILD_STARTED','pid':p.pid,'candidate':str(exe),'source':sha}),flush=True)
 try: code=p.wait(timeout=900)
 except subprocess.TimeoutExpired:
  subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True)
  p.wait();code=124;error='BUILD_TIMEOUT'
after=hashes()
work_after=hashlib.sha256(work.read_bytes()).hexdigest() if work.exists() else None
stable=git('rev-parse','HEAD')==sha and not git('status','--porcelain','--untracked-files=no') and before==after and work_before==work_after
meta=subprocess.run([str(go),'version','-m',str(exe)],capture_output=True,text=True,encoding='utf-8').stdout if code==0 else ''
dependency_verified=any('github.com/valyala/fasthttp' in line and fixed_version in line and fixed_sum in line for line in meta.splitlines())
toolchain_verified=bool(meta.splitlines()) and meta.splitlines()[0].endswith('go1.27.3')
revision_verified=any(line.strip().split('\t')==['build','vcs.revision='+sha] for line in meta.splitlines())
out={'goExecutable':str(go),'toolchainVerified':toolchain_verified,'vcsRevisionVerified':revision_verified,'resolvedDependency':module,'dependencyVerified':dependency_verified,'workspaceSha256':work_after,'sourceCommit':sha,'command':command,'seconds':time.monotonic()-start,'exitCode':code,'sourceStable':stable,'changedFileHashes':after,'binary':str(exe),'binarySha256':hashlib.sha256(exe.read_bytes()).hexdigest() if exe.exists() else None,'goBuildMetadata':meta,'error':error,'pass':code==0 and stable and dependency_verified and toolchain_verified and revision_verified,'productionProcessModified':False}
prefix.with_suffix('.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps({k:out[k] for k in ['sourceCommit','seconds','exitCode','sourceStable','binary','binarySha256','error','pass']}),flush=True)
if code!=0: print(prefix.with_suffix('.log').read_text(encoding='utf-8')[-7000:],flush=True)
sys.exit(0 if out['pass'] else 2)