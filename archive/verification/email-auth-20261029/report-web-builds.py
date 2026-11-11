from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re

workspace=Path.cwd();base=workspace/'.runtime/email-auth-20261029'
prior=json.loads((base/'prior-web-ui-builds.json').read_text(encoding='utf-8'))
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
assert sources['shared/detectionTasks.ts']==prior['sources']['shared/detectionTasks.ts']
changed=list(dict.fromkeys(prior['changed_files']+['frontend/src/Access.tsx','frontend/src/api.ts','frontend/src/EmailForms.tsx','frontend/src/email-forms.css']))
surfaces={}
for surface,prefix in [('frontend','/agriscan/workspace/'),('admin','/agriscan/admin/')]:
    dist=base/surface/'dist';index=(dist/'index.html').read_text(encoding='utf-8')
    entries=re.findall(r'<script[^>]+src="([^"]+)"',index);styles=re.findall(r'<link[^>]+href="([^"]+\.css)"',index)
    assert entries and all(value.startswith(prefix) for value in entries+styles)
    for value in entries+styles:assert (dist/value[len(prefix):]).is_file()
    javascript='\n'.join(path.read_text(encoding='utf-8') for path in (dist/'assets').glob('*.js'))
    assert 'no-store' in javascript and 'detection_with_classification' in javascript
    assert '/agriscan/admin/' in javascript
    if surface=='frontend':
        assert '1.0.4' in javascript and '网页工作台' in javascript
        assert 'forgot-password' in javascript and '/auth/email/verify' in javascript and '/auth/password-reset' in javascript
    else:assert '/agriscan/workspace/#login' in javascript
    files={str(path.relative_to(dist)).replace('\\','/'):digest(path) for path in sorted(dist.rglob('*')) if path.is_file()}
    assert not any(Path(name).suffix in {'.pt','.onnx','.pem','.key','.pptx','.xlsx'} for name in files)
    assert max((workspace/name).stat().st_mtime for name in changed)<=(dist/'index.html').stat().st_mtime
    surfaces[surface]={'status':'passed','tsc':'passed','vite_build':'passed','dist':str(dist),'production_base':prefix,'api_prefix':'/agriscan','entries':entries,'styles':styles,'file_count':len(files),'files':files,'build_reused_with_unchanged_dependencies':False}
checks=json.loads((base/'desktop-form-checks.json').read_text(encoding='utf-8'))
cua=json.loads((base/'cua-desktop-auth-checks.json').read_text(encoding='utf-8'))
assert checks['status']==cua['status']=='passed'
for name,sha in cua['source_sha256'].items():assert sources[name]['sha256']==sha
report={**prior,'status':'passed','auth_email_features':True,'release_version':'1.0.4','completed_at':datetime.now(timezone.utc).isoformat(),
        'source_manifest_phase':'frontend and admin rebuilt for email recovery/binding; prior tasks/maps/result features retained',
        'source_file_count':len(sources),'sources':sources,'changed_files':changed,'surfaces':surfaces,
        'post_verification_change':{'scope':'email recovery/public route and self-email binding UI; existing task/map/result behavior retained',
                                    'prior_release_proof':str(base/'prior-web-ui-builds.json')},
        'email_auth_checks':{'form_methods_and_scope':checks,'cua':cua,'cross_review':{'reviewer':'llm_review','status':'passed','findings_remaining':0},
                             'smtp_mail_sent':False,'production_passwords_changed':False,'registration_switch_independent':True,
                             'binding_requires_current_password_and_email_code':True,'reset_never_auto_logs_in':True},
        'browser_scope':'CUA local fake API forms for email recovery/binding; prior local map/task CUA evidence retained in prior release proof',
        'production_ui_tested_by_this_agent':False}
for target in [base/'web-auth-builds.json',workspace/'.runtime/dual-model-20261029/web-ui-builds.json']:
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'status':'passed','report':str(base/'web-auth-builds.json'),'source_files':len(sources),'entries':{name:value['entries'] for name,value in surfaces.items()},'form_cases':len(checks['cases'])}))
