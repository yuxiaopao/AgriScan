"""Run an owned, reversible production smoke after release activation.

Run on the AgriScan host with its venv Python. Passwords and tokens stay in memory;
only ADMIN_USERNAME/ADMIN_PASSWORD are selected from the private environment file.
No service, release symlink, Nginx configuration, or pre-existing record is changed.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

import httpx
from PIL import Image


MODEL_SHA256 = 'ff623c94555ade8c08a425caee3fe6fba5465ebc61ebd81ee502376bca8d4773'
FIXTURE_SHA256 = '5d7236ea8400b9b6093b51a860ebf4844d78b961e1505b6e64520a29fcef4427'
PUBLIC_KEYS = {'brand', 'features', 'limits', 'registration_enabled',
               'email_verification_enabled', 'version'}
INTEGRATION_KEYS = {
    'registration_enabled', 'email_verification_enabled', 'smtp_host', 'smtp_port',
    'smtp_username', 'smtp_from', 'smtp_security', 'smtp_password_configured',
    'llm_enabled', 'llm_base_url', 'llm_model', 'llm_timeout', 'llm_key_configured',
    'model_max_mb',
}


class SmokeFailure(RuntimeError):
    """Contains only an intentionally safe diagnostic, never a response body."""


def require(condition, message):
    if not condition:
        raise SmokeFailure(message)


def login_values(env_file):
    selected = {}
    with env_file.open(encoding='utf-8') as source:
        for line in source:
            key, separator, value = line.rstrip('\r\n').partition('=')
            if separator and key in {'ADMIN_USERNAME', 'ADMIN_PASSWORD'}:
                selected[key] = value.strip().strip('\"\'')
    require(all(selected.get(key) for key in ('ADMIN_USERNAME', 'ADMIN_PASSWORD')),
            'Private environment file lacks the required administrator login values.')
    return selected


def validate_public(data):
    require(isinstance(data, dict) and set(data) == PUBLIC_KEYS,
            'Public configuration contains an unexpected field or lacks its contract.')
    require(set(data['brand']) == {'app_name', 'tagline', 'announcement'},
            'Public brand fields differ from the public contract.')
    require(set(data['features']) == {'image_detection', 'video_detection', 'live_detection',
                                     'assistant', 'knowledge', 'plots'},
            'Public feature fields differ from the public contract.')
    require(set(data['limits']) == {'image_max_mb', 'video_max_mb', 'video_max_seconds',
                                   'video_max_frames', 'frame_interval_ms'},
            'Public limit fields differ from the public contract.')


def validate_admin(data):
    require(set(data) == {'brand', 'features', 'limits', 'integrations', 'version'},
            'Administrator configuration has unexpected fields.')
    require(set(data['integrations']) == INTEGRATION_KEYS,
            'Administrator integrations expose unexpected fields or lack configured flags.')
    for field in ('smtp_password_configured', 'llm_key_configured'):
        require(type(data['integrations'][field]) is bool, 'Secret configured flag is not boolean.')


def validate_boxes(row):
    require(row.get('prediction_model', {}).get('task') == 'detect',
            'A created detection does not identify the real detection model.')
    require(row.get('prediction_model', {}).get('onnx_sha256') == MODEL_SHA256,
            'A detection was produced by an unexpected ONNX artifact.')
    boxes = row.get('boxes')
    require(isinstance(boxes, list) and bool(boxes), 'The real leaf image has no target boxes.')
    for box in boxes:
        coordinates = box.get('bbox')
        require(isinstance(coordinates, list) and len(coordinates) == 4
                and all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1
                        for v in coordinates), 'A box is not finite normalized xyxy.')
        require(coordinates[0] < coordinates[2] and coordinates[1] < coordinates[3],
                'A target rectangle has no positive area.')
        require(isinstance(box.get('confidence'), (int, float))
                and 0.25 <= box['confidence'] <= 1, 'A target score is outside the detector contract.')
    require(row.get('is_demo') is False and row.get('plot_id') is None,
            'A smoke detection was marked as demo or associated with an existing plot.')


def service_snapshot():
    names = ['agriscan-api', 'mysqld', 'agriscan-redis']
    result = subprocess.run(['systemctl', 'is-active', *names], capture_output=True, text=True, timeout=15)
    states = result.stdout.splitlines()
    require(result.returncode == 0 and states == ['active'] * len(names),
            'AgriScan API, MySQL, or isolated Redis is not active.')
    result = subprocess.run(['systemctl', 'show', 'agriscan-api',
                             '--property=MainPID,NRestarts,MemoryCurrent,MemoryPeak,ActiveState,SubState'],
                            capture_output=True, text=True, timeout=15, check=True)
    data = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    require(data.get('ActiveState') == 'active' and data.get('SubState') == 'running'
            and int(data.get('MainPID', '0')) > 0, 'The API service is not running persistently.')
    for key in ('MainPID', 'NRestarts', 'MemoryCurrent', 'MemoryPeak'):
        if str(data.get(key, '')).isdigit():
            data[key] = int(data[key])
    status = Path(f"/proc/{data['MainPID']}/status")
    if status.exists():
        for line in status.read_text().splitlines():
            if line.startswith(('VmRSS:', 'VmHWM:')):
                key, value, _unit = line.split()
                data[key.rstrip(':') + '_bytes'] = int(value) * 1024
    data['mysql'] = data['redis'] = 'active'
    return data


class Smoke:
    def __init__(self, args):
        self.args = args
        self.run_id = 'server-smoke-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid4().hex[:8]
        self.report = {'run_id': self.run_id, 'started_at': datetime.now(timezone.utc).isoformat(),
                       'checks': [], 'created_ids': [], 'deleted_ids': [], 'warnings': []}
        self.report_path = args.report_dir / (self.run_id + '.json')
        self.owned = {}
        self.original = self.applied = None
        self.token = None
        self.client = httpx.Client(base_url='http://127.0.0.1:18000', trust_env=False,
                                   follow_redirects=False, timeout=120)

    def save(self):
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.report_path.with_suffix('.json.next')
        temporary.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(self.report_path)

    def checked(self, label):
        self.report['checks'].append(label)
        self.save()
        print('PASS:', label, flush=True)

    def request(self, method, path, expected=200, authenticated=True, **kwargs):
        headers = kwargs.pop('headers', {})
        if authenticated:
            require(bool(self.token), 'An authenticated request has no administrator session.')
            headers['Authorization'] = 'Bearer ' + self.token
        response = self.client.request(method, path, headers=headers, **kwargs)
        require(response.status_code == expected,
                f'{method} {path.split("?")[0]} returned HTTP {response.status_code}; expected {expected}.')
        return response

    def public_get(self, path, authenticated=False):
        # TLS hostname/chain verification stays enabled; --resolve targets this host's Nginx.
        url = 'https://' + self.args.domain + self.args.prefix + path.removeprefix('/api')
        config = ''
        if authenticated:
            require(bool(self.token), 'An HTTPS request has no administrator session.')
            config = 'header = "Authorization: Bearer ' + self.token + '"\n'
        result = subprocess.run(['curl', '--silent', '--show-error', '--noproxy', '*',
                                 '--connect-timeout', '10', '--max-time', '120',
                                 '--resolve', self.args.domain + ':443:' + self.args.resolve_ip,
                                 '--config', '-', '--write-out', '\n%{http_code}', url],
                                input=config.encode(), capture_output=True, timeout=125)
        require(result.returncode == 0, 'Verified HTTPS request to the source Nginx failed.')
        payload, separator, status = result.stdout.rpartition(b'\n')
        require(separator and status.isdigit(), 'HTTPS response lacks a valid status code.')
        return int(status), payload

    def upload(self, image, filename, note):
        response = self.client.post('/api/detections',
                                    headers={'Authorization': 'Bearer ' + self.token},
                                    data={'note': note}, files={'file': (filename, image, 'image/jpeg')})
        # Track any unexpectedly successful POST too, so cleanup never misses a test record.
        if response.status_code == 201:
            row = response.json()
            detection_id = row.get('id')
            require(isinstance(detection_id, str) and bool(re.fullmatch(r'[0-9a-f]{32}', detection_id)),
                    'A created detection has an invalid id; automatic deletion was refused.')
            self.owned[detection_id] = note
            self.report['created_ids'].append(detection_id)
            self.save()
        return response

    def configuration_test(self, row, leaf):
        self.original = self.request('GET', '/api/admin/config').json()
        validate_admin(self.original)
        brand, features = deepcopy(self.original['brand']), deepcopy(self.original['features'])
        brand['announcement'] = self.run_id + ' 临时部署验收，将按版本恢复。'
        features.update(image_detection=False, live_detection=False)
        patch = {'version': self.original['version'], 'brand': brand, 'features': features}
        self.applied = self.request('PATCH', '/api/admin/config', json=patch).json()
        validate_admin(self.applied)
        require(self.applied['version'] == self.original['version'] + 1,
                'Configuration save did not increment the optimistic version.')
        self.report['config_changed_version'] = self.applied['version']
        self.save()
        public = self.request('GET', '/api/client/config', authenticated=False).json()
        validate_public(public)
        require(public['brand'] == brand and public['features'] == features,
                'Public configuration did not publish the temporary announcement and feature changes.')
        self.request('PATCH', '/api/admin/config', expected=409, json=patch)
        disabled = self.upload(leaf, self.run_id + '-disabled.jpg', self.run_id + '-disabled')
        require(disabled.status_code == 403, 'Disabled image detection accepted a new operation.')
        self.request('POST', '/api/media/frame', expected=403, content=b'')
        require(self.request('GET', '/api/detections/' + row['id']).json()['boxes'] == row['boxes'],
                'Disabling new operations unexpectedly blocked detection history.')
        self.request('GET', row['image_url'])
        capabilities = self.request('GET', '/api/media/capabilities', authenticated=False).json()
        require(capabilities['live_enabled'] is False, 'Live feature capability did not reflect its switch.')
        self.checked('announcement and image/live switches; public refresh, 403 gates, readable history, stale-version 409')

    def restore_configuration(self):
        if self.applied is None:
            return
        current = self.request('GET', '/api/admin/config').json()
        if current['version'] != self.applied['version']:
            self.report['warnings'].append('Configuration changed concurrently; restoration was not attempted or forced.')
            self.report['config_restore'] = 'skipped_concurrent_change'
            self.save()
            return
        body = {'version': self.applied['version'], 'brand': self.original['brand'],
                'features': self.original['features']}
        response = self.client.patch('/api/admin/config', headers={'Authorization': 'Bearer ' + self.token}, json=body)
        if response.status_code == 409:
            self.report['warnings'].append('Configuration restore returned 409; another administrator update was preserved.')
            self.report['config_restore'] = 'conflict_409'
        else:
            require(response.status_code == 200, 'Configuration restoration failed; inspect the smoke report.')
            restored = response.json()
            require(restored['brand'] == self.original['brand'] and restored['features'] == self.original['features'],
                    'Restored public groups differ from the original groups.')
            self.report['config_restore'] = 'restored'
            self.report['config_restored_version'] = restored['version']
            self.checked('original announcement and feature switches restored with version check')
        self.applied = None
        self.save()

    def cleanup(self):
        if self.token:
            try:
                self.restore_configuration()
            except Exception as error:
                self.report['warnings'].append('Configuration cleanup failed: ' + type(error).__name__)
            for detection_id, note in self.owned.items():
                try:
                    response = self.request('GET', '/api/detections/' + detection_id)
                    row = response.json()
                    require(row.get('note') == note and note.startswith(self.run_id),
                            'Record ownership changed; deletion refused.')
                    self.request('DELETE', '/api/detections/' + detection_id)
                    self.report['deleted_ids'].append(detection_id)
                    self.request('GET', '/api/detections/' + detection_id, expected=404)
                    self.request('GET', row['image_url'], expected=404)
                except Exception as error:
                    self.report['warnings'].append('Owned record cleanup failed: ' + detection_id + ' (' + type(error).__name__ + ')')
            try:
                self.request('POST', '/api/auth/logout')
                self.checked('temporary session revoked; only owned detection ids and their images deleted')
            except Exception as error:
                self.report['warnings'].append('Session revocation failed: ' + type(error).__name__)
        self.client.close()
        self.save()

    def run(self):
        leaf = self.args.fixture.read_bytes()
        require(hashlib.sha256(leaf).hexdigest() == FIXTURE_SHA256,
                'The held-out Apple scab fixture SHA256 differs from the reviewed source.')
        self.report['fixture_sha256'] = FIXTURE_SHA256
        before_service = service_snapshot()
        self.report['service_before'] = before_service
        health = self.request('GET', '/api/health', authenticated=False).json()
        require(health == {'status': 'ok', 'database': 'connected', 'redis': 'connected',
                           'mode': 'production', 'model': 'ready'}, 'Health is not production/ready with MySQL and Redis connected.')
        for path in ('/api/auth/me', '/api/models', '/api/detections', '/api/admin/config'):
            self.request('GET', path, expected=401, authenticated=False)
        self.checked('persistent API/MySQL/Redis services, production health, anonymous API protection')
        credentials = login_values(self.args.env_file)
        response = self.request('POST', '/api/auth/login', authenticated=False,
                                json={'username': credentials['ADMIN_USERNAME'], 'password': credentials['ADMIN_PASSWORD']})
        self.token = response.json().get('access_token')
        credentials.clear()
        require(isinstance(self.token, str) and bool(self.token), 'Login did not return a session token.')
        require(self.request('GET', '/api/auth/me').json().get('role') == 'admin', 'The login account is not an administrator.')
        models = self.request('GET', '/api/models').json()
        require(models.get('status') == 'ready' and models.get('active', {}).get('task') == 'detect'
                and models['active'].get('onnx_sha256') == MODEL_SHA256,
                'The expected real detector is not active.')
        validate_public(self.request('GET', '/api/client/config', authenticated=False).json())
        validate_admin(self.request('GET', '/api/admin/config').json())
        self.checked('administrator login/me, expected real detector, public/private configuration disclosure contracts')

        response = self.upload(leaf, self.run_id + '-apple.jpg', self.run_id + '-leaf')
        require(response.status_code == 201, 'The real held-out Apple leaf image was not accepted.')
        row = response.json()
        validate_boxes(row)
        require(row['crop'] == '苹果' and row['result'] == '苹果黑星病', 'The reviewed Apple fixture has an unexpected primary detection.')
        stored = self.request('GET', '/api/detections/' + row['id']).json()
        require(stored == row, 'GET detection differs from the saved response or changes box coordinates.')
        image = self.request('GET', row['image_url'])
        require(image.headers.get('content-type', '').startswith('image/jpeg'), 'Saved original is not served as JPEG.')
        with Image.open(io.BytesIO(image.content)) as saved:
            require(saved.size == (256, 256), 'Saved image dimensions differ from the reviewed coordinate basis.')
            saved.verify()
        self.request('GET', row['image_url'], expected=401, authenticated=False)
        self.report['detection'] = {key: row[key] for key in ('id', 'crop', 'result', 'confidence', 'boxes')}
        self.checked('real Apple target boxes, normalized original coordinates, identical persistence, protected saved original')

        background = io.BytesIO()
        Image.new('RGB', (640, 640), 'black').save(background, 'JPEG')
        invalid_note = self.run_id + '-background'
        invalid = self.upload(background.getvalue(), self.run_id + '-background.jpg', invalid_note)
        require(invalid.status_code == 422, 'A blank background was not rejected as lacking a reliable target.')
        rows = self.request('GET', '/api/detections').json()
        require(not any(item.get('note') == invalid_note for item in rows), 'The rejected background created a record.')
        self.checked('blank background returns 422 without a corresponding database record')

        status, payload = self.public_get('/api/health')
        require(status == 200 and json.loads(payload) == health, 'Verified source HTTPS health differs from local health.')
        status, payload = self.public_get('/api/client/config')
        require(status == 200, 'Public configuration is unavailable through verified source HTTPS.')
        validate_public(json.loads(payload))
        status, _payload = self.public_get(row['image_url'])
        require(status == 401, 'The source Nginx exposes a saved image without authentication.')
        status, payload = self.public_get(row['image_url'], authenticated=True)
        require(status == 200 and hashlib.sha256(payload).digest() == hashlib.sha256(image.content).digest(),
                'Authenticated source HTTPS image differs from the saved original.')
        self.report['https'] = {'domain': self.args.domain, 'resolved_ip': self.args.resolve_ip,
                               'certificate_verification': True, 'api_prefix': self.args.prefix}
        self.checked('source Nginx via HTTPS Host/SNI and --resolve, valid certificate, identical protected image')

        self.configuration_test(row, leaf)
        self.restore_configuration()
        after_service = service_snapshot()
        require(after_service['MainPID'] == before_service['MainPID']
                and after_service['NRestarts'] == before_service['NRestarts'],
                'The API service restarted or changed its main process during smoke.')
        self.report['service_after'] = after_service
        self.checked('API remained running with unchanged PID/restart count; service and process memory peak captured')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=Path('/srv/agriscan/shared/production.env'))
    parser.add_argument('--fixture', type=Path, default=Path(__file__).with_name('smoke-apple-scab.jpg'))
    parser.add_argument('--report-dir', type=Path, default=Path('/srv/agriscan/shared/logs'))
    parser.add_argument('--domain', default='flowly-ai.top')
    parser.add_argument('--resolve-ip', default='127.0.0.1', choices=['127.0.0.1'])
    parser.add_argument('--prefix', default='/agriscan/api')
    args = parser.parse_args()
    require(bool(re.fullmatch(r'[A-Za-z0-9.-]+', args.domain)), 'Invalid HTTPS hostname.')
    require(bool(re.fullmatch(r'/[A-Za-z0-9/_-]*api', args.prefix)), 'Invalid public API prefix.')
    smoke = Smoke(args)
    failed = False
    try:
        smoke.run()
    except Exception as error:
        failed = True
        # A transport/library exception may contain request data. Never print it.
        message = str(error) if isinstance(error, SmokeFailure) else type(error).__name__
        smoke.report['failure'] = message
        print('FAIL:', message, flush=True)
    finally:
        smoke.cleanup()
        smoke.report['finished_at'] = datetime.now(timezone.utc).isoformat()
        smoke.report['status'] = 'failed' if failed else ('passed_with_warnings' if smoke.report['warnings'] else 'passed')
        smoke.save()
    print('Report:', smoke.report_path, flush=True)
    for warning in smoke.report['warnings']:
        print('WARNING:', warning, flush=True)
    return 1 if failed or smoke.report['warnings'] else 0


if __name__ == '__main__':
    sys.exit(main())
