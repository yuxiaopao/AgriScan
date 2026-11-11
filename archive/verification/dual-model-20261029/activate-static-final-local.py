"""Local validation by default; explicit --apply sends static-only script via SSH."""
import argparse,ast,base64,hashlib,importlib.util,json,os,shlex,subprocess,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,default=ROOT/'static-final-plan.json');parser.add_argument('--apply',action='store_true');args=parser.parse_args()
source=(ROOT/'activate-static-final-server.py').read_text(encoding='utf-8-sig')
helpers=(ROOT/'activate-server.py').read_text(encoding='utf-8-sig')
ast.parse(source);ast.parse(helpers)
if os.name=='nt':sys.modules['fcntl']=types.SimpleNamespace();sys.modules['grp']=types.SimpleNamespace()
spec=importlib.util.spec_from_file_location('static_final_reviewed',ROOT/'activate-static-final-server.py');m=importlib.util.module_from_spec(spec);m.__dict__['_REVIEWED_HELPERS']=helpers;spec.loader.exec_module(m)
plan=json.loads(args.plan.read_text(encoding='utf-8-sig'));m.validate(plan)
summary={'status':'validated_local_only','release_id':plan['release_id'],'script_sha256':hashlib.sha256(source.encode()).hexdigest(),
         'helpers_sha256':hashlib.sha256(helpers.encode()).hexdigest(),'api_restart_allowed':False}
if not args.apply:print(json.dumps(summary));raise SystemExit(0)
encoded=base64.b64encode(json.dumps(plan).encode()).decode()
bundle='_REVIEWED_HELPERS = '+repr(helpers)+'\n'+source
remote='/srv/agriscan/venv/bin/python - --plan-base64 '+shlex.quote(encoded)+' --apply'
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=8','tencent-server',remote],input=bundle,
                      text=True,encoding='utf-8',errors='replace',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600,
                      creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
for line in result.stdout.splitlines():
    if line.startswith(('STAGE ','PRECHECK_FAILED ')):print(line,flush=True)
lines=[line.removeprefix('RESULT ') for line in result.stdout.splitlines() if line.startswith('RESULT ')]
if len(lines)!=1:raise SystemExit('No unique static activation report. Inspect its private log before retry; no API restart is authorized.')
report=json.loads(lines[0]);report['static_script_sha256']=summary['script_sha256'];report['reviewed_helpers_sha256']=summary['helpers_sha256'];report['ssh_exit_code']=result.returncode
output=ROOT/'static-final-deployment.json';output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':report['status'],'report':str(output)}),flush=True)
raise SystemExit(0 if result.returncode==0 and report['status']=='passed' else 1)
