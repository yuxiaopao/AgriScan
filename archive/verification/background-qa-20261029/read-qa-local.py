"""Validate locally by default. Only --read-server dispatches the read-only SSH helper."""
import argparse,ast,hashlib,json,os,re,shlex,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUN_TAG='QA-BACKGROUND-20261029-1814'
def private_file(path,body):
    if path.exists():raise RuntimeError('Choose a new output filename; existing evidence is preserved.')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        if os.name=='nt':
            identity=subprocess.run(['whoami','/user','/fo','csv','/nh'],capture_output=True,text=True,check=True)
            found=re.search(r'S-1-5-[0-9-]+',identity.stdout)
            if not found:raise RuntimeError('Private output identity unavailable.')
            secured=subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r','*'+found.group()+':(F)','/grant:r','*S-1-5-18:(F)'],capture_output=True,text=True)
            if secured.returncode:raise RuntimeError('Private output ACL unavailable.')
        with os.fdopen(fd,'w',encoding='utf-8') as stream:fd=None;json.dump(body,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
    finally:
        if fd is not None:os.close(fd)
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--mode',choices=['evidence','runtime'],default='evidence');parser.add_argument('--owner-id');parser.add_argument('--run-tag',default=RUN_TAG);parser.add_argument('--samples',type=int,default=1);parser.add_argument('--interval',type=float,default=2);parser.add_argument('--output');parser.add_argument('--read-server',action='store_true');args=parser.parse_args()
    if args.run_tag!=RUN_TAG:parser.error('Only the exact authorized run tag is accepted.')
    if args.mode=='evidence' and not re.fullmatch(r'[0-9a-f]{32}',args.owner_id or ''):parser.error('Evidence requires the explicitly authorized 32-character --owner-id.')
    if not 1<=args.samples<=10 or not 0<=args.interval<=5 or (args.samples-1)*args.interval>45:parser.error('Sampling is limited to ten samples and 45 seconds.')
    filename=args.output or ('production-evidence.private.json' if args.mode=='evidence' else 'runtime-memory.private.json')
    output=ROOT/filename
    if output.parent!=ROOT or not re.fullmatch(r'[A-Za-z0-9_.-]+\.json',filename):parser.error('Output must be a new JSON filename in this helper directory.')
    source_path=ROOT/('qa-evidence-server.py' if args.mode=='evidence' else 'runtime-memory-server.py');source=source_path.read_text(encoding='utf-8');ast.parse(source)
    digest=hashlib.sha256(source.encode()).hexdigest()
    if not args.read_server:
        print(json.dumps({'status':'validated_local_only','mode':args.mode,'run_tag':RUN_TAG,'server_script_sha256':digest,'ssh_called':False,'production_mutations':False}));return 0
    if output.exists():raise SystemExit('Output already exists; preserve it and select a new filename.')
    parameters=['--run-tag',RUN_TAG,'--owner-id',args.owner_id] if args.mode=='evidence' else ['--samples',str(args.samples),'--interval',str(args.interval)]
    remote='/srv/agriscan/venv/bin/python - '+shlex.join(parameters)
    try:result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=10','tencent-server',remote],input=source,capture_output=True,text=True,encoding='utf-8',timeout=150,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except Exception:raise SystemExit('Read-only SSH helper unavailable; no private stderr was printed.')
    lines=[line.removeprefix('RESULT ') for line in result.stdout.splitlines() if line.startswith('RESULT ')]
    if len(lines)!=1:raise SystemExit('No unique read-only report received; private stdout/stderr was withheld.')
    report=json.loads(lines[0]);report['server_script_sha256']=digest;report['ssh_exit_code']=result.returncode
    private_file(output,report)
    print(json.dumps({'status':report['status'],'mode':args.mode,'private_report':str(output),'production_mutations':False}))
    return 0 if result.returncode==0 else 1
if __name__=='__main__':raise SystemExit(main())
