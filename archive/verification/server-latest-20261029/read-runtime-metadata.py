"""Only service/release/schema/checksum metadata; no credentials or user rows."""
import argparse,json,subprocess
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--output',default='readonly-runtime-before.json')
args=parser.parse_args()
folder=Path(__file__).resolve().parent
target=folder/args.output
assert target.parent==folder and target.suffix=='.json'
source=r'''
import json,subprocess
from pathlib import Path
from urllib.request import urlopen
from datetime import datetime,timezone
report={'checked_at':datetime.now(timezone.utc).isoformat(),'release':str(Path('/srv/agriscan/current').resolve())}
state=subprocess.run(['systemctl','show','agriscan-api','--property=ActiveState,SubState,MainPID,NRestarts,ExecMainStartTimestamp'],capture_output=True,text=True,check=True)
report['api']=dict(line.split('=',1) for line in state.stdout.splitlines() if '=' in line)
statement="SELECT version_num FROM agriscan.alembic_version; SELECT version,SHA2(CONCAT_WS(CHAR(31),id,version,CAST(data AS CHAR),COALESCE(encrypted_secrets,''),COALESCE(updated_by,''),COALESCE(CAST(updated_at AS CHAR),'')),256) FROM agriscan.workspace_configuration WHERE id='workspace';"
result=subprocess.run(['mysql','--batch','--skip-column-names','--execute',statement],capture_output=True,text=True,check=True,timeout=15)
lines=result.stdout.splitlines()
assert len(lines)==2
version,digest=lines[1].split('\t')
report['schema']=lines[0]
report['configuration']={'version':int(version),'row_sha256':digest,'method':'MySQL SHA2 of canonical field concatenation; no data or secret value returned'}
with urlopen('http://127.0.0.1:18000/api/health',timeout=15) as response:report['health']=json.load(response)
print(json.dumps(report))
'''
result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','tencent-server','python3 -'],
                       input=source,text=True,capture_output=True,timeout=45)
if result.returncode:raise SystemExit('Read-only metadata query failed; private stderr was not printed.')
report=json.loads(result.stdout)
target.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
