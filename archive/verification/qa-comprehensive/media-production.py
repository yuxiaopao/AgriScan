"""One bounded real-media smoke; exact returned IDs only are cleaned up."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

import cv2
from dotenv import dotenv_values
import httpx

FOLDER = Path(__file__).resolve().parent
MARKER = 'qa20261028_1935_media'
BASE = 'https://flowly-ai.top/agriscan/api'
REPORT = FOLDER / 'media-production.json'
report = {
    'marker': MARKER, 'origin': BASE, 'source': 'Real production-server HTTPS API functional supplement over SSH; not APP or public-browser video interaction',
    'tlsVerification': True, 'appTested': False, 'cameraPermissionRequested': False,
    'startedAt': datetime.now(timezone.utc).isoformat(), 'recordIds': [], 'cleanup': [],
    'modelChanged': False, 'configurationChanged': False, 'usersCreated': False,
}
own_rows = []
baseline_ids = None
authenticated = False
failures = []


def save():
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')


def need(condition, label):
    if not condition:
        raise AssertionError(label)


def checked(response, label):
    need(response.status_code == 200, f'{label}_HTTP_{response.status_code}')
    return response


def summarize(row):
    boxes = row.get('boxes') or []
    need(row.get('crop') == '苹果', 'EXPECTED_APPLE_CROP')
    need(bool(boxes), 'MISSING_REAL_BOXES')
    for box in boxes:
        coords = box.get('bbox', [])
        need(len(coords) == 4 and all(0 <= value <= 1 for value in coords), 'INVALID_NORMALIZED_BOX')
        need(coords[0] < coords[2] and coords[1] < coords[3], 'EMPTY_BOX')
        need(box.get('crop') == '苹果', 'EXPECTED_APPLE_BOX')
    model = row.get('prediction_model') or {}
    need(model.get('task') == 'detect', 'EXPECTED_REAL_DETECTOR')
    return {key: row.get(key) for key in ('id', 'crop', 'result', 'confidence', 'boxes', 'prediction_model', 'image_url', 'note')}


with httpx.Client(base_url=BASE, timeout=150, trust_env=False, follow_redirects=False) as client:
    try:
        settings = dotenv_values('/srv/agriscan/shared/production.env')
        credentials = {'username': settings['ADMIN_USERNAME'], 'password': settings['ADMIN_PASSWORD']}
        response = checked(client.post('/auth/login', json=credentials), 'LOGIN')
        credentials.clear()
        settings.clear()
        client.headers['Authorization'] = 'Bearer ' + response.json()['access_token']
        authenticated = True
        report['loginStatus'] = response.status_code
        baseline = checked(client.get('/detections'), 'BASELINE').json()
        baseline_ids = {row['id'] for row in baseline}
        report['baseline'] = {'count': len(baseline_ids), 'ids': sorted(baseline_ids)}
        report['capabilities'] = checked(client.get('/media/capabilities'), 'CAPABILITIES').json()
        print('Authenticated production HTTPS session; baseline recorded.', flush=True)

        image = FOLDER / 'leaf.jpg'
        report['input'] = {'sha256': hashlib.sha256(image.read_bytes()).hexdigest(), 'bytes': image.stat().st_size}
        with image.open('rb') as source:
            response = checked(client.post('/media/frame', files={'file': (MARKER + '.jpg', source, 'image/jpeg')}), 'FRAME')
        frame = response.json()
        report['frame'] = {'status': response.status_code, 'result': summarize(frame)}
        after_frame = checked(client.get('/detections'), 'AFTER_FRAME').json()
        after_frame_ids = {row['id'] for row in after_frame}
        need(frame['id'] not in after_frame_ids, 'FRAME_PREVIEW_WAS_SAVED')
        need(frame.get('image_url') is None, 'FRAME_HAS_STORED_IMAGE')
        need(baseline_ids.issubset(after_frame_ids), 'BASELINE_RECORD_MISSING_AFTER_FRAME')
        report['frame']['previewNotPersisted'] = True
        report['frame']['countAfterPreview'] = len(after_frame_ids)

        source = cv2.imread(str(image))
        need(source is not None, 'SOURCE_DECODE_FAILED')
        height, width = source.shape[:2]
        width, height = width - width % 2, height - height % 2
        source = source[:height, :width]
        video = FOLDER / (MARKER + '_2frames.mp4')
        writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*'mp4v'), 2.0, (width, height))
        need(writer.isOpened(), 'VIDEO_WRITER_FAILED')
        try:
            writer.write(source)
            writer.write(source)
        finally:
            writer.release()
        report['videoInput'] = {'frames': 2, 'fps': 2.0, 'durationSeconds': 1.0, 'width': width, 'height': height, 'bytes': video.stat().st_size}
        with video.open('rb') as source_file:
            response = checked(client.post('/media/video', files={'file': (video.name, source_file, 'video/mp4')}, data={'note': MARKER}), 'VIDEO')
        value = response.json()
        own_rows = [entry['detection'] for entry in value.get('results', [])]
        report['recordIds'] = [row['id'] for row in own_rows]
        save()
        need(value.get('sampled_frames') == 2 and len(own_rows) == 2, 'EXPECTED_TWO_SAMPLED_FRAMES')
        need(0 < value.get('duration_seconds', 0) <= 1.0, 'VIDEO_DURATION_OUT_OF_BOUND')
        report['video'] = {'status': response.status_code, 'durationSeconds': value['duration_seconds'], 'sampledFrames': value['sampled_frames'], 'timestamps': [entry['timestamp_seconds'] for entry in value['results']], 'results': []}
        for row in own_rows:
            need(row['id'] not in baseline_ids, 'RETURNED_PREEXISTING_RECORD')
            need(row.get('note', '').startswith(MARKER), 'OWN_RECORD_MARKER_MISSING')
            persisted = checked(client.get('/detections/' + row['id']), 'PERSISTED_DETAIL').json()
            need(persisted.get('boxes') == row.get('boxes'), 'BOX_SNAPSHOT_CHANGED')
            image_url = row.get('image_url') or ''
            need(image_url.startswith('/api/uploads/'), 'INVALID_STORED_IMAGE_PATH')
            original = checked(client.get(image_url.removeprefix('/api')), 'PERSISTED_IMAGE')
            need(original.headers.get('content-type', '').startswith('image/jpeg'), 'INVALID_STORED_IMAGE_TYPE')
            result = summarize(persisted)
            result['originalImageStatus'] = original.status_code
            result['originalImageSha256'] = hashlib.sha256(original.content).hexdigest()
            report['video']['results'].append(result)
        need(report['video']['timestamps'] == [0.0, 0.5], 'INCORRECT_SAMPLING_TIMESTAMPS')
        report['checksPassed'] = True
        print('Frame preview and two-frame video inferred real apple boxes; cleaning exact returned IDs.', flush=True)
    except Exception as error:
        failures.append(str(error) if isinstance(error, AssertionError) else type(error).__name__)
    finally:
        if authenticated:
            for row in own_rows:
                cleanup = {'id': row['id']}
                try:
                    need(baseline_ids is not None and row['id'] not in baseline_ids, 'REFUSE_BASELINE_DELETE')
                    need(row.get('note', '').startswith(MARKER), 'REFUSE_UNMARKED_DELETE')
                    cleanup['deleteStatus'] = client.delete('/detections/' + row['id']).status_code
                    cleanup['detailAfterDelete'] = client.get('/detections/' + row['id']).status_code
                    cleanup['imageAfterDelete'] = client.get(row['image_url'].removeprefix('/api')).status_code
                    need(cleanup['deleteStatus'] == 200 and cleanup['detailAfterDelete'] == 404 and cleanup['imageAfterDelete'] == 404, 'EXACT_CLEANUP_FAILED')
                except Exception as error:
                    failures.append(str(error) if isinstance(error, AssertionError) else type(error).__name__)
                report['cleanup'].append(cleanup)
            try:
                final = checked(client.get('/detections'), 'FINAL_LIST').json()
                final_ids = {row['id'] for row in final}
                report['final'] = {'count': len(final_ids), 'ids': sorted(final_ids), 'baselinePreserved': baseline_ids.issubset(final_ids), 'ownRecordsRemaining': sorted(final_ids.intersection(report['recordIds'])), 'concurrentNonTestIds': sorted(final_ids - baseline_ids - set(report['recordIds']))}
                need(baseline_ids.issubset(final_ids), 'FINAL_BASELINE_RECORD_MISSING')
                need(not final_ids.intersection(report['recordIds']), 'OWN_RECORD_REMAINS')
            except Exception as error:
                failures.append(str(error) if isinstance(error, AssertionError) else type(error).__name__)
            try:
                report['logoutStatus'] = client.post('/auth/logout').status_code
                need(report['logoutStatus'] == 200, 'LOGOUT_FAILED')
                report['sessionAfterLogout'] = client.get('/auth/me').status_code
                need(report['sessionAfterLogout'] == 401, 'LOGOUT_TOKEN_STILL_VALID')
            except Exception as error:
                failures.append(str(error) if isinstance(error, AssertionError) else type(error).__name__)
            client.headers.pop('Authorization', None)
        report['failures'] = failures
        report['status'] = 'passed' if not failures and report.get('checksPassed') else 'failed'
        report['finishedAt'] = datetime.now(timezone.utc).isoformat()
        save()
print(json.dumps({'status': report['status'], 'baselineCount': report.get('baseline', {}).get('count'), 'finalCount': report.get('final', {}).get('count'), 'created': len(own_rows), 'cleanup': len(report['cleanup']), 'logoutStatus': report.get('logoutStatus'), 'failures': failures}))
sys.exit(0 if report['status'] == 'passed' else 1)
