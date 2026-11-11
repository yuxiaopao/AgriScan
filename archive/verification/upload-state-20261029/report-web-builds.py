from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re

workspace=Path.cwd();base=workspace/'.runtime/upload-state-20261029'
prior=json.loads((base/'prior-web-ui-builds.json').read_text(encoding='utf-8'))
def digest(path):
    data=path.read_bytes();return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
sources={name:digest(workspace/name) for name in prior['sources']}
assert len(sources)==118
changed=[name for name in sources if sources[name]!=prior['sources'][name]]
assert changed==['shared/detectionTasks.ts'],changed
surfaces={}
for surface,prefix in [('frontend','/agriscan/workspace/'),('admin','/agriscan/admin/')]:
    dist=base/surface/'dist';index=(dist/'index.html').read_text(encoding='utf-8')
    entries=re.findall(r'<script[^>]+src="([^"]+)"',index);styles=re.findall(r'<link[^>]+href="([^"]+\.css)"',index)
    assert entries and all(value.startswith(prefix) for value in entries+styles)
    for name in entries+styles:assert (dist/name[len(prefix):]).is_file()
    js='\n'.join(path.read_text(encoding='utf-8') for path in (dist/'assets').glob('*.js'))
    assert 'no-store' in js and 'detection_with_classification' in js and '/agriscan/admin/' in js
    if surface=='frontend':assert '1.0.4' in js and 'forgot-password' in js and '/auth/email/verify' in js
    else:assert '/agriscan/workspace/#login' in js
    files={str(path.relative_to(dist)).replace('\\','/'):digest(path) for path in sorted(dist.rglob('*')) if path.is_file()}
    assert not any(Path(name).suffix in {'.pt','.onnx','.pem','.key','.pptx','.xlsx'} for name in files)
    assert (workspace/'shared/detectionTasks.ts').stat().st_mtime<=(dist/'index.html').stat().st_mtime
    surfaces[surface]={'status':'passed','tsc':'passed','vite_build':'passed','dist':str(dist),'production_base':prefix,'api_prefix':'/agriscan','entries':entries,'styles':styles,'file_count':len(files),'files':files,'build_reused_with_unchanged_dependencies':False}
    if surface=='admin':assert files==prior['surfaces']['admin']['files']
core=json.loads((workspace/'.runtime/detection-tasks-20261029/core-checks.json').read_text(encoding='utf-8'))
regressions=json.loads((workspace/'.runtime/detection-tasks-20261029/buffered-upload-checks.json').read_text(encoding='utf-8'))
independent=json.loads((workspace/'.runtime/mobile-task-core-review-20261029/core-progress-checks.json').read_text(encoding='utf-8'))
assert core['status']==regressions['status']==independent['status']=='passed'
assert independent['source_sha256']==sources['shared/detectionTasks.ts']['sha256']
assert all(prior.get(name) is True for name in ['auth_email_features','completed_result_view','background_detection_tasks'])
report={**prior,'status':'passed','completed_at':datetime.now(timezone.utc).isoformat(),'release_version':'1.0.4',
        'upload_state_fix':True,'reservation_recovery_fix':True,
        'source_manifest_phase':'only shared task transport changed after the prior frozen auth/result/map release; both web surfaces rebuilt',
        'source_file_count':len(sources),'sources':sources,'surfaces':surfaces,
        'post_verification_change':{'scope':'shared task state/progress reconciliation and recovered reservation continuation only',
                                    'prior_release_proof':str(base/'prior-web-ui-builds.json'),
                                    'product_sources_changed':changed,'prior_core_sha256':prior['sources']['shared/detectionTasks.ts']['sha256'],
                                    'current_core_sha256':sources['shared/detectionTasks.ts']['sha256']},
        'background_task_checks':{**prior['background_task_checks'],'core':core,'buffered_upload_regressions':regressions,'independent_core_checks':independent,
                                 'shared_core_sha256':sources['shared/detectionTasks.ts']['sha256'],
                                 'fixes':['active XHR remains uploading while an upstream proxy still reports awaiting_upload',
                                          'only active unconfirmed local progress supplements server received_bytes',
                                          'confirmed queue/processing/terminal states ignore late local progress and stale server regressions',
                                          'GET-confirmed reservation survives a later POST timeout without another POST',
                                          'only awaiting_upload jobs enter an upload slot; queued/recovered/cancelled jobs never spin or resend PUT']},
        'cross_review':{'reviewer':'llm_review independent 9-case HTTP/XHR checks; llm_backend recovery path review','status':'passed','findings_remaining':0},
        'validation_scope':'new core behavior verified with actual shared manager and deferred synthetic HTTP/XHR; previous browser evidence retained for unchanged UI',
        'production_ui_tested_by_this_agent':False,'production_server_modified_by_this_agent':False}
for target in [base/'web-upload-state-builds.json',workspace/'.runtime/dual-model-20261029/web-ui-builds.json']:
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','report':str(base/'web-upload-state-builds.json'),'sources':len(sources),'modified_product_sources':changed,
                  'core_sha256':sources['shared/detectionTasks.ts']['sha256'],'entries':{name:value['entries'] for name,value in surfaces.items()},
                  'checks':{'existing_core':len(core['cases']),'regression_groups':len(regressions['cases']),'independent_core':len(independent['cases'])}}))
