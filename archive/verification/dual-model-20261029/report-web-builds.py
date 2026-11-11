import hashlib
import json
from pathlib import Path
import re
from datetime import datetime, timezone

workspace=Path.cwd();report_root=workspace/'.runtime/dual-model-20261029';build_root=workspace/'.runtime/detection-tasks-20261029'
changed=['frontend/src/types.ts','frontend/src/PredictionScores.tsx','frontend/src/ModelVerification.tsx',
         'frontend/src/RunningModels.tsx','frontend/src/predictionFormat.ts','frontend/src/model-verification.css',
         'frontend/src/Pages.tsx','frontend/src/FloatingAssistant.tsx','frontend/src/Integrations.tsx','admin/src/Admin.tsx',
         'frontend/src/App.tsx','frontend/src/DetectionJourney.tsx','frontend/src/DetectResultView.tsx','frontend/src/detect-result.css',
         'frontend/src/mapTiles.ts','frontend/src/MapTileFeedback.tsx','frontend/src/PlotLocationPicker.tsx',
         'frontend/src/PlotCoverCarousel.tsx','frontend/src/plot-editor.css',
         'frontend/src/DetectionTasks.tsx','frontend/src/detection-tasks.css','shared/detectionTasks.ts',
         'frontend/.env.example','scripts/build-web.ps1']
def digest(path):
    data=path.read_bytes();return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
paths=[]
for surface in ['frontend','admin']:
    paths.extend(path for path in (workspace/surface/'src').rglob('*') if path.is_file())
    paths.extend(path for path in (workspace/surface).glob('*') if path.is_file() and
                 (path.name in {'index.html','package.json','package-lock.json','vite.config.ts'} or
                  path.name.startswith('tsconfig') and path.suffix=='.json'))
paths.extend(path for path in (workspace/'frontend/public').rglob('*') if path.is_file())
paths.extend(path for path in (workspace/'shared').rglob('*.ts') if path.is_file())
paths.extend([workspace/'frontend/.env.example',workspace/'scripts/build-web.ps1'])
sources={str(path.relative_to(workspace)).replace('\\','/'):digest(path) for path in sorted(set(paths))}
before_report=json.loads((build_root/'version-label/web-ui-builds.before.json').read_text(encoding='utf-8'))
before_pages=build_root/'version-label/Pages-before.tsx'
old_version='<dd>1.0.0 · 基础版</dd>'
new_version="<dd>{import.meta.env.VITE_RELEASE_VERSION ? `${import.meta.env.VITE_RELEASE_VERSION} · 网页工作台` : '开发版本 · 网页工作台'}</dd>"
current_pages=(workspace/'frontend/src/Pages.tsx').read_text(encoding='utf-8')
assert current_pages.count(new_version)==1 and current_pages.replace(new_version,old_version)==before_pages.read_text(encoding='utf-8')
surfaces={}
for surface,prefix in [('frontend','/agriscan/workspace/'),('admin','/agriscan/admin/')]:
    dist=build_root/surface/'dist';index=(dist/'index.html').read_text(encoding='utf-8')
    entries=re.findall(r'<script[^>]+src="([^"]+)"',index)
    styles=re.findall(r'<link[^>]+href="([^"]+\.css)"',index)
    assert entries and all(value.startswith(prefix) for value in entries+styles)
    for value in entries+styles:assert (dist/value[len(prefix):]).is_file()
    javascript='\n'.join(path.read_text(encoding='utf-8') for path in (dist/'assets').glob('*.js'))
    assert 'detection_with_classification' in javascript and 'no-store' in javascript
    assert '/agriscan/admin/' in javascript
    if surface=='admin':assert '/agriscan/workspace/#login' in javascript
    files={str(path.relative_to(dist)).replace('\\','/'):digest(path) for path in sorted(dist.rglob('*')) if path.is_file()}
    assert not any(Path(name).suffix in {'.pt','.onnx','.pem','.key','.pptx','.xlsx'} for name in files)
    relevant=changed if surface=='frontend' else [name for name in changed if name not in {'shared/detectionTasks.ts','frontend/src/Pages.tsx','frontend/.env.example','scripts/build-web.ps1'}]
    assert max((workspace/name).stat().st_mtime for name in relevant)<=(dist/'index.html').stat().st_mtime
    surfaces[surface]={'status':'passed','tsc':'passed','vite_build':'passed','dist':str(dist),'production_base':prefix,
                       'api_prefix':'/agriscan','entries':entries,'styles':styles,'file_count':len(files),'files':files,
                       'build_reused_with_unchanged_dependencies':surface=='admin'}
    if surface=='admin':assert files==before_report['surfaces']['admin']['files']
    else:assert '1.0.4' in javascript and '网页工作台' in javascript
checks=json.loads((report_root/'web-contract-checks.json').read_text(encoding='utf-8'))
assert checks['status']=='passed'
result_checks=json.loads((report_root/'completed-result-checks.json').read_text(encoding='utf-8'))
assert result_checks['status']=='passed'
map_cua_checks=json.loads((workspace/'.runtime/map-20261029/cua-map-checks.json').read_text(encoding='utf-8'))
map_event_checks=json.loads((workspace/'.runtime/map-20261029/tile-event-checks.json').read_text(encoding='utf-8'))
assert map_cua_checks['status']==map_event_checks['status']=='passed'
for name,sha in map_cua_checks['source_sha256'].items():assert sources[name]['sha256']==sha
task_cua_checks=json.loads((build_root/'cua-desktop-checks.json').read_text(encoding='utf-8'))
task_core_checks=json.loads((build_root/'core-checks.json').read_text(encoding='utf-8'))
assert task_cua_checks['status']==task_core_checks['status']=='passed'
for name,sha in task_cua_checks['source_sha256'].items():
    assert (digest(before_pages)['sha256'] if name=='frontend/src/Pages.tsx' else sources[name]['sha256'])==sha
report={'status':'passed','release_version':'1.0.4','completed_result_view':True,'background_detection_tasks':True,'completed_at':datetime.now(timezone.utc).isoformat(),'source':'latest complete working tree',
        'source_manifest_phase':'frontend rebuilt with release version 1.0.4; admin reused with unchanged dependencies and artifact hashes',
        'post_verification_change':{'scope':'SettingsPage version label only; production version injected by scripts/build-web.ps1',
                                    'previous_pages_sha256':digest(before_pages)['sha256'],'current_pages_sha256':sources['frontend/src/Pages.tsx']['sha256'],
                                    'behavior_tests_reused':True,'frontend_tsc_vite':'passed'},
        'source_file_count':len(sources),'sources':sources,'changed_files':changed,'surfaces':surfaces,
        'contract':{'snapshot_verification':'record.prediction_model.verification','running_components':'model.active.components',
                    'scope':'whole_image','primary_detection_result_unchanged':True,'independent_scores':True,'scores_averaged':False,
                    'historical_snapshot_without_verification_supported':True,'empty_main_candidates_supported':True,
                    'empty_uploaded_registry_does_not_hide_running_components':True,
                    'states':['两模型一致','结果不一致，建议复核','需人工复核','分类复核暂不可用']},
        'render_contract_checks':checks,'completed_result_checks':result_checks,
        'result_view':{'success_enters_dedicated_result_view':True,'upload_form_collapsed':True,
                       'cancelled_picker_keeps_result':True,'failed_upload_remains_retryable':True,
                       'awaiting_model_is_saved_sample_only':True,'background_assistant_never_opens_or_focuses':True,
                       'explicit_advice_reuses_cache_or_starts_one_missing_analysis':True,
                       'analysis_ref_blocks_same_render_stale_busy_race':True,'queue_clears_old_pending_advice':True,
                       'exact_token_scopes_widget_and_cache':True},
        'cross_review':{'reviewer':'llm_review (result/session/map), llm_backend (task transport)','status':'passed','p1_p2_findings_remaining':0},
        'map_checks':{'cua':map_cua_checks,'events':map_event_checks},
        'background_task_checks':{'cua':task_cua_checks,'core':task_core_checks,
                                 'lifetime':'current App account/session; continues across routes; no guarantee after refresh/close/logout',
                                 'shared_core_sha256':sources['shared/detectionTasks.ts']['sha256'],
                                 'upload_concurrency':2,'transport':'XHR progress plus GET polling','repeated_reservation_on_lost_response':False},
        'inherited_privacy_guards':{'account_switch_clearing':True,'late_upload_mount_token_guard':True,'private_no_store':True},
        'browser_ui_tested':True,'browser_scope':'local map harness and full desktop App with isolated fixture API through CUA; actual handlers/React DOM also checked',
        'production_ui_tested_by_this_agent':False,'native_app_changed_by_this_agent':False,'backend_server_database_git_changed':False,
        'skill_read':'C:/Users/18984/.codex/skills/landing-page-design/SKILL.md'}
target=report_root/'web-ui-builds.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','report':str(target),'source_files':len(sources),'changed_files':len(changed),
                  'entries':{name:value['entries'] for name,value in surfaces.items()},'render_cases':len(checks['cases'])}))
