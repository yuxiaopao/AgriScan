"""Reviewed dual-model release activation; never imports or prewarms ONNX itself."""
import argparse
import base64
from datetime import datetime, timezone
import fcntl
import grp
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import tarfile
import time
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from dotenv import dotenv_values

ROOT = Path('/srv/agriscan')
ENV = ROOT / 'shared/production.env'
ENV_KEY = 'CLASSIFICATION_MODEL_MANIFEST'
ENV_VALUE = '/srv/agriscan/current/model-classification/manifest.json'
ENV_PATTERN = re.compile(rb'^\s*(?:export\s+)?CLASSIFICATION_MODEL_MANIFEST\s*=')
GRACEFUL = Path('/etc/systemd/system/agriscan-api.service.d/agriscan-graceful.conf')
GRACEFUL_BYTES = b'[Service]\nTimeoutStopSec=180s\n'
HASH = re.compile(r'[0-9a-f]{64}')
PUBLIC = 'https://agriscan.ming-ai.top/agriscan/'


class ActivationError(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise ActivationError(code)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def command(args, code, timeout=30):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, code)
    return result.stdout.strip()


def metadata():
    statement = ("SELECT version_num FROM agriscan.alembic_version; "
        "SELECT version,SHA2(CONCAT_WS(CHAR(31),id,version,CAST(data AS CHAR),COALESCE(encrypted_secrets,''),"
        "COALESCE(updated_by,''),COALESCE(CAST(updated_at AS CHAR),'')),256) "
        "FROM agriscan.workspace_configuration WHERE id='workspace';")
    lines = command(['mysql','--batch','--skip-column-names','--execute',statement], 'runtime_metadata_failed',15).splitlines()
    require(len(lines)==2,'runtime_metadata_shape')
    version, checksum = lines[1].split('\t')
    require(bool(HASH.fullmatch(checksum)),'runtime_metadata_checksum_shape')
    return {'schema':lines[0],'configuration_version':int(version),'configuration_sha256':checksum}


def service():
    names = 'MainPID,NRestarts,ActiveState,SubState,TimeoutStartUSec,TimeoutStopUSec,MemoryCurrent,MemoryPeak,MemoryMax,MemorySwapCurrent,CPUUsageNSec'
    text = command(['systemctl','show','agriscan-api','--property='+names],'service_metadata_failed')
    return dict(line.split('=',1) for line in text.splitlines() if '=' in line)


def seconds(value):
    if value == 'infinity':
        return float('inf')
    units = {'us':0.000001,'ms':0.001,'s':1,'min':60,'h':3600,'d':86400}
    tokens = re.findall(r'(\d+(?:\.\d+)?)\s*(us|ms|min|s|h|d)',value)
    require(bool(tokens),'unrecognized_systemd_duration')
    return sum(float(number)*units[unit] for number,unit in tokens)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


HTTP = build_opener(ProxyHandler({}),NoRedirect())


def request(url, *, data=None, token=None, timeout=20):
    headers = {'Cache-Control':'no-cache'}
    if data is not None:
        headers['Content-Type']='application/json'
    if token:
        require(url.startswith('http://127.0.0.1:18000/api/'),'authentication_destination_rejected')
        headers['Authorization']='Bearer '+token
    body = json.dumps(data).encode() if data is not None else None
    with HTTP.open(Request(url,data=body,headers=headers),timeout=timeout) as response:
        require(response.status==200,'unexpected_http_status')
        content=response.read(2*1024*1024+1)
        require(len(content)<=2*1024*1024,'http_reply_too_large')
        return content


def public_request(relative):
    for attempt in range(3):
        try:
            return request(PUBLIC+relative,timeout=25)
        except Exception:
            if attempt==2:
                raise ActivationError('public_http_check_failed') from None
            time.sleep(1)


def health(wait=150):
    deadline=time.monotonic()+wait
    while True:
        try:
            result=json.loads(request('http://127.0.0.1:18000/api/health',timeout=4))
            if result=={'status':'ok','database':'connected','redis':'connected','mode':'production','model':'ready'}:
                return result
        except Exception:
            pass
        if time.monotonic()>=deadline:
            raise ActivationError('api_health_deadline')
        time.sleep(1)


def path_name(value):
    require(isinstance(value,str) and value and '\\' not in value,'invalid_payload_path')
    path=PurePosixPath(value)
    require(not path.is_absolute() and all(part not in {'.','..'} for part in path.parts)
            and path.as_posix()==value,'invalid_payload_path')
    return value


def allowed(value, manifest_name, external=False):
    path_name(value)
    if value in {'release-info.json',manifest_name} or value.startswith(('backend/app/','public/')):
        return True
    return external and value in {'model-classification/model.onnx','model-classification/manifest.json',
                                  'model/model.onnx','model/manifest.json'}


def members(archive, manifest_name, classifier=False):
    entries=archive.getmembers()
    seen=set()
    total=0
    for entry in entries:
        name=path_name(entry.name)
        require(entry.isfile() and not entry.issparse() and name not in seen,'non_regular_or_duplicate_archive_member')
        require(0<=entry.size<=128*1024*1024,'archive_member_size_limit')
        if classifier:
            require(name in {'model-classification/model.onnx','model-classification/manifest.json'},'classifier_archive_scope')
        else:
            require(allowed(name,manifest_name) and name!='public/downloads/agriscan-test.apk','patch_archive_scope')
        seen.add(name)
        total+=entry.size
    require(len(entries)<=10000 and total<=600*1024*1024,'archive_total_limit')
    if classifier:
        require(seen=={'model-classification/model.onnx','model-classification/manifest.json'},'classifier_archive_incomplete')
    return entries


def target_file(release,name):
    target=release/name
    require(target.resolve().is_relative_to(release.resolve()),'payload_escapes_release')
    for ancestor in (target,*target.parents):
        if ancestor==release.parent:
            break
        require(not ancestor.is_symlink(),'payload_symlink_rejected')
    return target


def extract_regular(archive,entries,release):
    for entry in entries:
        target=target_file(release,entry.name)
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
        with archive.extractfile(entry) as source, target.open('wb') as output:
            shutil.copyfileobj(source,output,1024*1024)
        target.chmod(0o644)


def env_lines(raw):
    return [line for line in raw.splitlines(keepends=True) if ENV_PATTERN.match(line)]


def without_classification(raw):
    return b''.join(line for line in raw.splitlines(keepends=True) if not ENV_PATTERN.match(line))


def env_value(raw):
    require(len(env_lines(raw))<=1,'duplicate_classification_environment_key')
    return dotenv_values(stream=io.StringIO(raw.decode()),interpolate=False).get(ENV_KEY)


def patch_env(raw,new_line):
    lines=raw.splitlines(keepends=True)
    found=any(ENV_PATTERN.match(line) for line in lines)
    require(not raw or raw.endswith(b'\n'),'environment_missing_final_line_boundary')
    if found:
        return b''.join(new_line if ENV_PATTERN.match(line) else line for line in lines)
    return raw+new_line


def atomic_env(raw,expected_sha,identity,tag):
    require(sha(ENV)==expected_sha,'environment_concurrent_change')
    current_stat=ENV.stat()
    require((current_stat.st_uid,current_stat.st_gid,stat.S_IMODE(current_stat.st_mode))==identity,'environment_identity_changed')
    temporary=ENV.with_name('.production.'+tag+'.next')
    require(not temporary.exists() and not temporary.is_symlink(),'environment_temporary_exists')
    try:
        with temporary.open('xb') as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.chown(temporary,identity[0],identity[1])
        temporary.chmod(identity[2])
        require(sha(ENV)==expected_sha,'environment_concurrent_change')
        os.replace(temporary,ENV)
    finally:
        temporary.unlink(missing_ok=True)


def pointer(current,expected,target,tag):
    require(current.is_symlink() and current.resolve()==expected,'current_pointer_concurrent_change')
    temporary=ROOT/('.current.'+tag)
    require(not temporary.exists() and not temporary.is_symlink(),'pointer_temporary_exists')
    try:
        temporary.symlink_to(target,target_is_directory=True)
        require(current.resolve()==expected,'current_pointer_concurrent_change')
        os.replace(temporary,current)
    finally:
        temporary.unlink(missing_ok=True)


def graceful(backup,report):
    require(not GRACEFUL.parent.is_symlink(),'graceful_directory_symlink')
    GRACEFUL.parent.mkdir(parents=True,exist_ok=True,mode=0o755)
    created=False
    if GRACEFUL.exists():
        require(not GRACEFUL.is_symlink() and GRACEFUL.read_bytes()==GRACEFUL_BYTES,'existing_graceful_override_differs')
        shutil.copy2(GRACEFUL,backup/'graceful.before')
        (backup/'graceful.before').chmod(0o600)
    else:
        (backup/'graceful.before.absent').write_text('absent\n')
        (backup/'graceful.before.absent').chmod(0o600)
        temporary=GRACEFUL.with_name('.agriscan-graceful.'+report['release_id']+'.next')
        require(not temporary.exists(),'graceful_temporary_exists')
        try:
            with temporary.open('xb') as output:
                output.write(GRACEFUL_BYTES)
                output.flush()
                os.fsync(output.fileno())
            temporary.chmod(0o644)
            os.link(temporary,GRACEFUL)  # Atomic publication without overwriting another operator.
            created=True
        finally:
            temporary.unlink(missing_ok=True)
    command(['systemctl','daemon-reload'],'systemd_daemon_reload_failed',30)
    require(seconds(service()['TimeoutStopUSec'])>=180,'graceful_timeout_not_applied')
    report['graceful_override']={'created':created,'timeout_stop_seconds':180,'retained_on_failure':True,
                                'reason':'Keep sufficient SIGTERM grace instead of restoring the previous 5s forced kill.'}


def verify_models(plan,report):
    values=dotenv_values(stream=io.StringIO(ENV.read_text()),interpolate=False)
    login={'username':values.get('ADMIN_USERNAME'),'password':values.get('ADMIN_PASSWORD')}
    values.clear()
    require(all(login.values()),'administrator_login_configuration_missing')
    token=None
    try:
        token=json.loads(request('http://127.0.0.1:18000/api/auth/login',data=login))['access_token']
        login.clear()
        active=json.loads(request('http://127.0.0.1:18000/api/models',token=token))['active']
        require(active['task']=='detect' and active['pipeline']=='detection_with_classification','active_pipeline_mismatch')
        require(active['onnx_sha256']==plan['detection_onnx_sha256'],'active_detection_hash_mismatch')
        components=active['components']
        require(len(components)==2,'active_component_count')
        by_role={row['role']:row for row in components}
        require(set(by_role)=={'detection','verification'},'active_component_roles')
        for role,task,key in [('detection','detect','detection_onnx_sha256'),('verification','classify','classification_onnx_sha256')]:
            row=by_role[role]
            require(row['task']==task and row['status']=='ready' and row['class_count']==38
                    and row['onnx_sha256']==plan[key],'active_component_mismatch')
        report['active_components']=[{name:row[name] for name in ('name','role','task','status','class_count','onnx_sha256')}
                                     for row in components]
    finally:
        login.clear()
        revoked=False
        if token:
            for _ in range(3):
                try:
                    request('http://127.0.0.1:18000/api/auth/logout',data={},token=token,timeout=10)
                    revoked=True
                    break
                except Exception:
                    time.sleep(1)
        report['owned_session_revoked']=revoked
    require(report['owned_session_revoked'],'owned_session_logout_failed')


def validate_plan(plan):
    required={'patch_archive_path','patch_sha256','release_id','payload_manifest_sha256','expected_current',
              'expected_schema','expected_configuration_version','expected_configuration_sha256','expected_api_pid',
              'classification_archive_path','classification_archive_sha256','classification_onnx_sha256',
              'detection_onnx_sha256','apk_path','apk_sha256','apk_bytes','apk_version','apk_version_code',
              'expected_previous_classification_value'}
    require(set(plan)==required,'activation_plan_fields')
    require(bool(re.fullmatch(r'release-[a-z0-9][a-z0-9-]{5,100}',plan['release_id'])),'invalid_release_id')
    for name in ('patch_sha256','payload_manifest_sha256','expected_configuration_sha256','classification_archive_sha256',
                 'classification_onnx_sha256','detection_onnx_sha256','apk_sha256'):
        require(isinstance(plan[name],str) and bool(HASH.fullmatch(plan[name])),'invalid_plan_checksum')
    for name in ('patch_archive_path','classification_archive_path','apk_path'):
        path=Path(plan[name])
        require(path.is_absolute() and '..' not in path.parts and path.parent==ROOT/'bootstrap','invalid_bootstrap_path')
    require(Path(plan['expected_current']).parent==ROOT/'releases','invalid_expected_current')
    require(plan['expected_previous_classification_value'] is None
            or isinstance(plan['expected_previous_classification_value'],str),'invalid_previous_classification_value')


def activate(plan):
    validate_plan(plan)
    current=ROOT/'current'
    previous=Path(plan['expected_current'])
    release=ROOT/'releases'/plan['release_id']
    backup=ROOT/'shared/backups'/plan['release_id']
    log=ROOT/'shared/logs'/(plan['release_id']+'.json')
    require(current.is_symlink() and current.resolve()==previous,'baseline_current_changed')
    require(not release.exists() and not release.is_symlink() and not backup.exists() and not log.exists(),'release_identifier_already_used')
    before_service=service()
    require(before_service['ActiveState']=='active' and before_service['SubState']=='running'
            and int(before_service['MainPID'])==plan['expected_api_pid'],'baseline_service_changed')
    expected_metadata={'schema':plan['expected_schema'],'configuration_version':plan['expected_configuration_version'],
                       'configuration_sha256':plan['expected_configuration_sha256']}
    require(metadata()==expected_metadata,'baseline_runtime_changed')
    for name in ('patch_archive_path','classification_archive_path','apk_path'):
        artifact=Path(plan[name])
        require(artifact.is_file() and not artifact.is_symlink()
                and artifact.resolve().parent==(ROOT/'bootstrap').resolve(),'bootstrap_artifact_type')
    require(sha(plan['patch_archive_path'])==plan['patch_sha256'],'patch_archive_hash_mismatch')
    require(sha(plan['classification_archive_path'])==plan['classification_archive_sha256'],'classification_archive_hash_mismatch')
    require(sha(plan['apk_path'])==plan['apk_sha256'] and Path(plan['apk_path']).stat().st_size==plan['apk_bytes'],'apk_artifact_mismatch')
    require(not ENV.is_symlink() and ENV.is_file(),'environment_file_type')
    before_env=ENV.read_bytes()
    env_stat=ENV.stat()
    identity=(0,grp.getgrnam('agriscan').gr_gid,0o640)
    require((env_stat.st_uid,env_stat.st_gid,stat.S_IMODE(env_stat.st_mode))==identity,'environment_permissions_unexpected')
    require(env_value(before_env)==plan['expected_previous_classification_value'],'classification_environment_baseline_changed')
    before_env_sha=hashlib.sha256(before_env).hexdigest()
    next_line=(ENV_KEY+'='+ENV_VALUE+'\n').encode()
    next_env=patch_env(before_env,next_line)
    require(without_classification(before_env)==without_classification(next_env),'non_classification_environment_changed')
    next_env_sha=hashlib.sha256(next_env).hexdigest()
    protected=[Path('/etc/nginx/agriscan-locations.inc'),Path('/etc/nginx/conf.d/zz-agriscan.conf'),Path('/etc/nginx/conf.d/flowly-share.conf')]
    before_conf={str(path):sha(path) for path in protected}
    backup.mkdir(mode=0o700)
    (backup/'production.env.before').write_bytes(before_env)
    (backup/'production.env.before').chmod(0o600)
    (backup/'previous-release.txt').write_text(str(previous)+'\n')
    (backup/'previous-release.txt').chmod(0o600)
    report={'status':'preparing','release_id':plan['release_id'],'previous_release':str(previous),'release':str(release),
            'backup':str(backup),'started_at':datetime.now(timezone.utc).isoformat(),'stages':[],
            'runtime_before':expected_metadata,'service_before':before_service,'nginx_changed':False,
            'database_migration_performed':False,'business_configuration_mutated':False,'api_restart_attempts':0}
    switched=env_changed=restart_attempted=False
    def stage(name):
        report['stages'].append(name)
        print('STAGE '+name,flush=True)
    try:
        stage('validated_artifacts_and_baseline')
        with tarfile.open(plan['patch_archive_path'],'r:gz') as patch:
            entries=members(patch,'payload-files.json')
            by_name={entry.name:entry for entry in entries}
            require('payload-files.json' in by_name,'payload_manifest_missing')
            raw=patch.extractfile(by_name['payload-files.json']).read(4*1024*1024+1)
            require(len(raw)<=4*1024*1024 and hashlib.sha256(raw).hexdigest()==plan['payload_manifest_sha256'],'payload_manifest_hash_mismatch')
            manifest=json.loads(raw)
            require(isinstance(manifest,dict) and manifest,'payload_manifest_shape')
            for name,digest in manifest.items():
                require(allowed(name,'payload-files.json',external=True) and HASH.fullmatch(digest),'payload_manifest_entry')
            critical={'backend/app/main.py','backend/app/inference.py','backend/app/combined_inference.py',
                      'backend/app/class_verification_mapping.json','public/workspace/index.html','public/admin/index.html',
                      'public/downloads/agriscan-test.apk','public/downloads/release.json',
                      'public/downloads/agriscan-test.apk.sha256','model-classification/model.onnx',
                      'model-classification/manifest.json','release-info.json'}
            require(critical<=set(manifest),'payload_manifest_incomplete')
            require(set(by_name)-{'payload-files.json'}<=set(manifest),'unlisted_patch_member')
            def skip_generated(_path,names):
                return {name for name in names if name=='__pycache__' or name.endswith('.pyc')}
            shutil.copytree(previous,release,symlinks=True,ignore=skip_generated)
            extract_regular(patch,entries,release)
        with tarfile.open(plan['classification_archive_path'],'r:gz') as classifier:
            extract_regular(classifier,members(classifier,'payload-files.json',classifier=True),release)
        shutil.copyfile(plan['apk_path'],target_file(release,'public/downloads/agriscan-test.apk'))
        (release/'public/downloads/agriscan-test.apk').chmod(0o644)
        app=release/'backend/app'
        target_file(release,'backend/app/main.py')
        require(app.is_dir() and not app.is_symlink() and app.resolve().is_relative_to(release.resolve()),'app_tree_invalid')
        for path in app.rglob('*'):
            require(not path.is_symlink(),'app_symlink_rejected')
            if path.is_file() and path.relative_to(release).as_posix() not in manifest:
                path.unlink()  # Only obsolete copied code/cache in this new release.
        for name,digest in manifest.items():
            path=target_file(release,name)
            require(path.is_file() and sha(path)==digest,'payload_file_hash_mismatch')
        require(sha(release/'model/model.onnx')==plan['detection_onnx_sha256'],'inherited_detector_hash_mismatch')
        require(sha(release/'model-classification/model.onnx')==plan['classification_onnx_sha256'],'classifier_onnx_hash_mismatch')
        for relative,task,key in [('model/manifest.json','detect','detection_onnx_sha256'),('model-classification/manifest.json','classify','classification_onnx_sha256')]:
            model=json.loads((release/relative).read_text())
            require(model['task']==task and model['validation_passed'] is True and len(model['classes'])==38
                    and model['onnx_sha256']==plan[key],'model_manifest_mismatch')
        retained=0
        for surface in ('workspace','admin'):
            old=previous/'public'/surface/'assets'
            for path in old.rglob('*'):
                if path.is_file():
                    require(not path.is_symlink() and sha(path)==sha(release/path.relative_to(previous)),'previous_hashed_asset_changed')
                    retained+=1
        info=json.loads((release/'release-info.json').read_text())
        require(info['release_id']==plan['release_id'] and info['parent_release']==str(previous)
                and info['database_migration_required'] is False,'release_info_identity_mismatch')
        require(info['pipeline']=={'name':'detection_with_classification','detection_onnx_sha256':plan['detection_onnx_sha256'],
                                  'classification_onnx_sha256':plan['classification_onnx_sha256']},'release_info_pipeline_mismatch')
        download=json.loads((release/'public/downloads/release.json').read_text())
        require(download['status']=='ready' and download['version']==plan['apk_version'] and download['version_code']==plan['apk_version_code']
                and download['sha256']==plan['apk_sha256'] and download['size_bytes']==plan['apk_bytes']
                and download['api_base_url']==PUBLIC.rstrip('/') and download['package_id']=='cn.agriscan.mobile','download_metadata_mismatch')
        require((release/'public/downloads/agriscan-test.apk.sha256').read_text().split()==[plan['apk_sha256'],'agriscan-test.apk'],'download_checksum_mismatch')
        require(info['apk']['sha256']==plan['apk_sha256'] and info['apk']['apk_bytes']==plan['apk_bytes']
                and info['apk']['version']==plan['apk_version'] and info['apk']['version_code']==plan['apk_version_code'],'release_info_apk_mismatch')
        report.update(payload_files_verified=len(manifest),previous_hashed_assets_retained=retained,
                      source_tree_sha256=info['source_tree_sha256'],source_file_count=info['source_file_count'])
        stage('prepared_release_verified_without_model_preload')
        require(current.resolve()==previous and sha(ENV)==before_env_sha and metadata()==expected_metadata,'pre_switch_baseline_changed')
        require({str(path):sha(path) for path in protected}==before_conf,'nginx_changed_externally')
        graceful(backup,report)
        stage('graceful_timeout_ready')
        atomic_env(next_env,before_env_sha,identity,plan['release_id'])
        env_changed=True
        require(current.resolve()==previous,'pre_switch_current_changed')
        pointer(current,previous,release,plan['release_id']+'.next')
        switched=True
        stage('current_pointer_switched')
        restart_attempted=True
        report['api_restart_attempts']+=1
        command(['systemctl','restart','agriscan-api'],'api_restart_failed',330)
        report['health_after']=health()
        stage('api_restarted_and_model_ready')
        verify_models(plan,report)
        require(metadata()==expected_metadata,'post_start_runtime_changed')
        samples=[]
        for index in range(3):
            sample=service()
            require(sample['ActiveState']=='active' and sample['SubState']=='running'
                    and int(sample['MainPID'])!=plan['expected_api_pid'] and sample['NRestarts']=='0','new_service_not_stable')
            require(sample['MemoryMax']==before_service['MemoryMax'],'service_memory_limit_changed')
            if sample['MemoryMax'].isdigit() and sample['MemoryCurrent'].isdigit():
                require(int(sample['MemoryMax'])-int(sample['MemoryCurrent'])>=128*1024*1024,'insufficient_idle_memory_headroom')
            samples.append(sample)
            if index<2:
                time.sleep(2)
        report['idle_resource_samples']=samples
        stage('both_loaded_components_and_runtime_verified')
        checks={}
        for relative in ('index.html','workspace/index.html','admin/index.html','downloads/release.json'):
            content=public_request(relative)
            require(content==(release/'public'/relative).read_bytes(),'public_static_content_mismatch')
            checks[relative]={'status':200,'sha256':hashlib.sha256(content).hexdigest()}
        require(json.loads(public_request('api/health'))==report['health_after'],'public_api_health_mismatch')
        require(current.resolve()==release and sha(ENV)==next_env_sha and metadata()==expected_metadata,'final_runtime_changed')
        require({str(path):sha(path) for path in protected}==before_conf,'nginx_changed_externally')
        report.update(status='passed',runtime_after=metadata(),public_checks=checks,
                      environment_classification_only=True,environment_mode='0640 root:agriscan',
                      environment_before_sha256=before_env_sha,environment_after_sha256=next_env_sha,
                      detector_onnx_sha256=plan['detection_onnx_sha256'],classification_onnx_sha256=plan['classification_onnx_sha256'],
                      apk={'version':plan['apk_version'],'version_code':plan['apk_version_code'],'bytes':plan['apk_bytes'],'sha256':plan['apk_sha256']})
        stage('public_html_health_and_download_metadata_verified')
    except BaseException as error:
        report.update(status='failed',error_code=str(error) if isinstance(error,ActivationError) else type(error).__name__,
                      rollback_errors=[],graceful_setting_retained=True)
        can_restore=current.resolve() in {previous,release}
        if not can_restore:
            report['rollback_errors'].append('current_pointer_changed_externally_preserved')
        if can_restore:
            try:
                if env_changed:
                    actual=ENV.read_bytes()
                    require(env_lines(actual)==[next_line],'classification_environment_changed_externally_preserved')
                    old_lines=env_lines(before_env)
                    restored=patch_env(actual,old_lines[0] if old_lines else b'')
                    atomic_env(restored,hashlib.sha256(actual).hexdigest(),identity,plan['release_id']+'.rollback')
                    report['rollback_preserved_other_environment_changes']=without_classification(actual)!=without_classification(before_env)
                if switched and current.resolve()==release:
                    pointer(current,release,previous,plan['release_id']+'.rollback')
                if restart_attempted:
                    report['api_restart_attempts']+=1
                    command(['systemctl','restart','agriscan-api'],'rollback_restart_failed',330)
                report['rollback_health']=health()
                report['rolled_back']=current.resolve()==previous and env_value(ENV.read_bytes())==plan['expected_previous_classification_value']
                require(report['rolled_back'],'rollback_identity_failed')
            except BaseException as rollback_error:
                report['rolled_back']=False
                report['rollback_errors'].append(str(rollback_error) if isinstance(rollback_error,ActivationError) else type(rollback_error).__name__)
        else:
            report['rolled_back']=False
    finally:
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        temporary=log.with_name('.'+log.name+'.next')
        with temporary.open('x',encoding='utf-8') as output:
            json.dump(report,output,ensure_ascii=True,indent=2)
        temporary.chmod(0o600)
        os.replace(temporary,log)
        try:
            print('RESULT '+json.dumps(report,ensure_ascii=True),flush=True)
        except BrokenPipeError:
            pass  # The private server report remains available after SSH loss.
    return 0 if report['status']=='passed' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan-base64',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    require(args.apply,'explicit_apply_required')
    plan=json.loads(base64.b64decode(args.plan_base64,validate=True))
    def interrupted(_signum,_frame):
        raise ActivationError('activation_interrupted_by_signal')
    for name in ('SIGTERM','SIGHUP'):
        if hasattr(signal,name):
            signal.signal(getattr(signal,name),interrupted)
    lock_path=ROOT/'shared/dual-model-activation.lock'
    with lock_path.open('a') as lock:
        lock_path.chmod(0o600)
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return activate(plan)


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except ActivationError as error:
        print('PRECHECK_FAILED '+str(error),flush=True)
        raise SystemExit(1)
