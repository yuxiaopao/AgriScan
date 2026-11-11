"""Analyze matching APK chunks locally; no SSH without explicit inspect/apply."""
import argparse,base64,hashlib,importlib.util,json,os,re,shlex,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OLD_SHA='1ff189e0f9573d5d0f0cec6396776269b4abe73704bc5bafbc72d1861331a0c2'
CHUNK=5*1024*1024

def blocks(path):
    result=[];total=0;whole=hashlib.sha256()
    with path.open('rb') as stream:
        while raw:=stream.read(CHUNK):
            whole.update(raw);total+=len(raw);result.append({'index':len(result),'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    return whole.hexdigest(),total,result

def compare(new_source,old_parts,old_sha,old_bootstrap):
    if not re.fullmatch('[a-f0-9]{64}',old_sha):raise ValueError('Expected complete old SHA256')
    old_hash=hashlib.sha256();old_bytes=0;old=[]
    names=sorted(path for path in old_parts.iterdir() if re.fullmatch('part-[0-9]{3}',path.name))
    if not names:raise ValueError('Old local uploader parts are unavailable')
    for index,path in enumerate(names):
        if path.name!=f'part-{index:03d}' or path.is_symlink() or not path.is_file():raise ValueError('Old parts must be contiguous regular files')
        raw=path.read_bytes()
        if not 0<len(raw)<=CHUNK or (index<len(names)-1 and len(raw)!=CHUNK):raise ValueError('Old parts do not match 5MiB uploader chunks')
        old_hash.update(raw);old_bytes+=len(raw);old.append({'index':index,'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    if old_hash.hexdigest()!=old_sha:raise ValueError('Old local parts fail full artifact SHA256')
    new_sha,new_bytes,new=blocks(new_source)
    if new_sha==old_sha:raise ValueError('Artifact is identical; the normal uploader can reuse all existing parts')
    reuse=[part for part in new if part['index']<len(old) and part==old[part['index']]]
    return {'old_sha256':old_sha,'old_bytes':old_bytes,'new_sha256':new_sha,'new_bytes':new_bytes,'chunk_bytes':CHUNK,
            'part_count':len(new),'reuse_parts':reuse,'old_bootstrap_apk':old_bootstrap}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new-source',type=Path,required=True);parser.add_argument('--new-sha');parser.add_argument('--old-sha',default=OLD_SHA)
    parser.add_argument('--old-parts',type=Path);parser.add_argument('--old-bootstrap-apk',default='/srv/agriscan/bootstrap/dual-model-app-1.0.4.apk')
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--inspect-server',action='store_true');mode.add_argument('--apply',action='store_true')
    args=parser.parse_args();source=args.new_source.resolve(strict=True)
    if source.suffix.lower()!='.apk':raise SystemExit('Only an explicitly selected APK is supported')
    old_parts=args.old_parts or REPO/'.runtime/artifact-upload-parts'/args.old_sha[:16]
    plan=compare(source,old_parts,args.old_sha,args.old_bootstrap_apk)
    if args.new_sha and args.new_sha!=plan['new_sha256']:raise SystemExit('New APK does not match the supplied final SHA256')
    spec=importlib.util.spec_from_file_location('preseed_standby',ROOT/'preseed-artifact-server.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.validate(plan)
    tag=plan['new_sha256'][:16];target=ROOT/('preseed-plan-'+tag+'.json');target.write_text(json.dumps(plan,indent=2),encoding='utf-8')
    summary={'status':'analyzed_local_only','new_sha256':plan['new_sha256'],'new_bytes':plan['new_bytes'],
             'matching_indices':[part['index'] for part in plan['reuse_parts']],
             'reusable_bytes':sum(part['size_bytes'] for part in plan['reuse_parts']),
             'remaining_upload_bytes':plan['new_bytes']-sum(part['size_bytes'] for part in plan['reuse_parts']),'plan':str(target)}
    if not (args.apply or args.inspect_server):print(json.dumps(summary));return
    encoded=base64.b64encode(json.dumps(plan).encode()).decode()
    remote='python3 - --plan-base64 '+shlex.quote(encoded)+(' --apply' if args.apply else '')
    code=(ROOT/'preseed-artifact-server.py').read_text(encoding='utf-8-sig')
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server',remote],input=code,text=True,
                          encoding='utf-8',errors='replace',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    lines=[line.removeprefix('RESULT ') for line in result.stdout.splitlines() if line.startswith('RESULT ')]
    if len(lines)!=1:raise SystemExit('No unique safe preseed report; no artifact publication was requested')
    report=json.loads(lines[0]);report['ssh_exit_code']=result.returncode
    path=ROOT/('preseed-report-'+tag+'.json');path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps({**summary,'server_result':report['status'],'report':str(path)}))
    if result.returncode or report['status']=='refused_or_incomplete':raise SystemExit(1)

if __name__=='__main__':main()
