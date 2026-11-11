"""CAS-only AgriScan request-streaming repair. Default is inspection, never API restart."""
import argparse
import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from urllib.request import ProxyHandler, build_opener

INC=Path('/etc/nginx/agriscan-locations.inc')
PROTECTED=('/etc/nginx/nginx.conf','/etc/nginx/conf.d/zz-agriscan.conf','/etc/nginx/conf.d/flowly-share.conf')
BACKUPS=Path('/srv/agriscan/shared/backups')
ANCHOR=b'location /agriscan/api/ {\n    proxy_pass http://127.0.0.1:18000/api/;\n'
ADDED=b'    proxy_http_version 1.1;\n    proxy_request_buffering off;\n'

class Refused(RuntimeError): pass

def require(value,code):
    if not value: raise Refused(code)

def sha(raw): return hashlib.sha256(raw).hexdigest()

def patch(raw):
    require(raw.count(ANCHOR)==1,'api_block_anchor_not_unique')
    block=raw.split(ANCHOR,1)[1].split(b'\n}',1)[0]
    require(b'proxy_request_buffering' not in block and b'proxy_http_version' not in block,'api_proxy_directive_already_present')
    result=raw.replace(ANCHOR,ANCHOR+ADDED,1)
    require(result.replace(ANCHOR+ADDED,ANCHOR,1)==raw,'non_streaming_configuration_changed')
    return result

def run(args,code,timeout=20):
    result=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    require(result.returncode==0,code)
    return result.stdout.strip()

def pid(name): return int(run(['systemctl','show',name,'--property=MainPID','--value'],'service_pid_unavailable'))

def children(master):
    return set(Path(f'/proc/{master}/task/{master}/children').read_text().split())

def reload_nginx(master,old_children):
    run(['systemctl','reload','nginx'],'nginx_reload_failed',30)
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        require(pid('nginx')==master,'nginx_master_changed_externally')
        fresh=children(master)-old_children
        if fresh:
            run(['systemctl','is-active','--quiet','nginx'],'nginx_not_active')
            return sorted(fresh)
        time.sleep(.25)
    raise Refused('nginx_new_worker_generation_not_observed')

def publish(raw,expected_sha,identity,tag):
    require(not INC.is_symlink() and INC.is_file() and sha(INC.read_bytes())==expected_sha,'include_concurrent_change')
    original=INC.stat()
    require((original.st_uid,original.st_gid,stat.S_IMODE(original.st_mode))==identity,'include_identity_changed')
    temporary=INC.with_name('.agriscan-locations.'+tag+'.next')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.chown(temporary,identity[0],identity[1]);temporary.chmod(identity[2])
        require(sha(INC.read_bytes())==expected_sha,'include_concurrent_change')
        os.replace(temporary,INC)
    finally:temporary.unlink(missing_ok=True)

def private_write(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())

def health():
    with build_opener(ProxyHandler({})).open('http://127.0.0.1:18000/api/health',timeout=10) as response:
        result=json.loads(response.read(65536))
    require(result.get('status')=='ok' and result.get('model')=='ready','local_api_health_unavailable')
    return result

def validate(plan):
    require(set(plan)=={'run_id','expected_inc_sha256','expected_patched_sha256','protected_sha256'},'plan_fields')
    require(isinstance(plan['run_id'],str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{5,90}',plan['run_id']),'run_id')
    require(set(plan['protected_sha256'])==set(PROTECTED),'protected_paths')
    for value in (plan['expected_inc_sha256'],plan['expected_patched_sha256'],*plan['protected_sha256'].values()):
        require(isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value),'plan_checksum')

def execute(plan,apply=False):
    validate(plan)
    require(not INC.is_symlink() and INC.is_file(),'include_not_regular')
    old=INC.read_bytes();current_sha=sha(old)
    details=INC.stat();identity=(details.st_uid,details.st_gid,stat.S_IMODE(details.st_mode))
    require(identity[0]==0 and identity[2]==0o644,'include_permissions_unexpected')
    require({name:sha(Path(name).read_bytes()) for name in PROTECTED}==plan['protected_sha256'],'parent_configuration_changed')
    api_before=pid('agriscan-api');master=pid('nginx')
    require(api_before>0 and master>0,'service_not_running')
    run(['nginx','-t'],'baseline_nginx_test_failed')
    report={'status':'prepared_read_only','run_id':plan['run_id'],'mode':'apply' if apply else 'inspect',
            'started_at':datetime.now(timezone.utc).isoformat(),'api_pid_before':api_before,
            'nginx_master_before':master,'nginx_restart_performed':False,'api_restart_performed':False,
            'database_modified':False,'mail_sent':False,'mutations':[]}
    if current_sha==plan['expected_patched_sha256']:
        require(ANCHOR+ADDED in old,'patched_configuration_shape')
        report.update(status='already_applied',include_sha256=current_sha)
        return report
    require(current_sha==plan['expected_inc_sha256'],'include_baseline_changed')
    candidate=patch(old)
    require(sha(candidate)==plan['expected_patched_sha256'],'candidate_checksum_mismatch')
    report.update(include_before_sha256=current_sha,include_after_sha256=sha(candidate),
                  exact_change=['proxy_http_version 1.1','proxy_request_buffering off'])
    if not apply:return report
    backup=BACKUPS/plan['run_id']
    require(backup.parent==BACKUPS and not backup.exists() and not backup.is_symlink(),'backup_path_exists')
    backup.mkdir(mode=0o700);backup.chmod(0o700)
    private_write(backup/'agriscan-locations.inc.before',old)
    private_write(backup/'agriscan-locations.inc.after',candidate)
    report['backup']=str(backup)
    published=reloaded=False
    try:
        require({name:sha(Path(name).read_bytes()) for name in PROTECTED}==plan['protected_sha256'],'parent_configuration_changed')
        publish(candidate,current_sha,identity,plan['run_id']);published=True
        report['mutations'].append('publish exact two API streaming directives with byte CAS')
        run(['nginx','-t'],'candidate_nginx_test_failed')
        old_children=children(master)
        report['new_nginx_workers']=reload_nginx(master,old_children);reloaded=True
        report['mutations'].append('systemctl reload nginx (graceful new worker generation)')
        report['health_after']=health()
        require(sha(INC.read_bytes())==plan['expected_patched_sha256'],'include_changed_after_reload')
        require({name:sha(Path(name).read_bytes()) for name in PROTECTED}==plan['protected_sha256'],'parent_configuration_changed')
        report.update(status='passed',api_pid_after=pid('agriscan-api'),nginx_master_after=pid('nginx'))
        require(report['api_pid_after']==api_before,'api_pid_changed_externally')
        require(report['nginx_master_after']==master,'nginx_master_changed_externally')
    except BaseException as error:
        report.update(status='failed',error=str(error) if isinstance(error,Refused) else type(error).__name__,rolled_back=False)
        if published:
            try:
                publish(old,plan['expected_patched_sha256'],identity,plan['run_id']+'-rollback')
                run(['nginx','-t'],'rollback_nginx_test_failed')
                # Reload even if the first reload command returned an ambiguous
                # failure: restore disk + running configuration, never restart.
                report['rollback_nginx_workers']=reload_nginx(master,children(master))
                report['rolled_back']=sha(INC.read_bytes())==current_sha
                report['rollback_health']=health()
            except BaseException as rollback_error:
                report['rollback_error']=str(rollback_error) if isinstance(rollback_error,Refused) else type(rollback_error).__name__
    report['finished_at']=datetime.now(timezone.utc).isoformat()
    private_write(backup/'report.json',json.dumps(report,ensure_ascii=False,indent=2).encode())
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-base64',required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    try:
        plan=json.loads(base64.b64decode(args.plan_base64,validate=True))
        lock=Path('/srv/agriscan/shared/nginx-streaming-fix.lock')
        # Inspection has no lock-file side effect.
        if args.apply:
            with lock.open('a') as stream:
                lock.chmod(0o600);fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
                report=execute(plan,True)
        else:report=execute(plan)
    except BaseException as error:
        report={'status':'refused','error':str(error) if isinstance(error,Refused) else type(error).__name__}
    print('RESULT '+json.dumps(report,ensure_ascii=False),flush=True)
    raise SystemExit(0 if report['status'] in {'passed','already_applied','prepared_read_only'} else 1)

if __name__=='__main__':main()
