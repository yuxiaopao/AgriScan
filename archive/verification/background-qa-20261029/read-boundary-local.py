"""Prepare locally. --read-server explicitly logs in and probes two forbidden GETs."""
import argparse,ast,base64,hashlib,importlib.util,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--credentials',type=Path);parser.add_argument('--output',default='personal-boundary.private.json');parser.add_argument('--read-server',action='store_true');args=parser.parse_args()
    source=(ROOT/'boundary-probe-server.py').read_text(encoding='utf-8');ast.parse(source);digest=hashlib.sha256(source.encode()).hexdigest()
    if not args.read_server:print(json.dumps({'status':'validated_local_only','ssh_called':False,'credentials_read':False,'script_sha256':digest}));return 0
    if not args.credentials or not args.credentials.is_file():parser.error('--credentials requires the private existing administrator handoff file.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.json',args.output):parser.error('Output must be a new JSON filename in this helper directory.')
    output=ROOT/args.output
    if output.exists():raise SystemExit('Existing evidence is preserved; select a new output filename.')
    raw=args.credentials.read_text(encoding='utf-8-sig')
    try:value=json.loads(raw);credentials={key:value[key] for key in ('username','password')}
    except Exception:
        found={match.group(1).lower():match.group(2).strip() for match in re.finditer(r'^\s*(Username|Password)\s*:\s*(.+?)\s*$',raw,re.I|re.M)}
        if set(found)!={'username','password'}:raise SystemExit('Private credential handoff format unavailable; nothing was printed.')
        credentials=found
    if not all(isinstance(value,str) and value for value in credentials.values()):raise SystemExit('Private credentials unavailable.')
    encoded=base64.b64encode(json.dumps(credentials).encode()).decode()
    payload="import base64,json\n_PRIVATE_INPUT=json.loads(base64.b64decode('"+encoded+"'))\n"+source
    try:result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','/srv/agriscan/venv/bin/python -'],input=payload,capture_output=True,text=True,encoding='utf-8',timeout=150)
    except Exception:raise SystemExit('Private boundary request unavailable; no credentials or private stderr were printed.')
    lines=[line.removeprefix('RESULT ') for line in result.stdout.splitlines() if line.startswith('RESULT ')]
    if len(lines)!=1:raise SystemExit('No unique safe boundary report received; private stdout/stderr was withheld.')
    report=json.loads(lines[0]);report['server_script_sha256']=digest;report['ssh_exit_code']=result.returncode
    spec=importlib.util.spec_from_file_location('readonly_local_private_file',ROOT/'read-qa-local.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.private_file(output,report)
    print(json.dumps({'status':report['status'],'private_report':str(output),'foreign_metadata_or_body_returned':False}))
    return 0 if result.returncode==0 else 1
if __name__=='__main__':raise SystemExit(main())
