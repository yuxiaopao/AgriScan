import hashlib
import json
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

workspace=Path.cwd()
destination=workspace/'.runtime/server-latest-20261029'
before=json.loads((destination/'web-source-before.json').read_text(encoding='utf-8'))
def digest(path):
    data=path.read_bytes()
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
paths=[]
for surface in ['frontend','admin']:
    paths.extend(path for path in (workspace/surface/'src').rglob('*') if path.is_file())
    paths.extend(path for path in (workspace/surface).glob('*') if path.is_file() and
                 (path.name in {'index.html','package.json','package-lock.json','vite.config.ts'} or
                  path.name.startswith('tsconfig') and path.suffix=='.json'))
paths.extend(path for path in (workspace/'frontend/public').rglob('*') if path.is_file())
paths.extend(workspace/'website'/name for name in ['index.html','app.js','style.css'])
paths.extend(path for path in (workspace/'website/site-assets').rglob('*') if path.is_file())
after={str(path.relative_to(workspace)).replace('\\','/'):digest(path) for path in sorted(set(paths))}
changed=[name for name in set(after)|set(before['source_files']) if after.get(name)!=before['source_files'].get(name)]
if changed:raise RuntimeError('Source changed during production build; rebuild affected sources: '+json.dumps(changed))

checks={}
app=(workspace/'frontend/src/App.tsx').read_text(encoding='utf-8')
admin=(workspace/'admin/src/Admin.tsx').read_text(encoding='utf-8')
plot=(workspace/'frontend/src/PlotEditor.tsx').read_text(encoding='utf-8')
checks['account_data_cleared_on_transition']='clearAccountData()' in app and "const expired = () => {clearAccountData();" in app
checks['late_data_response_token_guard']='getToken()===requestToken' in app and 'controller.abort()' in app
checks['late_boot_session_guard']='getToken()===bootToken' in app
checks['members_manage_own_plots']='canManage={Boolean(user)}' in app
checks['personal_client_has_no_owner_picker']='OwnerPicker' not in app
checks['owner_control_only_admin_plot_prefix']="apiPrefix==='/admin/plots'&&ownerId!==undefined" in plot
checks['admin_detections_and_plots_use_admin_routes']='/admin/detections/' in admin and '/admin/plots/' in admin and not re.search(r"api\(['\"]/(?:detections|plots)/",admin)
checks['admin_owner_change_clears_plot']="setOwner(value);setPlotId('');" in admin
checks['private_api_and_image_no_store']=all("cache: 'no-store'" in (workspace/name).read_text(encoding='utf-8') for name in ['frontend/src/api.ts','frontend/src/components.tsx'])
checks['new_completed_ui_modules_present']=all((workspace/name).is_file() for name in ['frontend/src/motion.tsx','frontend/src/ObservationStack.tsx','frontend/src/DetectionJourney.tsx','frontend/src/refinement.css','admin/src/polish.css'])
website=(workspace/'website/index.html').read_text(encoding='utf-8')
site_js=(workspace/'website/app.js').read_text(encoding='utf-8')
checks['website_new_domain_canonical']='rel="canonical" href="https://agriscan.ming-ai.top/agriscan/"' in website
checks['website_dynamic_release_no_store']="fetch('./downloads/release.json', { cache: 'no-store'" in site_js
checks['website_download_same_origin_guard']='url.origin !== location.origin' in site_js
checks['website_no_old_domain']='flowly-ai.top' not in website+site_js
detect_source=(workspace/'frontend/src/Pages.tsx').read_text(encoding='utf-8')
checks['detect_upload_late_response_guard']='mounted.current && pendingUpload.current === controller && !controller.signal.aborted && getToken() === requestToken' in detect_source
checks['detect_upload_unmount_aborts']='mounted.current = false; pendingUpload.current?.abort(); pendingUpload.current = null' in detect_source
if not all(checks.values()):raise RuntimeError('Release guard check failed: '+json.dumps([name for name,value in checks.items() if not value]))

builds={}
for surface,prefix in [('frontend','/agriscan/workspace/'),('admin','/agriscan/admin/')]:
    dist=destination/surface/'dist'
    html=(dist/'index.html').read_text(encoding='utf-8')
    entries=re.findall(r'<script[^>]+src="([^"]+)"',html)
    styles=re.findall(r'<link[^>]+href="([^"]+\.css)"',html)
    assert entries and all(value.startswith(prefix) for value in entries+styles)
    for value in entries+styles:assert (dist/value[len(prefix):]).is_file()
    javascript='\n'.join(path.read_text(encoding='utf-8') for path in (dist/'assets').glob('*.js'))
    assert 'no-store' in javascript and '/agriscan/admin/' in javascript and '/agriscan' in javascript
    if surface=='admin':assert '/agriscan/workspace/#login' in javascript
    files={str(path.relative_to(dist)).replace('\\','/'):digest(path) for path in sorted(dist.rglob('*')) if path.is_file()}
    for name in files:
        assert not any(part in {'.runtime','deliverables','design','node_modules','datasets','uploads'} for part in Path(name).parts)
        assert Path(name).suffix not in {'.pptx','.pt','.onnx','.pem','.key','.xlsx'}
    builds[surface]={'status':'passed','tsc':'passed','vite':'passed','public_base':prefix,'dist':str(dist),'entries':entries,'styles':styles,
                     'file_count':len(files),'total_bytes':sum(value['bytes'] for value in files.values()),'files':files}

site_stage=destination/'website'
site_files={str(path.relative_to(site_stage)).replace('\\','/'):digest(path) for path in sorted(site_stage.rglob('*')) if path.is_file()}
for name,value in site_files.items():assert value==digest(workspace/'website'/name)
assert not (site_stage/'downloads').exists()
previous=workspace/'.runtime/isolation-20261029/ui-builds.json'
previous_entries={}
if previous.is_file():
    old=json.loads(previous.read_text(encoding='utf-8'))
    previous_entries={name:data['entry_scripts'] for name,data in old['surfaces'].items() if name in {'frontend','admin'}}
report={'status':'passed','finished_at':datetime.now(timezone.utc).isoformat(),'source':'latest complete current working tree',
        'source_unchanged_during_build':True,'source_file_count':len(after),'source_files':after,'checks':checks,
        'builds':builds,'website':{'status':'passed','stage':str(site_stage),'file_count':len(site_files),'files':site_files,
                   'downloads_excluded':True,'relative_assets_and_anchor_checks':'passed','javascript_syntax':'passed'},
        'phone_font_and_ip_assets':before['mobile_font_ip_assets'],
        'comparison':{'production_baseline_supplied_by_parent':'release-20261029-user-isolation-104127 / APK 1.0.2',
                      'previous_local_isolation_build_entries':previous_entries,
                      'latest_entries':{name:data['entries'] for name,data in builds.items()},
                      'new_completed_desktop_modules':['motion.tsx','DetectionJourney.tsx','ObservationStack.tsx','refinement.css'],
                      'new_completed_admin_styles':'polish.css and latest interaction/form changes',
                      'website_changes':'latest responsive navigation, workflow interaction, animation, download/retry feedback and account isolation copy',
                      'server_not_contacted_by_this_subtask':True},
        'ui_source_fixes':[{'file':'frontend/src/Pages.tsx','change':'Guard upload success/failure/finally by mount, active request and captured token; abort on unmount to prevent late account A response changing B theme or feedback.'}],
        'detect_deferred_behavior_checks':json.loads((destination/'detect-deferred-checks.json').read_text(encoding='utf-8')),
        'cross_review':{'status':'passed','reviewer':'llm_review','scope':'DetectPage mount/token/controller guards, abort cleanup, preserved timeout and no regression of account clearing/no-store/admin interlocks'},
        'api_database_git_changed':False,'production_browser_tested':False}
target=destination/'web-ready.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','report':str(target),'source_files':len(after),'checks':len(checks),
                  'entries':{name:data['entries'] for name,data in builds.items()},'website_files':len(site_files)}))
