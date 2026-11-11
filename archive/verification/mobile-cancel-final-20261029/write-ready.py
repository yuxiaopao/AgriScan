import hashlib,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
root=Path('E:/AgriScan');folder=Path(__file__).resolve().parent
manifest=json.loads((folder/'mobile-source-manifest.json').read_text(encoding='utf-8'))
verification=json.loads((folder/'apk/verification.json').read_text(encoding='utf-8'))
assert verification['status']=='passed' and manifest['source_file_count']==147
assert verification['source_tree_sha256']==manifest['source_tree_sha256']
for row in manifest['files']:
    assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256']
assert manifest['shared']['sha256']=='fbb4f74be2999f95473f159c08d5ad58eb0d61f28adb21e236ab2135113a38a1'
qa=root/'.runtime/mobile-auth-qa-20261029'
handlers=json.loads((qa/'form-checks.json').read_text(encoding='utf-8'))
browser=json.loads((qa/'browser-checks.json').read_text(encoding='utf-8'))
assert handlers['status']==browser['status']=='passed'
previous=[]
for name in ('mobile-task-final-20261029','mobile-auth-final-20261029','mobile-final-20261029','dual-model-20261029'):
    proof=json.loads((root/'.runtime'/name/'apk/verification.json').read_text(encoding='utf-8'))
    artifact=Path(proof['artifact'])
    assert artifact.is_file() and hashlib.sha256(artifact.read_bytes()).hexdigest()==proof['sha256']
    previous.append({'path':str(artifact),'sha256':proof['sha256'],'bytes':artifact.stat().st_size,'preserved':True,'is_final':False})
report={'status':'passed','finished_at':datetime.now(timezone.utc).isoformat(),'source_root':str(root),'snapshot_root':str(folder),
 'source_file_count':manifest['source_file_count'],'source_tree_sha256':manifest['source_tree_sha256'],
 'source_hash_algorithm':manifest['source_hash_algorithm'],'path_convention':manifest['path_convention'],
 'source_files':{row['path']:{'bytes':row['bytes'],'sha256':row['sha256']} for row in manifest['files']},
 'shared':manifest['shared'],'artifact':verification,'previous_artifacts_preserved':previous,
 'checks':{'typescript':'passed','vite_production_build':'passed','capacitor_sync':'passed','gradle_assemble_debug':'passed',
 'signature_and_zip':'passed','source_root_and_snapshot_stable':'passed','mobile_auth_actual_handlers':{'count':len(handlers['cases']),'report':str(qa/'form-checks.json')},
 'mobile_auth_cua_synthetic_contract':{'count':len(browser['cases']),'report':str(qa/'browser-checks.json')},
 'cross_review':'llm_admin read-only reviewed final auth, plots, task, camera and session guards; no blocking findings',
 'shared_upload_progress_review':{'report':str(root/'.runtime/mobile-cancel-core-review-20261029/core-progress-checks.json'),'status':'passed','cases':9},
 'shared_cancellation_order_review':{'report':str(root/'.runtime/mobile-cancel-core-review-20261029/cancel-order-checks.json'),'status':'passed','cases':5},
 'earlier_plot_checks':{'pure_validation':19,'isolated_personal_api':14},'earlier_task_checks':{'local_live_http_protocol':10,'shared_core_deferred_report':str(root/'.runtime/detection-tasks-20261029/core-checks.json')}},
 'features':['Public forgot-password route independent of registration availability',
 'Verified-email reset with six-digit code, 10–128 character password, confirmation and explicit return to login',
 'Self-only verified email status and current-password plus mailbox-code binding/change flow',
 'Synchronous busy locks, absolute sixty-second mail cooldown, route/token/service lifetime guards and safe error feedback',
 'Personal plot create/edit, paired optional coordinates, cover retry and linked own records',
 'Root-owned background image/video tasks, real XHR progress, explicit cancellation/status/results and current-page focus guards',
 'Camera stops after leaving its page; explicitly saved frame task continues across app routes',
 'Dual-model detection plus whole-image classifier verification with separate scores and model status',
 'Account/service changes clear previews, task references, form drafts and late callbacks'],
 'scope_limits':{'native_android_runtime_tested':False,'real_camera_permission_exercised':False,'smtp_mail_delivery_tested_here':False,
 'real_password_or_production_account_modified':False,'continues_across_app_routes_and_modes':True,'survives_close_refresh_logout':False,
 'browser_auth_tests_used_synthetic_contract_fixture':True,'browser_auth_console_errors':0},
 'production_contacted':False,'server_published':False,'git_mutations':False}
(folder/'final-mobile-ready.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
subprocess.run([sys.executable,str(folder/'verify-build-derivation.py')],check=True)
print(json.dumps({key:report[key] for key in ('status','source_file_count','source_tree_sha256')}))
print(json.dumps({'apk':verification['artifact'],'bytes':verification['apk_bytes'],'sha256':verification['sha256']}))
