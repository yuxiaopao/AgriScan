"""Minimal registration release with a bounded, reversible detection-admission drain.

Inspect is read-only. Apply creates a new release, temporarily gates NEW detection
POSTs at Nginx, and leaves existing PUT/GET requests running. No database, runtime
configuration, environment, models, APK or website content is replaced.
"""
import argparse
import base64
from datetime import datetime, timezone
import fcntl
import hashlib
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
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path('/srv/agriscan')
INC = Path('/etc/nginx/agriscan-locations.inc')
STAGING = ROOT/'shared/uploads/.task-staging'
PROTECTED = [ROOT/'shared/production.env', Path('/etc/nginx/nginx.conf'),
    Path('/etc/nginx/conf.d/zz-agriscan.conf'), Path('/etc/nginx/conf.d/flowly-share.conf'),
    Path('/etc/systemd/system/agriscan-api.service'),
    Path('/etc/systemd/system/agriscan-api.service.d/agriscan-graceful.conf')]
IMMUTABLE = ['model', 'model-classification', 'public/downloads']
HASH = re.compile(r'[a-f0-9]{64}')
PUBLIC = 'https://agriscan.ming-ai.top/agriscan/'
HTTP = build_opener(ProxyHandler({}))
API_ANCHOR = b'location /agriscan/api/ {\n'
PROXY = b'    proxy_pass http://127.0.0.1:18000/api/;\n'
ENDPOINTS = ('detection-tasks', 'detections', 'media/video', 'media/frame')


class Refused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise Refused(code)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def raw_sha(raw):
    return hashlib.sha256(raw).hexdigest()


def command(args, code, timeout=30):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    require(result.returncode == 0, code)
    return result.stdout.strip()


def metadata():
    sql = ("SELECT version_num FROM agriscan.alembic_version; "
        "SELECT version,SHA2(CONCAT_WS(CHAR(31),id,version,CAST(data AS CHAR),COALESCE(encrypted_secrets,''),"
        "COALESCE(updated_by,''),COALESCE(CAST(updated_at AS CHAR),'')),256) "
        "FROM agriscan.workspace_configuration WHERE id='workspace';")
    lines = command(['mysql', '--batch', '--skip-column-names', '--execute', sql], 'runtime_metadata_failed', 15).splitlines()
    require(len(lines) == 2, 'runtime_metadata_shape')
    version, checksum = lines[1].split('\t')
    require(version.isdigit() and HASH.fullmatch(checksum), 'runtime_metadata_checksum')
    return dict(schema=lines[0], configuration_version=int(version), configuration_sha256=checksum)


def service(name='agriscan-api'):
    properties = 'MainPID,NRestarts,ActiveState,SubState,MemoryCurrent,MemoryPeak,MemoryMax,TimeoutStopUSec'
    return dict(line.split('=', 1) for line in command(
        ['systemctl', 'show', name, '--property='+properties], 'service_metadata_failed').splitlines() if '=' in line)


def protected():
    for path in PROTECTED:
        require(path.is_file() and not path.is_symlink(), 'protected_path_not_regular')
    return {str(path): sha(path) for path in PROTECTED}


def request(url, data=None, timeout=15):
    headers = {'Cache-Control': 'no-cache'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(url, data=None if data is None else json.dumps(data).encode(), headers=headers)
    try:
        response = HTTP.open(req, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        body = response.read(4*1024*1024+1)
        require(len(body) <= 4*1024*1024, 'http_response_too_large')
        return response.status, body


def health(wait=150):
    deadline = time.monotonic()+wait
    while True:
        try:
            status, raw = request('http://127.0.0.1:18000/api/health', timeout=4)
            data = json.loads(raw)
            if status == 200 and data == {'status':'ok', 'database':'connected', 'redis':'connected', 'mode':'production', 'model':'ready'}:
                return data
        except Exception:
            pass
        require(time.monotonic() < deadline, 'api_health_deadline')
        time.sleep(1)


def gate_bytes(raw):
    require(raw.count(API_ANCHOR) == 1 and b'AGRISCAN_REGISTRATION_HOTFIX_GATE' not in raw, 'nginx_gate_anchor')
    body, end = raw.split(API_ANCHOR, 1)[1].split(b'\n}', 1)
    require(b'{' not in body and b'}' not in body and body.count(PROXY.rstrip(b'\n')) == 1, 'nginx_api_block_shape')
    # The baseline body includes exactly the existing headers, timeouts and
    # request-streaming options. Only the upstream path differs for exact routes.
    require(b'proxy_request_buffering off;' in body and b'proxy_http_version 1.1;' in body, 'streaming_options_missing')
    locations = [b'# AGRISCAN_REGISTRATION_HOTFIX_GATE: transient detection POST admission only\n']
    for endpoint in ENDPOINTS:
        for suffix in ('', '/'):
            route = endpoint+suffix
            copied = body.replace(PROXY.rstrip(b'\n'), b'    proxy_pass http://127.0.0.1:18000/api/'+route.encode()+b';', 1)
            locations.append(b'location = /agriscan/api/'+route.encode()+b' {\n'
                b'    if ($request_method = POST) {\n'
                b'        add_header Retry-After 15 always;\n'
                b'        add_header Cache-Control "private, no-store" always;\n'
                b'        return 503;\n'
                b'    }\n'+copied+b'\n}\n')
    return b''.join(locations)+raw


def children(master):
    return set(Path(f'/proc/{master}/task/{master}/children').read_text().split())


def reload_nginx(master):
    old = children(master)
    command(['systemctl', 'reload', 'nginx'], 'nginx_reload_failed')
    deadline = time.monotonic()+15
    while time.monotonic() < deadline:
        require(int(service('nginx')['MainPID']) == master, 'nginx_master_changed')
        if children(master)-old:
            return old
        time.sleep(.25)
    raise Refused('nginx_new_generation_missing')


def publish_include(raw, expected_sha, identity, tag):
    require(INC.is_file() and not INC.is_symlink() and sha(INC) == expected_sha, 'nginx_include_concurrent_change')
    current = INC.stat()
    require((current.st_uid, current.st_gid, stat.S_IMODE(current.st_mode)) == identity, 'nginx_include_identity_changed')
    temporary = INC.with_name('.agriscan-locations.'+tag+'.next')
    fd = os.open(temporary, os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(raw); output.flush(); os.fsync(output.fileno())
        os.chown(temporary, identity[0], identity[1]); temporary.chmod(identity[2])
        require(sha(INC) == expected_sha, 'nginx_include_concurrent_change')
        os.replace(temporary, INC)
    finally:
        temporary.unlink(missing_ok=True)


def staging_empty():
    require(not STAGING.is_symlink(), 'staging_symlink')
    if not STAGING.exists():
        return True
    require(STAGING.is_dir(), 'staging_not_directory')
    return not any(STAGING.iterdir())


def established_api_connections():
    # Kernel TCP state only; no user data, socket payloads, credentials or task
    # process-memory inspection. All Nginx API requests connect to this port.
    count = 0
    for name in ('tcp', 'tcp6'):
        path = Path('/proc/net')/name
        if not path.exists():
            continue
        for line in path.read_text().splitlines()[1:]:
            fields = line.split()
            if len(fields) >= 4 and fields[1].rsplit(':', 1)[1] == f'{18000:04X}' and fields[3] == '01':
                count += 1
    return count


def drain(master, old_workers, report, timeout=600):
    started = time.monotonic()
    deadline = started+timeout
    # Old workers may already own an upload. Let them finish before counting the
    # reservation-expiry interval; then every newly admitted request sees gate.
    while children(master) & old_workers:
        require(time.monotonic() < deadline, 'old_nginx_workers_still_busy_no_restart')
        require(int(service('nginx')['MainPID']) == master, 'nginx_master_changed')
        time.sleep(1)
    enforced = time.monotonic()
    for endpoint in ENDPOINTS:
        status, _raw = request(PUBLIC+'api/'+endpoint, data={})
        require(status == 503, 'public_detection_gate_not_effective_no_restart')
    idle_since = None
    next_progress = enforced+30
    while time.monotonic() < deadline:
        now = time.monotonic()
        empty = staging_empty()
        connections = established_api_connections()
        if now >= next_progress:
            print('STAGE drain_wait elapsed_seconds='+str(round(now-started))
                +' staging_empty='+str(empty).lower()+' api_connections='+str(connections), flush=True)
            next_progress = now+30
        if now-enforced >= 185 and empty and connections == 0:
            idle_since = idle_since or now
            if now-idle_since >= 5:
                report['drain'] = dict(status='passed', old_workers_exited=True,
                    elapsed_seconds=round(now-started, 2), gate_enforced_seconds=round(now-enforced, 2),
                    empty_staging=True, api_established_connections=0, continuous_idle_seconds=round(now-idle_since, 2),
                    reservation_expiry_seconds=180, no_process_injection=True)
                return
        else:
            idle_since = None
        time.sleep(1)
    raise Refused('detection_or_api_traffic_still_busy_no_restart')


def valid_name(value):
    require(isinstance(value, str) and value and '\\' not in value, 'payload_name')
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value and all(part not in ('.', '..') for part in path.parts), 'payload_path')
    return path


def allowed(name):
    path = valid_name(name)
    require(not any(part in ('.env', 'node_modules', '__pycache__', '.git', '.runtime') for part in path.parts), 'payload_private_path')
    return (name in ('hotfix-files.json', 'hotfix-info.json')
        or name.startswith('backend/app/') and path.suffix in ('.py', '.json')
        or name.startswith(('public/workspace/', 'public/admin/')) and path.suffix.lower() in
            ('.html', '.js', '.css', '.json', '.svg', '.png', '.jpg', '.jpeg', '.webp', '.ico', '.woff', '.woff2', '.ttf', '.txt'))


def target(release, name):
    valid_name(name)
    path = release/name
    require(path.resolve().is_relative_to(release.resolve()), 'payload_escaped_release')
    for ancestor in (path, *path.parents):
        if ancestor == release.parent:
            break
        require(not ancestor.is_symlink(), 'payload_symlink')
    return path


def tree(release, relative):
    folder = release/relative
    require(folder.is_dir() and not folder.is_symlink(), 'inherited_tree_not_regular')
    result = {}
    for path in folder.rglob('*'):
        if '__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo'):
            continue
        require(not path.is_symlink(), 'inherited_tree_symlink')
        if path.is_file():
            result[path.relative_to(release).as_posix()] = sha(path)
    require(result, 'inherited_tree_empty')
    return result


def pointer(expected, release, tag):
    current = ROOT/'current'
    require(current.is_symlink() and current.resolve() == expected, 'current_pointer_concurrent_change')
    temporary = ROOT/('.current.'+tag)
    require(not temporary.exists() and not temporary.is_symlink(), 'pointer_temporary_exists')
    try:
        temporary.symlink_to(release, target_is_directory=True)
        require(current.resolve() == expected, 'current_pointer_concurrent_change')
        os.replace(temporary, current)
    finally:
        temporary.unlink(missing_ok=True)


def private_write(path, raw):
    fd = os.open(path, os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(fd, 'wb') as output:
        output.write(raw); output.flush(); os.fsync(output.fileno())


def preserve_copied_ownership(previous, release):
    # copytree/copy2 preserves modes but does not preserve owner/group. Keep
    # original identities on this NEW copy so a 0640 model/0750 code directory
    # remains readable by the service account. Symlink targets are never touched.
    for source in [previous, *previous.rglob('*')]:
        relative = source.relative_to(previous)
        if '__pycache__' in relative.parts or source.suffix in ('.pyc', '.pyo'):
            continue
        copied = release/relative
        if not copied.exists() and not copied.is_symlink():
            continue
        info = source.lstat()
        os.chown(copied, info.st_uid, info.st_gid, follow_symlinks=False)


def service_readable(release):
    # Read one byte only; nothing from source/model files is returned or logged.
    probe = ("import pathlib,sys; root=pathlib.Path(sys.argv[1]); "
        "paths=[p for rel in ('backend/app','model','model-classification') for p in (root/rel).rglob('*') "
        "if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')]; "
        "[(p.open('rb').close()) for p in paths]")
    command(['runuser', '-u', 'agriscan', '--', str(ROOT/'venv/bin/python'), '-c', probe, str(release)],
        'new_release_unreadable_by_service_account')


def inspect():
    current = (ROOT/'current').resolve()
    require(current.parent == ROOT/'releases', 'current_outside_releases')
    raw = INC.read_bytes()
    candidate = gate_bytes(raw)
    state = service()
    runtime = metadata()
    hashes = protected()
    require(metadata() == runtime, 'inspection_configuration_changed_retry')
    return dict(status='read_only_observed', expected_current=str(current), expected_api_pid=int(state['MainPID']),
        expected_api_nrestarts=int(state['NRestarts']), expected_schema=runtime['schema'],
        expected_configuration_version=runtime['configuration_version'], expected_configuration_sha256=runtime['configuration_sha256'],
        expected_protected_sha256=hashes, expected_nginx_include_sha256=raw_sha(raw),
        candidate_nginx_include_sha256=raw_sha(candidate), service=state, nginx_master=int(service('nginx')['MainPID']),
        staging_empty=staging_empty(), api_established_connections=established_api_connections(),
        health=health(wait=5), production_mutations=False)


FIELDS = {'run_id', 'release_id', 'expected_current', 'expected_api_pid', 'expected_api_nrestarts',
    'expected_schema', 'expected_configuration_version', 'expected_configuration_sha256', 'expected_protected_sha256',
    'expected_nginx_include_sha256', 'patch_archive_path', 'patch_sha256', 'payload_manifest_sha256', 'expected_payload_files'}


def validate(plan):
    require(set(plan) == FIELDS, 'plan_fields')
    for key in ('run_id', 'release_id'):
        require(isinstance(plan[key], str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{5,100}', plan[key]), 'plan_identifier')
    require(plan['release_id'].startswith('release-'), 'release_identifier')
    require(re.fullmatch(r'/srv/agriscan/releases/release-[a-z0-9-]+', plan['expected_current']), 'expected_current_path')
    require(re.fullmatch(r'/srv/agriscan/bootstrap/[a-zA-Z0-9_.-]+\.tar\.gz', plan['patch_archive_path']), 'patch_path')
    for key in ('expected_api_pid', 'expected_api_nrestarts', 'expected_configuration_version', 'expected_payload_files'):
        require(type(plan[key]) is int and plan[key] >= 0, 'plan_integer')
    require(plan['expected_api_pid'] > 0 and plan['expected_payload_files'] > 0, 'plan_positive_integer')
    require(plan['expected_schema'] == '20261029_06', 'schema_not_reviewed')
    require(set(plan['expected_protected_sha256']) == {str(path) for path in PROTECTED}, 'protected_plan_paths')
    for value in [plan['expected_configuration_sha256'], plan['expected_nginx_include_sha256'], plan['patch_sha256'],
                  plan['payload_manifest_sha256'], *plan['expected_protected_sha256'].values()]:
        require(isinstance(value, str) and HASH.fullmatch(value), 'plan_checksum')


def expected_metadata(plan):
    return {key:plan['expected_'+key] for key in ('schema', 'configuration_version', 'configuration_sha256')}


def assert_baseline(plan, gated_sha=None):
    require((ROOT/'current').is_symlink() and str((ROOT/'current').resolve()) == plan['expected_current'], 'baseline_current_changed')
    state = service()
    require(state['ActiveState'] == 'active' and state['SubState'] == 'running'
        and int(state['MainPID']) == plan['expected_api_pid'] and int(state['NRestarts']) == plan['expected_api_nrestarts'], 'baseline_service_changed')
    require(metadata() == expected_metadata(plan), 'runtime_configuration_changed_preserved')
    require(protected() == plan['expected_protected_sha256'], 'protected_configuration_changed_preserved')
    require(sha(INC) == (gated_sha or plan['expected_nginx_include_sha256']), 'nginx_include_changed_preserved')


def execute(plan):
    validate(plan)
    assert_baseline(plan)
    previous = Path(plan['expected_current'])
    release = ROOT/'releases'/plan['release_id']
    backup = ROOT/'shared/backups'/plan['run_id']
    log = ROOT/'shared/logs'/(plan['run_id']+'.json')
    require(not any(path.exists() or path.is_symlink() for path in (release, backup, log)), 'hotfix_identifier_used')
    archive_path = Path(plan['patch_archive_path'])
    require(archive_path.is_file() and not archive_path.is_symlink() and sha(archive_path) == plan['patch_sha256'], 'patch_hash_or_type')
    require(shutil.disk_usage(ROOT).free > 900*1024*1024, 'insufficient_release_disk_space')
    immutable = {name:tree(previous, name) for name in IMMUTABLE}
    backend_before = tree(previous, 'backend/app')
    release_info_before = sha(previous/'release-info.json')
    nginx_raw = INC.read_bytes(); gated = gate_bytes(nginx_raw); gated_sha = raw_sha(gated)
    st = INC.stat(); identity = (st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode))
    require(identity[0] == 0 and identity[2] == 0o644, 'nginx_include_identity')
    master = int(service('nginx')['MainPID'])
    before_service = service()
    report = dict(status='preparing', run_id=plan['run_id'], release_id=plan['release_id'],
        previous_release=str(previous), release=str(release), started_at=datetime.now(timezone.utc).isoformat(),
        stages=[], api_restart_attempts=0, environment_mutated=False, database_mutated=False,
        business_configuration_mutated=False, models_mutated=False, apk_mutated=False,
        nginx_temporarily_gated=False, nginx_restored=False, runtime_before=expected_metadata(plan), api_pid_before=plan['expected_api_pid'])
    gated_published = switched = restart_attempted = False
    def stage(name):
        report['stages'].append(name); print('STAGE '+name, flush=True)
    backup.mkdir(mode=0o700)
    private_write(backup/'nginx.before', nginx_raw)
    private_write(backup/'nginx.gated', gated)
    private_write(backup/'previous-release.txt', (str(previous)+'\n').encode())
    try:
        with tarfile.open(archive_path, 'r:gz') as archive:
            entries = archive.getmembers(); names = set(); total = 0
            for entry in entries:
                require(entry.isfile() and not entry.issparse() and entry.name not in names and allowed(entry.name), 'unsafe_patch_member')
                require(0 <= entry.size <= 20*1024*1024, 'patch_member_size')
                names.add(entry.name); total += entry.size
            require(len(entries) <= 1000 and total <= 100*1024*1024 and 'hotfix-files.json' in names, 'patch_archive_bounds')
            raw = archive.extractfile('hotfix-files.json').read(1024*1024+1)
            require(len(raw) <= 1024*1024 and raw_sha(raw) == plan['payload_manifest_sha256'], 'manifest_hash')
            manifest = json.loads(raw)
            require(isinstance(manifest, dict) and len(manifest) == plan['expected_payload_files']
                and names == set(manifest)|{'hotfix-files.json'}, 'manifest_exact_archive_members')
            require({'backend/app/schemas.py', 'backend/app/extensions.py', 'backend/app/admin.py', 'hotfix-info.json'} <= set(manifest), 'hotfix_critical_members')
            for name, checksum in manifest.items():
                require(allowed(name) and name != 'hotfix-files.json' and isinstance(checksum, str) and HASH.fullmatch(checksum), 'manifest_entry')
            shutil.copytree(previous, release, symlinks=True,
                ignore=lambda _path, names: {name for name in names if name == '__pycache__' or name.endswith(('.pyc', '.pyo'))})
            preserve_copied_ownership(previous, release)
            for entry in entries:
                if entry.name == 'hotfix-files.json':
                    continue
                path = target(release, entry.name)
                if '/assets/' in entry.name and path.exists():
                    require(sha(path) == manifest[entry.name], 'old_hashed_asset_would_change')
                path.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(entry) as source, path.open('wb') as output:
                    shutil.copyfileobj(source, output, 1024*1024)
                path.chmod(0o644)
                require(sha(path) == manifest[entry.name], 'payload_file_hash')
        expected_backend = dict(backend_before)
        expected_backend.update({name:value for name,value in manifest.items() if name.startswith('backend/app/')})
        require(tree(release, 'backend/app') == expected_backend, 'unexpected_backend_changes')
        for name, before in immutable.items():
            require(tree(release, name) == before, 'inherited_artifact_changed')
        require(sha(release/'release-info.json') == release_info_before, 'old_release_metadata_changed')
        service_readable(release)
        info = json.loads((release/'hotfix-info.json').read_text())
        require(info['release_id'] == plan['release_id'] and info['parent_release'] == str(previous), 'hotfix_metadata_identity')
        for key, prefix in (('workspace_entries', '/agriscan/workspace/'), ('admin_entries', '/agriscan/admin/')):
            require(isinstance(info[key], list) and info[key] and all(isinstance(value, str) and value.startswith(prefix) for value in info[key]), 'hotfix_entry_urls')
        stage('new_release_and_inherited_models_apk_verified')
        assert_baseline(plan)
        command(['nginx', '-t'], 'baseline_nginx_test_failed')
        publish_include(gated, plan['expected_nginx_include_sha256'], identity, plan['run_id']); gated_published = True
        report['nginx_temporarily_gated'] = True
        command(['nginx', '-t'], 'gate_nginx_test_failed')
        old_workers = reload_nginx(master)
        stage('new_detection_posts_temporarily_gated_existing_put_get_continue')
        drain(master, old_workers, report)
        stage('existing_detection_work_drained_and_reservations_expired')
        assert_baseline(plan, gated_sha)
        require(staging_empty() and established_api_connections() == 0, 'api_became_busy_no_restart')
        pointer(previous, release, plan['run_id']); switched = True
        stage('new_release_pointer_switched')
        restart_attempted = True; report['api_restart_attempts'] += 1
        command(['systemctl', 'restart', 'agriscan-api'], 'api_restart_failed', 330)
        report['health_after'] = health()
        after_service = service()
        require(after_service['ActiveState'] == 'active' and after_service['SubState'] == 'running'
            and int(after_service['MainPID']) != plan['expected_api_pid'] and after_service['NRestarts'] == '0'
            and after_service['MemoryMax'] == before_service['MemoryMax'], 'new_api_not_stable')
        require(metadata() == expected_metadata(plan) and protected() == plan['expected_protected_sha256'], 'post_restart_config_changed_preserved')
        require(sha(INC) == gated_sha and (ROOT/'current').resolve() == release, 'post_restart_pointer_or_nginx_changed')
        for name, before in immutable.items():
            require(tree(release, name) == before, 'post_restart_artifact_changed')
        stage('api_restarted_once_models_ready_runtime_unchanged')
        checks = {}
        for relative in ['workspace/index.html', 'admin/index.html']+[value.removeprefix('/agriscan/') for value in info['workspace_entries']+info['admin_entries']]:
            valid_name(relative)
            require(relative.startswith(('workspace/', 'admin/')), 'public_check_scope')
            status, body = request(PUBLIC+relative, timeout=25)
            require(status == 200 and body == target(release, 'public/'+relative).read_bytes(), 'public_static_check_failed')
            checks[relative] = {'status':status, 'sha256':raw_sha(body)}
        status, raw = request(PUBLIC+'api/auth/config')
        auth_config = json.loads(raw)
        require(status == 200 and auth_config.get('email_verification_enabled') is True
            and auth_config.get('registration_enabled') is True, 'registration_probe_needs_verification')
        status, raw = request(PUBLIC+'api/auth/register', dict(username='qa.registration+2026@example.invalid',
            name='QA registration validation', password='REDACTED_SECRET',
            email='qa.registration+2026@example.invalid', code='000000'))
        require(status == 400 and json.loads(raw).get('detail') == '验证码失效，请重新获取。', 'email_username_validation_probe_failed')
        report.update(status='passed', public_checks=checks, registration_probe=dict(status=400,
            username_accepted=True, otp_still_required=True, email_sent=False, account_created=False),
            api_pid_after=int(after_service['MainPID']), api_nrestarts_after=int(after_service['NRestarts']),
            inherited_models_apk_download_metadata_unchanged=True, runtime_after=metadata(),
            protected_configuration_sha256=protected(), changed_payload_files=len(manifest),
            nginx_master_before=master, nginx_master_after=int(service('nginx')['MainPID']))
        stage('public_registration_username_and_static_hotfix_verified')
    except BaseException as error:
        report.update(status='failed', error_code=str(error) if isinstance(error, Refused) else type(error).__name__, rolled_back=False)
        if switched:
            try:
                pointer(release, previous, plan['run_id']+'-rollback')
                if restart_attempted:
                    report['api_restart_attempts'] += 1
                    command(['systemctl', 'restart', 'agriscan-api'], 'rollback_restart_failed', 330)
                report['rollback_health'] = health()
                report['rolled_back'] = (ROOT/'current').resolve() == previous
            except BaseException as rollback_error:
                report['rollback_error'] = str(rollback_error) if isinstance(rollback_error, Refused) else type(rollback_error).__name__
    finally:
        if gated_published:
            try:
                publish_include(nginx_raw, gated_sha, identity, plan['run_id']+'-restore')
                command(['nginx', '-t'], 'restore_nginx_test_failed')
                reload_nginx(master)
                require(sha(INC) == plan['expected_nginx_include_sha256'], 'nginx_restore_hash')
                report['nginx_restored'] = True
                status, _raw = request(PUBLIC+'api/detection-tasks', data={})
                require(status == 401, 'public_detection_gate_restore_probe_failed')
                report['public_detection_gate_restored_probe'] = {'status':status, 'anonymous_request_denied':True}
            except BaseException as restore_error:
                report['status'] = 'failed'
                report['nginx_restore_error'] = str(restore_error) if isinstance(restore_error, Refused) else type(restore_error).__name__
        else:
            report['nginx_restored'] = sha(INC) == plan['expected_nginx_include_sha256']
        try:
            report['runtime_configuration_preserved'] = metadata() == expected_metadata(plan)
            report['protected_configuration_preserved'] = protected() == plan['expected_protected_sha256']
        except BaseException:
            report['status'] = 'failed'
            report['final_preservation_check_unavailable'] = True
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        private_write(log, json.dumps(report, ensure_ascii=False, indent=2).encode())
        private_write(backup/'report.json', json.dumps(report, ensure_ascii=False, indent=2).encode())
        print('RESULT '+json.dumps(report, ensure_ascii=False), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--plan-base64')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.inspect:
        require(not args.apply and not args.plan_base64, 'inspect_arguments')
        print('RESULT '+json.dumps(inspect()), flush=True)
        return 0
    require(args.apply and args.plan_base64, 'explicit_apply_and_plan_required')
    plan = json.loads(base64.b64decode(args.plan_base64, validate=True)); validate(plan)
    def interrupted(_signum, _frame):
        raise Refused('activation_interrupted')
    for name in ('SIGTERM', 'SIGHUP', 'SIGINT'):
        signal.signal(getattr(signal, name), interrupted)
    with (ROOT/'shared/dual-model-activation.lock').open('a') as lock:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        result = execute(plan)
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except BaseException as error:
        if isinstance(error, SystemExit):
            raise
        print('PRECHECK_FAILED '+(str(error) if isinstance(error, Refused) else type(error).__name__), flush=True)
        raise SystemExit(1)
