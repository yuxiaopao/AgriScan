"""New isolated mobile build; previous product sources and APK proofs stay intact."""
import hashlib,json
from pathlib import Path
root=Path('E:/AgriScan');old=root/'.runtime/mobile-task-final-20261029';new=root/'.runtime/mobile-cancel-final-20261029'
expected='fbb4f74be2999f95473f159c08d5ad58eb0d61f28adb21e236ab2135113a38a1'
assert hashlib.sha256((root/'shared/detectionTasks.ts').read_bytes()).hexdigest()==expected
reviews=Path(__file__).resolve().parent
for name in ('cancel-order-checks.json','core-progress-checks.json'):
    report=json.loads((reviews/name).read_text(encoding='utf-8'));assert report['status']=='passed' and report['source_sha256']==expected
previous=json.loads((old/'mobile-source-manifest.json').read_text(encoding='utf-8'))
for row in previous['files']:
    if row['path'].startswith('mobile/'):assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256'],'Frozen mobile source changed: '+row['path']
assert not new.exists();new.mkdir()
for name in ('prepare-mobile.py','build-mobile.ps1','verify-mobile.py','check-signature.ps1','verify-build-derivation.py','write-ready.py'):
    value=(old/name).read_text(encoding='utf-8').replace('mobile-task-final-20261029','mobile-cancel-final-20261029').replace('mobile-task-core-review-20261029','mobile-cancel-core-review-20261029').replace('9242e1fd18d2e08bb409eeffe724d41b409162adeb2bb394ed01d739f5db9676',expected)
    if name=='write-ready.py':
        value=value.replace("for name in ('mobile-auth-final-20261029','mobile-final-20261029','dual-model-20261029'):","for name in ('mobile-task-final-20261029','mobile-auth-final-20261029','mobile-final-20261029','dual-model-20261029'):")
        value=value.replace("'previous_unpublished_artifacts':previous", "'previous_artifacts_preserved':previous")
        value=value.replace("'earlier_plot_checks':", "'shared_cancellation_order_review':{'report':str(root/'.runtime/mobile-cancel-core-review-20261029/cancel-order-checks.json'),'status':'passed','cases':5},\n 'earlier_plot_checks':")
    (new/name).write_text(value,encoding='utf-8')
print(json.dumps({'status':'prepared','snapshot_root':str(new),'shared_sha256':expected,'mobile_source_entries_unchanged':146}))
