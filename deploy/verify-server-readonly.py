"""Read-only API cross-checks; the only POSTs open and revoke our own session."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import subprocess
import sys

import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--domain', default='agriscan.ming-ai.top')
    args = parser.parse_args()
    if not args.run_id.replace('_', '').isalnum():
        raise SystemExit('Invalid QA run id.')
    if not args.domain or any(character not in 'abcdefghijklmnopqrstuvwxyz0123456789.-' for character in args.domain):
        raise SystemExit('Domain must be a lowercase hostname, without a URL scheme or path.')
    spec = importlib.util.spec_from_file_location('smoke_helpers', Path(__file__).with_name('smoke-server.py'))
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    require = helpers.require
    report = {'run_id': args.run_id, 'kind': 'read_only_backend',
              'started_at': datetime.now(timezone.utc).isoformat(), 'checks': [], 'warnings': []}
    target = Path('/srv/agriscan/shared/logs') / (args.run_id + '-backend-readonly.json')
    token = None
    failed = False

    def checked(label):
        report['checks'].append(label)
        print('PASS:', label, flush=True)

    with httpx.Client(base_url='http://127.0.0.1:18000', trust_env=False,
                      follow_redirects=False, timeout=30) as client:
        def request(path, expected=200, authenticated=True, **kwargs):
            headers = {'Authorization': 'Bearer ' + token} if authenticated and token else {}
            response = client.get(path, headers=headers, **kwargs)
            require(response.status_code == expected,
                    f'GET {path} returned HTTP {response.status_code}; expected {expected}.')
            return response

        try:
            report['service_before'] = helpers.service_snapshot()
            health = request('/api/health', authenticated=False).json()
            require(health == {'status': 'ok', 'database': 'connected', 'redis': 'connected',
                               'mode': 'production', 'model': 'ready'}, 'Production health is degraded.')
            with Path('/srv/agriscan/current/model/model.onnx').open('rb') as source:
                require(hashlib.file_digest(source, 'sha256').hexdigest() == helpers.MODEL_SHA256,
                        'The deployed model bytes differ from the reviewed detector.')
            for path, status in [('/api/auth/me', 401), ('/api/models', 401), ('/api/detections', 401),
                                 ('/api/plots', 401), ('/api/knowledge', 401), ('/api/admin/config', 401),
                                 ('/api/admin/overview', 403), ('/api/admin/users', 403),
                                 ('/api/admin/detections/export.csv', 403), ('/api/admin/audit', 403)]:
                request(path, expected=status, authenticated=False)
            checked('production health, real ONNX file SHA256, service state, anonymous resource protection')

            credentials = helpers.login_values(Path('/srv/agriscan/shared/production.env'))
            login = client.post('/api/auth/login', json={'username': credentials['ADMIN_USERNAME'],
                                                        'password': credentials['ADMIN_PASSWORD']})
            credentials.clear()
            require(login.status_code == 200, 'Administrator login failed.')
            token = login.json().get('access_token')
            require(isinstance(token, str) and bool(token), 'Login did not return a session token.')
            require(request('/api/auth/me').json()['role'] == 'admin', 'Administrator role was not returned.')
            model = request('/api/models').json()
            require(model['status'] == 'ready' and model['active']['task'] == 'detect'
                    and model['active']['onnx_sha256'] == helpers.MODEL_SHA256
                    and model['active']['test_top1'] is None and model['active']['test_macro_f1'] is None,
                    'Model API task/hash/metric semantics differ from the deployed detector.')
            report['model'] = {'task': model['active']['task'], 'sha256': model['active']['onnx_sha256'],
                               'class_count': model['active']['class_count']}
            checked('administrator login/me and active detector API hash with no reused classification metrics')

            public = request('/api/client/config', authenticated=False).json()
            admin = request('/api/admin/config').json()
            helpers.validate_public(public)
            helpers.validate_admin(admin)
            require(all(public[group] == admin[group] for group in ('brand', 'features', 'limits')),
                    'Public and administrative configuration groups disagree.')
            report['configuration_version_start'] = admin['version']
            users = request('/api/admin/users?page_size=100').json()
            require(all(not ({'password', 'password_hash', 'token_version', 'access_token'} & set(row))
                        for row in users['items']), 'User listing discloses credential material.')
            overview = request('/api/admin/overview?days=7').json()
            require(len(overview['trend']) == 7 and overview['services'] == {
                'database': 'connected', 'redis': 'connected', 'model': 'ready'}, 'Administrative overview services/trend are invalid.')
            report['counts_at_read'] = overview['counts']
            checked('public configuration excludes integrations, write-only secret flags, user privacy, administrative overview')

            invalid_reads = [
                '/api/dashboard?days=4', '/api/detections?status=unknown', '/api/detections?crop=unknown',
                '/api/admin/overview?days=8', '/api/admin/users?page=0', '/api/admin/users?page_size=101',
                '/api/admin/users?role=unknown', '/api/admin/users?status=active&is_active=false',
                '/api/admin/detections?page_size=0', '/api/admin/detections?source=unknown',
                '/api/admin/detections?date_from=2026-10-29&date_to=2026-10-28',
                '/api/admin/detections/export.csv?date_from=2026-10-29&date_to=2026-10-28',
                '/api/admin/knowledge?status=unknown', '/api/admin/plots?crop=unknown',
            ]
            for path in invalid_reads:
                request(path, expected=422)
            for path in ('/api/detections/qa-nonexistent-record', '/api/uploads/../../production.env',
                         '/api/uploads/00000000000000000000000000000000.jpg'):
                request(path, expected=404)
            checked('14 invalid GET filters/date/pagination boundaries return 422; missing and path-traversal resources return 404')

            filters = {'search': args.run_id, 'source': 'real'}
            listing = request('/api/admin/detections', params={**filters, 'page_size': 100}).json()
            exported = request('/api/admin/detections/export.csv', params=filters)
            require(exported.content.startswith(b'\xef\xbb\xbf')
                    and exported.headers.get('content-type', '').startswith('text/csv')
                    and exported.headers.get('cache-control') == 'no-store', 'CSV encoding/headers are invalid.')
            rows = list(csv.DictReader(io.StringIO(exported.content.decode('utf-8-sig'), newline='')))
            require(list(rows[0]) == ['id', 'name', 'crop', 'plot_name', 'status', 'result', 'confidence',
                                     'created_at', 'is_demo', 'note', 'owner_id', 'owner_username', 'owner_name'] if rows else
                    exported.content.decode('utf-8-sig').startswith('id,name,crop,plot_name,status,result,confidence,created_at,is_demo,note,owner_id,owner_username,owner_name'),
                    'CSV schema differs from its API contract.')
            for row in rows:
                require(not any(value.lstrip(' \t\r\n').startswith(('=', '+', '-', '@'))
                                for value in row.values()), 'CSV contains an unescaped spreadsheet formula prefix.')
            if listing['total'] <= 100 and {row['id'] for row in rows} != {row['id'] for row in listing['items']}:
                latest = request('/api/admin/detections', params={**filters, 'page_size': 100}).json()
                require({row['id'] for row in rows} == {row['id'] for row in latest['items']},
                        'CSV differs from both the before/after filtered listing.')
                report['warnings'].append('QA records changed between list and CSV reads; CSV matched the latest list.')
            report['qa_filtered_detection_count'] = len(rows)
            report['qa_record_ids_read'] = [row['id'] for row in rows]
            if listing['items']:
                row = listing['items'][0]
                if row.get('boxes'):
                    require(row.get('prediction_model', {}).get('task') == 'detect',
                            'An existing QA result has boxes without detection task metadata.')
                    for box in row['boxes']:
                        coordinates = box.get('bbox', [])
                        require(len(coordinates) == 4
                                and all(isinstance(value, (float, int)) and math.isfinite(value)
                                        and 0 <= value <= 1 for value in coordinates)
                                and coordinates[0] < coordinates[2] and coordinates[1] < coordinates[3],
                                'A persisted QA box violates the normalized original-image rectangle contract.')
                    require(request('/api/admin/detections/' + row['id']).json()['boxes'] == row['boxes'],
                            'Persisted boxes changed between administrative and user reads.')
                if row.get('image_url'):
                    require(request(row['image_url']).headers.get('content-type', '').startswith('image/'),
                            'An existing QA image is not readable by its authenticated user.')
                    request(row['image_url'], expected=401, authenticated=False)
            checked('filtered CSV matches real QA records with BOM/no-store/formula escaping; available saved boxes/images stay protected')

            tls = subprocess.run(['curl', '--silent', '--show-error', '--noproxy', '*', '--fail',
                                  '--connect-timeout', '10', '--max-time', '30', '--resolve',
                                  f'{args.domain}:443:127.0.0.1', f'https://{args.domain}/agriscan/api/health'],
                                 capture_output=True, timeout=35)
            require(tls.returncode == 0 and json.loads(tls.stdout) == health,
                    'Verified source Nginx HTTPS health failed.')
            report['https'] = {'domain': args.domain, 'resolve_ip': '127.0.0.1', 'certificate_verification': True}
            report['configuration_version_finish'] = request('/api/admin/config').json()['version']
            report['service_after'] = helpers.service_snapshot()
            require(report['service_before']['MainPID'] == report['service_after']['MainPID']
                    and report['service_before']['NRestarts'] == report['service_after']['NRestarts'],
                    'Service process restarted during read-only verification.')
            checked('source Nginx HTTPS with certificate verification, stable PID/restart count, memory snapshot')
        except Exception as error:
            failed = True
            message = str(error) if isinstance(error, helpers.SmokeFailure) else type(error).__name__
            report['failure'] = message
            print('FAIL:', message, flush=True)
        finally:
            if token:
                try:
                    response = client.post('/api/auth/logout', headers={'Authorization': 'Bearer ' + token})
                    require(response.status_code == 200, 'Temporary verification session could not be revoked.')
                    request('/api/auth/me', expected=401)
                    checked('only the verification session was revoked; no data/configuration mutation requests were sent')
                except Exception as error:
                    report['warnings'].append('Session cleanup failed: ' + type(error).__name__)
            report['finished_at'] = datetime.now(timezone.utc).isoformat()
            report['status'] = 'failed' if failed else ('passed_with_warnings' if report['warnings'] else 'passed')
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print('Report:', target, flush=True)
    return 1 if failed or report['warnings'] else 0


if __name__ == '__main__':
    sys.exit(main())
