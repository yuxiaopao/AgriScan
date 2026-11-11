"""Seed only byte-verified matching chunks; never writes the published artifact."""
import argparse,base64,hashlib,json,os,re,stat
from pathlib import Path
from uuid import uuid4

BOOT=Path('/srv/agriscan/bootstrap')
PARTS=BOOT/'artifact-parts'
CHUNK=5*1024*1024
class Refused(RuntimeError):pass

def require(value,code):
    if not value:raise Refused(code)

def digest(raw):return hashlib.sha256(raw).hexdigest()

def validate(plan):
    require(set(plan)=={'old_sha256','old_bytes','new_sha256','new_bytes','chunk_bytes','part_count','reuse_parts','old_bootstrap_apk'},'plan_fields')
    for name in ('old_sha256','new_sha256'):require(isinstance(plan[name],str) and re.fullmatch('[a-f0-9]{64}',plan[name]),'artifact_sha')
    require(plan['old_sha256']!=plan['new_sha256'],'same_artifact_needs_no_preseed')
    require(plan['chunk_bytes']==CHUNK and type(plan['new_bytes']) is int and 0<plan['new_bytes']<=512*1024*1024,'chunk_or_size')
    require(type(plan['old_bytes']) is int and 0<plan['old_bytes']<=512*1024*1024,'old_size')
    require(plan['part_count']==(plan['new_bytes']+CHUNK-1)//CHUNK,'part_count')
    require(isinstance(plan['old_bootstrap_apk'],str) and re.fullmatch(r'/srv/agriscan/bootstrap/[A-Za-z0-9_.-]+\.apk',plan['old_bootstrap_apk']),'old_apk_path')
    require(isinstance(plan['reuse_parts'],list),'reuse_parts')
    seen=set()
    for part in plan['reuse_parts']:
        require(set(part)=={'index','size_bytes','sha256'},'part_fields')
        i=part['index'];require(type(i) is int and 0<=i<plan['part_count'] and i not in seen,'part_index');seen.add(i)
        expected=min(CHUNK,plan['new_bytes']-i*CHUNK)
        require(part['size_bytes']==expected and part['size_bytes']==min(CHUNK,max(0,plan['old_bytes']-i*CHUNK)),'part_size')
        require(isinstance(part['sha256'],str) and re.fullmatch('[a-f0-9]{64}',part['sha256']),'part_sha')

def directory(path):
    require(path.is_dir() and not path.is_symlink(),'directory_not_regular')
    for parent in path.parents:
        require(not parent.is_symlink(),'symlink_parent')

def valid_part(path,part):
    if not path.exists():return False
    require(path.is_file() and not path.is_symlink(),'part_not_regular')
    return path.stat().st_size==part['size_bytes'] and digest(path.read_bytes())==part['sha256']

def read_old_apk(plan):
    path=Path(plan['old_bootstrap_apk'])
    if not path.is_file() or path.is_symlink():return None
    require(path.parent==BOOT,'source_not_bootstrap')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    stream=os.fdopen(fd,'rb')
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):stream.close();return None
    whole=hashlib.file_digest(stream,'sha256').hexdigest()
    if whole!=plan['old_sha256'] or os.fstat(stream.fileno()).st_size!=plan['old_bytes']:stream.close();return None
    return stream

def source_chunk(plan,part,old_stream):
    cached=PARTS/plan['old_sha256']/f"part-{part['index']:03d}"
    if cached.parent.is_dir() and not cached.parent.is_symlink():
        directory(cached.parent)
        if valid_part(cached,part):return cached.read_bytes(),'old_parts'
    if old_stream is not None:
        old_stream.seek(part['index']*CHUNK);raw=old_stream.read(part['size_bytes'])
        if len(raw)==part['size_bytes'] and digest(raw)==part['sha256']:return raw,'old_bootstrap_apk'
    raise Refused('verified_matching_source_part_unavailable')

def execute(plan,apply=False):
    validate(plan);directory(BOOT);directory(PARTS)
    target=PARTS/plan['new_sha256']
    require(target.parent==PARTS and target.resolve().parent==PARTS.resolve() and not target.is_symlink(),'target_directory_scope')
    if target.exists():directory(target)
    report={'status':'prepared_read_only','new_sha256':plan['new_sha256'],'old_sha256':plan['old_sha256'],
            'destination':str(target),'published_artifact_modified':False,'copied_parts':[],'already_valid_parts':[],
            'reusable_bytes':sum(part['size_bytes'] for part in plan['reuse_parts']),'apply':apply}
    if not plan['reuse_parts']:report['status']='no_reusable_parts';return report
    old_stream=read_old_apk(plan)
    try:
        # Verify every proposed source before the first destination write.
        for part in plan['reuse_parts']:source_chunk(plan,part,old_stream)
        if not apply:return report
        if not target.exists():target.mkdir(mode=0o755)
        directory(target)
        for part in plan['reuse_parts']:
            output=target/f"part-{part['index']:03d}"
            if output.exists():
                require(valid_part(output,part),'existing_target_part_conflict_preserved')
                report['already_valid_parts'].append(part['index']);continue
            raw,source=source_chunk(plan,part,old_stream)
            require(len(raw)==part['size_bytes'] and digest(raw)==part['sha256'],'source_part_changed')
            temporary=target/('.preseed-'+output.name+'-'+uuid4().hex)
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o644)
            try:
                with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
                require(valid_part(temporary,part),'temporary_part_verification_failed')
                try:os.link(temporary,output)  # Never overwrite a concurrent uploader.
                except FileExistsError:require(valid_part(output,part),'concurrent_target_conflict_preserved')
                require(valid_part(output,part),'published_part_verification_failed')
                report['copied_parts'].append({'index':part['index'],'source':source,'sha256':part['sha256']})
            finally:temporary.unlink(missing_ok=True)
        report['status']='passed'
        return report
    finally:
        if old_stream is not None:old_stream.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan-base64',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    try:report=execute(json.loads(base64.b64decode(args.plan_base64,validate=True)),args.apply)
    except BaseException as error:report={'status':'refused_or_incomplete','error':str(error) if isinstance(error,Refused) else type(error).__name__,'published_artifact_modified':False}
    print('RESULT '+json.dumps(report),flush=True)
    raise SystemExit(0 if report['status'] in {'passed','prepared_read_only','no_reusable_parts'} else 1)

if __name__=='__main__':main()
