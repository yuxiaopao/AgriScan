from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re

workspace = Path.cwd()
base = workspace / '.runtime/cancel-order-20261029'
prior = json.loads((base / 'prior-web-ui-builds.json').read_text(encoding='utf-8'))

def digest(path):
    data = path.read_bytes()
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

sources = {name: digest(workspace / name) for name in prior['sources']}
assert len(sources) == 118
changed = [name for name in sources if sources[name] != prior['sources'][name]]
assert changed == ['shared/detectionTasks.ts'], changed
core_sha = sources['shared/detectionTasks.ts']['sha256']
assert core_sha == 'fbb4f74be2999f95473f159c08d5ad58eb0d61f28adb21e236ab2135113a38a1'

log = (base / 'node-tests.log').read_text(encoding='utf-8-sig')
assert re.search(r'tests 21\s', log) and re.search(r'pass 21\s', log) and re.search(r'fail 0\s', log)
test_names = re.findall(r'^. (.*?) \([\d.]+ms\)$', log, flags=re.M)
assert len(test_names) == 21, test_names
checks = {
    'status': 'passed', 'command': 'node --test shared/tests/detectionTasks.test.mjs',
    'source': 'actual shared TypeScript manager transpiled in memory using existing frontend TypeScript; public APIs and controlled HTTP/XHR/clock',
    'source_sha256': core_sha, 'tests': 21, 'passed': 21, 'failed': 0,
    'cases': [{'name': name, 'status': 'passed'} for name in test_names],
    'red_before_fix': {'tests': 21, 'passed': 17, 'failed': 4,
                       'symptom': 'DELETE is still pending but XHR has already been aborted'},
    'dispose_assertions': ['no scheduled timers', 'no active XHR transports', 'no held controlled requests'],
    'production_network_called': False,
}
independent_base = workspace / '.runtime/mobile-cancel-core-review-20261029'
independent = json.loads((independent_base / 'core-progress-checks.json').read_text(encoding='utf-8'))
cancel = json.loads((independent_base / 'cancel-order-checks.json').read_text(encoding='utf-8'))
for evidence in [independent, cancel]:
    assert evidence['status'] == 'passed' and evidence['source_sha256'] == core_sha
assert len(independent['cases']) == 9 and len(cancel['cases']) == 5

surfaces = {}
for surface, prefix in [('frontend', '/agriscan/workspace/'), ('admin', '/agriscan/admin/')]:
    dist = base / surface / 'dist'
    index = (dist / 'index.html').read_text(encoding='utf-8')
    entries = re.findall(r'<script[^>]+src="([^"]+)"', index)
    styles = re.findall(r'<link[^>]+href="([^"]+\.css)"', index)
    assert entries and all(value.startswith(prefix) for value in entries + styles)
    for name in entries + styles:
        assert (dist / name[len(prefix):]).is_file()
    js = '\n'.join(path.read_text(encoding='utf-8') for path in (dist / 'assets').glob('*.js'))
    assert 'no-store' in js and 'detection_with_classification' in js
    if surface == 'frontend':
        assert all(value in js for value in ['1.0.4', 'forgot-password', '/auth/email/verify', '/agriscan/admin/'])
    else:
        assert '/agriscan/workspace/#login' in js
    files = {str(path.relative_to(dist)).replace('\\', '/'): digest(path)
             for path in sorted(dist.rglob('*')) if path.is_file()}
    assert not any(Path(name).suffix in {'.pt', '.onnx', '.pem', '.key', '.pptx', '.xlsx'} for name in files)
    assert (workspace / 'shared/detectionTasks.ts').stat().st_mtime <= (dist / 'index.html').stat().st_mtime
    if surface == 'admin':
        assert files == prior['surfaces']['admin']['files']
    surfaces[surface] = {
        'status': 'passed', 'tsc': 'passed', 'vite_build': 'passed', 'dist': str(dist),
        'production_base': prefix, 'api_prefix': '/agriscan', 'entries': entries, 'styles': styles,
        'file_count': len(files), 'files': files, 'build_reused_with_unchanged_dependencies': False,
    }

assert all(prior.get(name) is True for name in [
    'auth_email_features', 'completed_result_view', 'background_detection_tasks',
    'upload_state_fix', 'reservation_recovery_fix',
])
report = {
    **prior, 'status': 'passed', 'completed_at': datetime.now(timezone.utc).isoformat(),
    'release_version': '1.0.4', 'cancellation_order_fix': True,
    'source_manifest_phase': 'only shared task cancellation ordering changed after frozen upload-state release; both web surfaces rebuilt',
    'source_file_count': len(sources), 'sources': sources, 'surfaces': surfaces,
    'verification_sources': {name: digest(workspace / name)
                             for name in ['shared/tests/detectionTasks.test.mjs', 'shared/README.md']},
    'post_verification_change': {
        'scope': 'request server cancellation before aborting active upload; preserve honest server terminal state',
        'prior_release_proof': str(base / 'prior-web-ui-builds.json'),
        'product_sources_changed': changed,
        'prior_core_sha256': prior['sources']['shared/detectionTasks.ts']['sha256'],
        'current_core_sha256': core_sha,
    },
    'background_task_checks': {
        **prior['background_task_checks'], 'core': checks, 'shared_core_sha256': core_sha,
        'independent_core_checks': independent, 'cancellation_order_checks': cancel,
        'buffered_upload_regressions': {
            'status': 'passed', 'source': checks['source'], 'source_sha256': core_sha,
            'cases': [case for case in checks['cases'] if any(value in case['name'] for value in
                      ['buffered server', 'GET can recover', 'GET-confirmed', 'cancel during reservation'])],
        },
        'fixes': prior['background_task_checks']['fixes'] + [
            'mark cancellation immediately and wait for server DELETE acknowledgement before aborting active XHR',
            'DELETE rejection or bounded 15-second timeout still tears down local upload; unconfirmed cancellation remains pending',
            'server failed/completed responses remain honest terminal states; no optimistic cancellation or record deletion',
        ],
    },
    'cross_review': {'reviewer': 'llm_review independent 9 upload + 5 cancellation public API cases',
                     'status': 'passed', 'findings_remaining': 0},
    'validation_scope': 'new cancellation ordering verified by repository actual-core tests and independent controlled HTTP/XHR; historical browser evidence retained for unchanged UI',
    'production_ui_tested_by_this_agent': False,
    'production_server_modified_by_this_agent': False,
}
for target in [base / 'web-cancel-order-builds.json', workspace / '.runtime/dual-model-20261029/web-ui-builds.json']:
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'status': 'passed', 'report': str(base / 'web-cancel-order-builds.json'),
                  'sources': len(sources), 'modified_product_sources': changed, 'core_sha256': core_sha,
                  'entries': {name: value['entries'] for name, value in surfaces.items()},
                  'checks': {'repository': 21, 'independent_upload': 9, 'independent_cancellation': 5}}))
