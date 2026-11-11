"""Prepare a new clean mobile snapshot only after the reviewed shared core SHA freezes."""
import argparse,hashlib,json,re
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--core-sha256',required=True);args=parser.parse_args()
assert re.fullmatch(r'[0-9a-f]{64}',args.core_sha256)
root=Path('E:/AgriScan');old=root/'.runtime/mobile-auth-final-20261029';new=root/'.runtime/mobile-task-final-20261029'
assert hashlib.sha256((root/'shared/detectionTasks.ts').read_bytes()).hexdigest()==args.core_sha256
review=json.loads((Path(__file__).parent/'core-progress-checks.json').read_text(encoding='utf-8'))
assert review['status']=='passed' and review['source_sha256']==args.core_sha256
assert not new.exists(),'Preserve prior snapshots and outputs.'
new.mkdir()
for name in ('prepare-mobile.py','build-mobile.ps1','verify-mobile.py','check-signature.ps1','verify-build-derivation.py','write-ready.py'):
    value=(old/name).read_text(encoding='utf-8').replace('mobile-auth-final-20261029','mobile-task-final-20261029').replace('ac3e42c703eedc4a94b82aa8141a0fab4415805bdcd1f2b0d3a28c7a6b298a5e',args.core_sha256)
    if name=='write-ready.py':
        value=value.replace("for name in ('mobile-final-20261029','dual-model-20261029'):","for name in ('mobile-auth-final-20261029','mobile-final-20261029','dual-model-20261029'):")
        value=value.replace("'earlier_plot_checks':", "'shared_upload_progress_review':{'report':str(root/'.runtime/mobile-task-core-review-20261029/core-progress-checks.json'),'status':'passed','cases':"+str(len(review['cases']))+"},\n 'earlier_plot_checks':")
    (new/name).write_text(value,encoding='utf-8')
print(json.dumps({'status':'prepared','new_snapshot_root':str(new),'expected_shared_sha256':args.core_sha256}))
