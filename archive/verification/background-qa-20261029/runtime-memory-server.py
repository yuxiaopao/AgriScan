"""Small read-only service/cgroup samples; no user records or private env values."""
import argparse,json,re,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import urlopen
class Refused(RuntimeError):pass
def run(command,timeout=15):
    result=subprocess.run(command,capture_output=True,text=True,timeout=timeout)
    if result.returncode:raise Refused('read_only_command_unavailable')
    return result.stdout
def metadata():
    lines=run(['mysql','--batch','--skip-column-names','--execute',"SELECT version_num FROM agriscan.alembic_version; SELECT version,SHA2(CONCAT_WS(CHAR(31),id,version,CAST(data AS CHAR),COALESCE(encrypted_secrets,''),COALESCE(updated_by,''),COALESCE(CAST(updated_at AS CHAR),'')),256) FROM agriscan.workspace_configuration WHERE id='workspace';"]).splitlines()
    if len(lines)!=2:raise Refused('runtime_metadata_shape')
    version,checksum=lines[1].split('\t')
    if not version.isdigit() or not re.fullmatch(r'[0-9a-f]{64}',checksum):raise Refused('runtime_checksum_shape')
    return {'schema':lines[0],'configuration_version':int(version),'configuration_canonical_sql_row_sha256':checksum}
def sample():
    properties='ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestamp,InvocationID,MemoryCurrent,MemoryPeak,MemoryMax,ControlGroup,OOMPolicy,Result,ExecMainCode,ExecMainStatus'
    state=dict(line.split('=',1) for line in run(['systemctl','show','agriscan-api','--property='+properties]).splitlines() if '=' in line)
    report={'sampled_at':datetime.now(timezone.utc).isoformat(),'release':str(Path('/srv/agriscan/current').resolve()),'service':state}
    group=state.get('ControlGroup','');base=Path('/sys/fs/cgroup').resolve();target=(base/group.lstrip('/')).resolve()
    if group.startswith('/') and target.is_relative_to(base) and target.is_dir():
        report['cgroup']={}
        for name in ('memory.current','memory.peak','memory.max'):
            path=target/name
            if path.is_file():
                value=path.read_text().strip()
                if value=='max' or value.isdigit():report['cgroup'][name]=int(value) if value.isdigit() else value
        path=target/'memory.events'
        if path.is_file():report['cgroup']['memory.events']={key:int(value) for key,value in (line.split() for line in path.read_text().splitlines()) if value.isdigit()}
    pid=state.get('MainPID','')
    if pid.isdigit() and int(pid)>0:
        status=Path('/proc')/pid/'status'
        if status.is_file():report['process_memory']={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in status.read_text().splitlines() if line.startswith(('VmRSS:','VmHWM:','VmSwap:'))}
    try:
        with urlopen('http://127.0.0.1:18000/api/health',timeout=10) as response:
            body=json.load(response);report['health']={key:body.get(key) for key in ('status','database','redis','mode','model')};report['health_http_status']=response.status
    except Exception:report['health']={'status':'unavailable'}
    return report
def execute(samples=1,interval=2):
    if not 1<=samples<=10 or not 0<=interval<=5 or (samples-1)*interval>45:raise Refused('bounded_sampling_required')
    before=metadata();rows=[]
    for index in range(samples):
        if index:time.sleep(interval)
        rows.append(sample())
    after=metadata()
    return {'status':'read_only_observed','runtime_before':before,'runtime_after':after,'runtime_configuration_unchanged':before==after,
      'samples':rows,'service_pid_unchanged':len({row['service'].get('MainPID') for row in rows})==1,
      'service_nrestarts_unchanged':len({row['service'].get('NRestarts') for row in rows})==1,
      'notes':['MemoryPeak/memory.peak is cumulative for the current service invocation/cgroup; compare a before and after sample.','memory.events counters include oom/oom_kill when supported. No counters, services or limits are reset.'],
      'production_mutations':False,'user_rows_read':False,'private_environment_read':False}
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--samples',type=int,default=1);parser.add_argument('--interval',type=float,default=2);args=parser.parse_args()
    try:report=execute(args.samples,args.interval)
    except Refused as error:report={'status':'refused','reason':str(error),'production_mutations':False}
    except Exception:report={'status':'refused','reason':'read_only_monitor_unavailable','production_mutations':False}
    print('RESULT '+json.dumps(report));return 0 if report['status']=='read_only_observed' else 1
if __name__=='__main__':raise SystemExit(main())
