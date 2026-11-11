"""Static-only final release: identical API/models, no service/env/database writes."""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import types

# The local wrapper embeds the reviewed activation helpers into stdin. Importing
# them only defines helpers; activate()/main()/model prewarming are never called.
if '_REVIEWED_HELPERS' not in globals():
    _REVIEWED_HELPERS=(Path(__file__).resolve().parent/'activate-server.py').read_text(encoding='utf-8')
h=types.ModuleType('static_reviewed_activation_helpers')
exec(compile(_REVIEWED_HELPERS,'reviewed-activation-helpers.py','exec'),h.__dict__)
ROOT=Path('/srv/agriscan')
UNCHANGED_TREES=('backend/app','model','model-classification')
PROTECTED=(Path('/srv/agriscan/shared/production.env'),Path('/etc/nginx/nginx.conf'),
           Path('/etc/nginx/agriscan-locations.inc'),Path('/etc/nginx/conf.d/zz-agriscan.conf'),Path('/etc/nginx/conf.d/flowly-share.conf'))

class Refused(RuntimeError): pass

def require(value,code):
    if not value: raise Refused(code)

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def interpreter_cache(name):
    path=PurePosixPath(name)
    return '__pycache__' in path.parts or path.suffix in {'.pyc','.pyo'}

def validate(plan):
    fields={'patch_archive_path','patch_sha256','release_id','payload_manifest_sha256','expected_current','expected_schema',
            'expected_configuration_version','expected_configuration_sha256','expected_api_pid','expected_api_nrestarts',
            'expected_payload_files','apk_path','apk_sha256','apk_bytes','apk_version','apk_version_code',
            'detection_onnx_sha256','classification_onnx_sha256'}
    require(set(plan)==fields,'static_plan_fields')
    require(isinstance(plan['release_id'],str) and re.fullmatch(r'release-[a-z0-9][a-z0-9-]{5,100}',plan['release_id']),'release_id')
    require(plan['expected_schema']=='20261029_06','schema_not_reviewed')
    for key in fields:
        if key.endswith('_sha256'):require(isinstance(plan[key],str) and re.fullmatch('[a-f0-9]{64}',plan[key]),'plan_checksum')
    for key in ('expected_configuration_version','expected_api_pid','expected_api_nrestarts','expected_payload_files','apk_bytes','apk_version_code'):
        require(type(plan[key]) is int and plan[key]>=0,'plan_integer')
    require(plan['expected_api_pid']>0 and plan['expected_payload_files']>0 and plan['apk_bytes']>0,'positive_plan_integer')
    for key in ('patch_archive_path','apk_path'):
        value=plan[key]
        require(isinstance(value,str) and re.fullmatch(r'/srv/agriscan/bootstrap/[a-zA-Z0-9_.-]+',value),'bootstrap_path')
    require(isinstance(plan['expected_current'],str) and re.fullmatch(r'/srv/agriscan/releases/release-[a-z0-9-]+',plan['expected_current']),'expected_current')

def tree(release,relative):
    folder=release/relative
    h.target_file(release,relative+'/__tree_probe__')
    require(folder.is_dir() and not folder.is_symlink(),'inherited_tree_invalid')
    result={}
    for path in sorted(folder.rglob('*')):
        if relative=='backend/app' and interpreter_cache(path.relative_to(folder).as_posix()):
            continue
        require(not path.is_symlink(),'inherited_tree_symlink')
        if path.is_file():result[path.relative_to(release).as_posix()]=h.sha(path)
    require(result,'inherited_tree_empty')
    return result

def unchanged_trees(previous,release,before):
    for relative in UNCHANGED_TREES:
        require(tree(previous,relative)==before[relative],'current_code_or_models_changed_during_prepare')
        require(tree(release,relative)==before[relative],'backend_or_models_changed_refuse_no_restart')

def runtime_matches(plan,service):
    require(service['ActiveState']=='active' and service['SubState']=='running'
            and int(service['MainPID'])==plan['expected_api_pid']
            and int(service['NRestarts'])==plan['expected_api_nrestarts'],'live_api_identity_changed')

def metadata_expected(plan):
    return {'schema':plan['expected_schema'],'configuration_version':plan['expected_configuration_version'],
            'configuration_sha256':plan['expected_configuration_sha256']}

def protected():return {str(path):h.sha(path) for path in PROTECTED}

def private_write(path,raw):
    with path.open('xb') as stream:stream.write(raw);stream.flush();h.os.fsync(stream.fileno())
    path.chmod(0o600)

def activate(plan):
    validate(plan)
    current=ROOT/'current';previous=Path(plan['expected_current']);release=ROOT/'releases'/plan['release_id']
    backup=ROOT/'shared/backups'/(plan['release_id']+'-static-only')
    log=ROOT/'shared/logs'/(plan['release_id']+'-static-only.json')
    require(current.is_symlink() and current.resolve()==previous,'baseline_current_changed')
    require(not release.exists() and not release.is_symlink() and not backup.exists() and not log.exists(),'static_release_id_used')
    service_before=h.service();runtime_matches(plan,service_before)
    expected=metadata_expected(plan);require(h.metadata()==expected,'baseline_runtime_changed')
    env_nginx_before=protected()
    before={relative:tree(previous,relative) for relative in UNCHANGED_TREES}
    require(h.sha(previous/'model/model.onnx')==plan['detection_onnx_sha256']
            and h.sha(previous/'model-classification/model.onnx')==plan['classification_onnx_sha256'],'inherited_model_hash_mismatch')
    for key in ('patch_archive_path','apk_path'):
        path=Path(plan[key]);require(path.is_file() and not path.is_symlink()
            and path.resolve().parent==(ROOT/'bootstrap').resolve(),'bootstrap_artifact_type')
    require(h.sha(plan['patch_archive_path'])==plan['patch_sha256'],'patch_archive_sha_mismatch')
    require(h.sha(plan['apk_path'])==plan['apk_sha256'] and Path(plan['apk_path']).stat().st_size==plan['apk_bytes'],'apk_artifact_mismatch')
    backup.mkdir(mode=0o700)
    private_write(backup/'previous-release.txt',(str(previous)+'\n').encode())
    report={'status':'preparing','release_id':plan['release_id'],'previous_release':str(previous),'release':str(release),
            'backup':str(backup),'started_at':datetime.now(timezone.utc).isoformat(),'stages':[],
            'api_restart_attempts':0,'service_mutated':False,'environment_mutated':False,'nginx_mutated':False,
            'database_mutated':False,'configuration_mutated':False,'runtime_before':expected,
            'api_pid_before':plan['expected_api_pid'],'api_nrestarts_before':plan['expected_api_nrestarts']}
    switched=False
    def stage(name):report['stages'].append(name);print('STAGE '+name,flush=True)
    try:
        stage('static_baseline_and_artifacts_verified')
        with tarfile.open(plan['patch_archive_path'],'r:gz') as archive:
            entries=h.members(archive,'payload-files.json');by_name={entry.name:entry for entry in entries}
            require('payload-files.json' in by_name,'payload_manifest_missing')
            raw=archive.extractfile(by_name['payload-files.json']).read(4*1024*1024+1)
            require(len(raw)<=4*1024*1024 and hashlib.sha256(raw).hexdigest()==plan['payload_manifest_sha256'],'payload_manifest_sha_mismatch')
            manifest=json.loads(raw)
            require(isinstance(manifest,dict) and len(manifest)==plan['expected_payload_files'],'payload_file_count_mismatch')
            for name,value in manifest.items():require(h.allowed(name,'payload-files.json',external=True) and isinstance(value,str) and h.HASH.fullmatch(value),'payload_manifest_entry')
            require(not any(name.startswith('backend/app/') and interpreter_cache(name) for name in manifest),
                    'payload_contains_interpreter_cache')
            require(set(by_name)-{'payload-files.json'}<=set(manifest),'patch_member_not_in_manifest')
            required={'backend/app/main.py','public/workspace/index.html','public/admin/index.html','release-info.json',
                      'public/downloads/release.json','public/downloads/agriscan-test.apk','public/downloads/agriscan-test.apk.sha256'}
            require(required<=set(manifest),'static_payload_missing_critical_files')
            require({name:value for name,value in manifest.items() if name.startswith('backend/app/')}==before['backend/app'],
                    'manifest_backend_differs_from_live_api')
            # Even if copied from a broad old package, changed API code/model
            # bytes are rejected before publishing the pointer.
            shutil.copytree(previous,release,symlinks=True)
            h.extract_regular(archive,entries,release)
        shutil.copyfile(plan['apk_path'],h.target_file(release,'public/downloads/agriscan-test.apk'))
        (release/'public/downloads/agriscan-test.apk').chmod(0o644)
        for name,value in manifest.items():
            path=h.target_file(release,name);require(path.is_file() and h.sha(path)==value,'payload_file_sha_mismatch')
        unchanged_trees(previous,release,before)
        # copytree retains all historical hashed assets for already-open pages.
        for surface in ('workspace','admin'):
            for path in (previous/'public'/surface/'assets').rglob('*'):
                if path.is_file():require(not path.is_symlink() and h.sha(path)==h.sha(h.target_file(release,path.relative_to(previous).as_posix())),'old_hashed_asset_changed')
        info=json.loads((release/'release-info.json').read_text())
        require(info['release_id']==plan['release_id'] and info['parent_release']==str(previous)
                and info['database_migration_required'] is False,'release_info_identity')
        require(info['pipeline']=={'name':'detection_with_classification','detection_onnx_sha256':plan['detection_onnx_sha256'],
                                  'classification_onnx_sha256':plan['classification_onnx_sha256']},'release_pipeline_mismatch')
        apk=info['apk'];download=json.loads((release/'public/downloads/release.json').read_text())
        require(apk['sha256']==plan['apk_sha256'] and apk['apk_bytes']==plan['apk_bytes'] and apk['version']==plan['apk_version']
                and apk['version_code']==plan['apk_version_code'],'release_info_apk_mismatch')
        require(download['status']=='ready' and download['sha256']==plan['apk_sha256'] and download['size_bytes']==plan['apk_bytes']
                and download['version']==plan['apk_version'] and download['version_code']==plan['apk_version_code']
                and download['api_base_url']==h.PUBLIC.rstrip('/') and download['package_id']=='cn.agriscan.mobile','download_metadata_mismatch')
        require((release/'public/downloads/agriscan-test.apk.sha256').read_text().split()==[plan['apk_sha256'],'agriscan-test.apk'],'download_checksum_mismatch')
        report.update(payload_files_verified=len(manifest),source_tree_sha256=info['source_tree_sha256'],source_file_count=info['source_file_count'],
                      inherited_tree_sha256={name:digest(values) for name,values in before.items()},backend_and_models_identical=True)
        stage('complete_manifest_backend_and_models_identical')
        require(current.resolve()==previous and protected()==env_nginx_before and h.metadata()==expected,'pre_switch_baseline_changed')
        runtime_matches(plan,h.service())
        h.pointer(current,previous,release,plan['release_id']+'-static');switched=True
        stage('static_pointer_switched_without_api_restart')
        require(h.health(wait=20)['model']=='ready','live_api_health_changed')
        runtime_matches(plan,h.service())
        checks={}
        relatives=['index.html','workspace/index.html','admin/index.html','downloads/release.json','downloads/agriscan-test.apk.sha256']
        for entry in info['workspace_entries']+info['admin_entries']:
            require(isinstance(entry,str) and entry.startswith('/agriscan/'),'entry_url_scope')
            relative=entry.removeprefix('/agriscan/');h.path_name(relative);relatives.append(relative)
        for relative in dict.fromkeys(relatives):
            content=h.public_request(relative)
            require(content==h.target_file(release,'public/'+relative).read_bytes(),'public_static_bytes_mismatch')
            checks[relative]={'status':200,'sha256':hashlib.sha256(content).hexdigest()}
        require(current.resolve()==release and h.metadata()==expected and protected()==env_nginx_before,'final_runtime_changed')
        service_after=h.service();runtime_matches(plan,service_after)
        require(service_after['MemoryMax']==service_before['MemoryMax'],'service_memory_limit_changed')
        require(h.sha(ROOT/'current/model/model.onnx')==plan['detection_onnx_sha256']
                and h.sha(ROOT/'current/model-classification/model.onnx')==plan['classification_onnx_sha256'],'final_model_identity')
        report.update(status='passed',runtime_after=h.metadata(),api_pid_after=int(service_after['MainPID']),
                      api_nrestarts_after=int(service_after['NRestarts']),protected_configuration_sha256=env_nginx_before,
                      public_checks=checks,apk={'sha256':plan['apk_sha256'],'bytes':plan['apk_bytes'],
                      'version':plan['apk_version'],'version_code':plan['apk_version_code']})
        stage('public_static_and_unchanged_live_api_verified')
    except BaseException as error:
        report.update(status='failed',error_code=str(error) if isinstance(error,(Refused,h.ActivationError)) else type(error).__name__,rolled_back=False)
        if switched:
            try:
                # Only our own symlink is reverted; no env, database or service
                # restore is allowed, including on a concurrent config edit.
                h.pointer(current,release,previous,plan['release_id']+'-static-rollback')
                report['rolled_back']=current.resolve()==previous
                report['rollback_health']=h.health(wait=20)
                after=h.service();report['api_pid_after']=int(after['MainPID']);report['api_nrestarts_after']=int(after['NRestarts'])
            except BaseException as rollback_error:
                report['rollback_error']=str(rollback_error) if isinstance(rollback_error,(Refused,h.ActivationError)) else type(rollback_error).__name__
    finally:
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        private_write(log,json.dumps(report,ensure_ascii=False,indent=2).encode())
        private_write(backup/'report.json',json.dumps(report,ensure_ascii=False,indent=2).encode())
        print('RESULT '+json.dumps(report,ensure_ascii=False),flush=True)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan-base64',required=True);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    try:
        plan=json.loads(base64.b64decode(args.plan_base64,validate=True));validate(plan)
        require(args.apply,'explicit_apply_required')
        lock_path=ROOT/'shared/dual-model-activation.lock'
        with lock_path.open('a') as stream:
            lock_path.chmod(0o600);h.fcntl.flock(stream,h.fcntl.LOCK_EX|h.fcntl.LOCK_NB)
            result=activate(plan)
    except BaseException as error:
        print('PRECHECK_FAILED '+(str(error) if isinstance(error,(Refused,h.ActivationError)) else type(error).__name__),flush=True)
        raise SystemExit(1)
    raise SystemExit(0 if result['status']=='passed' else 1)

if __name__=='__main__':main()
