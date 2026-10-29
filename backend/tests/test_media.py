"""Exercise real image/video decoding and persistence with deterministic inference."""
import io
from pathlib import Path

from fastapi import HTTPException
import pytest
from PIL import Image
from sqlalchemy import func, select

from app.db import Detection, DetectionPrediction
from app.inference import InferenceResult
from app.media import install_media
from test_api import owned_demo_auth as auth, client, picture


class Classifier:
    status = 'ready'
    active = {'name': 'SYNTHETIC_TEST_ONLY', 'task': 'classify'}
    supported_crops = ['番茄', '玉米']

    def __init__(self):
        self.paths = []
        self.fail_at = None

    def predict(self, path, crop=None):
        assert crop is None
        self.paths.append(Path(path))
        if self.fail_at == len(self.paths):
            raise HTTPException(503, 'inference unavailable')
        with Image.open(path) as image:
            red, green, _ = image.convert('RGB').getpixel((0, 0))
        crop = '番茄' if red > green else '玉米'
        return InferenceResult('attention' if crop == '番茄' else 'healthy',
                               '番茄早疫病' if crop == '番茄' else '玉米健康', 0.9,
                               [{'key': crop, 'crop': crop, 'label': crop, 'healthy': crop == '玉米', 'confidence': 0.9}],
                               {'name': 'SYNTHETIC_TEST_ONLY', 'task': 'classify', 'onnx_sha256': 'test-only'}, crop)


@pytest.fixture()
def media_client(client):
    def get_db():
        with client.app.state.session() as db:
            yield db
    if not any(route.path == '/api/media/frame' for route in client.app.routes):
        install_media(client.app, get_db)
    client.app.state.inference = Classifier()
    return client


def video(tmp_path, frames=12, fps=4, color=(30, 150, 50), colors=None):
    import cv2
    import numpy as np
    target = tmp_path / 'test.avi'
    writer = cv2.VideoWriter(str(target), cv2.VideoWriter_fourcc(*'MJPG'), fps, (64, 48))
    assert writer.isOpened()
    for index in range(frames):
        writer.write(np.full((48, 64, 3), colors[index % len(colors)] if colors else color, dtype=np.uint8))
    writer.release()
    return target.read_bytes()


def post_frame(client, headers, data=None):
    return client.post('/api/media/frame', headers=headers,
                       files={'file': ('camera.png', picture() if data is None else data, 'image/png')})


def post_video(client, headers, data, **fields):
    return client.post('/api/media/video', headers=headers, data=fields,
                       files={'file': ('../../sample.avi', data, 'video/x-msvideo')})


def test_frame_predicts_without_persisting_and_removes_temporary_image(media_client):
    client = media_client
    response = post_frame(client, auth(client))
    assert response.status_code == 200, response.text
    row = response.json()
    assert row['crop'] == '玉米' and row['status'] == 'healthy'
    assert row['confidence'] == 0.9 and row['candidates'][0]['crop'] == '玉米'
    assert row['prediction_model']['name'] == 'SYNTHETIC_TEST_ONLY'
    assert row['is_demo'] is False and row['image_url'] is None
    assert client.get('/api/dashboard',headers=auth(client)).json()['stats']['total'] == 12
    assert list(client.app.state.settings.upload_dir.iterdir()) == []
    assert client.app.state.inference.paths and all(not path.exists() for path in client.app.state.inference.paths)


def test_capabilities_report_effective_classification_limits(media_client):
    response = media_client.get('/api/media/capabilities')
    assert response.status_code == 200
    assert response.json() == {'video_max_mb': 50, 'video_max_seconds': 60, 'video_max_frames': 8,
                               'frame_min_interval_ms': 750, 'video_enabled': True, 'live_enabled': True,
                               'mode': 'leaf_classification', 'model_ready': True}


@pytest.mark.parametrize('route', ['frame', 'video'])
def test_media_requires_authentication(media_client, route):
    response = media_client.post('/api/media/' + route, files={'file': ('file.png', picture(), 'image/png')})
    assert response.status_code == 401


@pytest.mark.parametrize('route', ['frame', 'video'])
def test_media_requires_active_model_and_does_not_save_samples(media_client, route):
    media_client.app.state.inference.status = 'awaiting_weights'
    response = media_client.post('/api/media/' + route, headers=auth(media_client),
                                 files={'file': ('file.png', picture(), 'image/png')})
    assert response.status_code == 503 and '模型' in response.json()['detail']
    assert list(media_client.app.state.settings.upload_dir.iterdir()) == []


def test_invalid_frame_and_burst_are_rejected(media_client):
    headers = auth(media_client)
    assert post_frame(media_client, headers, b'not-image').status_code == 422
    assert post_frame(media_client, headers).status_code == 429
    assert media_client.app.state.inference.paths == []


def test_frame_rejects_oversized_decoded_image(media_client):
    data = io.BytesIO()
    Image.new('RGB', (4000, 4000), '#41823e').save(data, format='PNG')
    response = post_frame(media_client, auth(media_client), data.getvalue())
    assert response.status_code == 422 and '分辨率' in response.json()['detail']
    assert media_client.app.state.inference.paths == []


def test_frame_rejects_species_not_covered_by_model(media_client, monkeypatch):
    monkeypatch.setattr(media_client.app.state.inference, 'predict',
                        lambda path, crop=None: InferenceResult('healthy', '水稻健康', 0.9, crop='水稻'))
    assert post_frame(media_client, auth(media_client)).status_code == 503
    assert list(media_client.app.state.settings.upload_dir.iterdir()) == []


def test_video_decoder_does_not_block_camera_inference(media_client):
    guard = media_client.app.state.media_guard
    assert guard.acquire(blocking=False)
    try:
        assert post_frame(media_client, auth(media_client)).status_code == 200
    finally:
        guard.release()


def test_video_samples_real_frames_uniformly_and_persists_snapshots(media_client, tmp_path):
    client = media_client
    response = post_video(client, auth(client), video(tmp_path), plot_id='plot-corn', note='试验田视频')
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['filename'] == 'sample.avi' and report['source'] == 'sampled_video'
    assert report['duration_seconds'] == pytest.approx(3)
    assert report['sampled_frames'] == 8 == len(report['results'])
    assert report['summary'] == {'total': 8, 'healthy': 8, 'attention': 0}
    timestamps = [item['timestamp_seconds'] for item in report['results']]
    assert timestamps[0] == 0 and timestamps[-1] == pytest.approx(2.75)
    assert timestamps == sorted(set(timestamps))
    for item in report['results']:
        row = item['detection']
        assert row['crop'] == '玉米' and row['plot_id'] == 'plot-corn'
        assert row['candidates'][0]['confidence'] == 0.9 and '试验田视频' in row['note']
        assert client.get('/api/detections/' + row['id'], headers=auth(client)).json() == row
        assert client.get(row['image_url'], headers=auth(client)).status_code == 200
    assert client.get('/api/dashboard', headers=auth(client)).json()['stats']['total'] == 20
    assert len(list(client.app.state.settings.upload_dir.iterdir())) == 8
    with client.app.state.session() as db:
        assert db.scalar(select(func.count()).select_from(DetectionPrediction)) == 8
    assert all(not path.exists() for path in client.app.state.inference.paths)


def test_each_video_sample_is_classified_independently(media_client, tmp_path):
    response = post_video(media_client, auth(media_client),
                          video(tmp_path, frames=2, fps=1, colors=[(0, 0, 200), (0, 180, 0)]))
    assert response.status_code == 200, response.text
    report = response.json()
    assert report['summary'] == {'total': 2, 'healthy': 1, 'attention': 1}
    assert [item['detection']['crop'] for item in report['results']] == ['番茄', '玉米']
    assert [item['detection']['result'] for item in report['results']] == ['番茄早疫病', '玉米健康']


def test_video_storage_failure_removes_partial_files_and_rows(media_client, tmp_path, monkeypatch):
    from app import media
    original_copy = media.shutil.copyfile
    count = 0

    def broken_storage(source, target):
        nonlocal count
        count += 1
        if count == 3:
            raise OSError('disk unavailable')
        return original_copy(source, target)

    monkeypatch.setattr(media.shutil, 'copyfile', broken_storage)
    response = post_video(media_client, auth(media_client), video(tmp_path))
    assert response.status_code == 503
    assert count == 3
    assert media_client.get('/api/dashboard',headers=auth(media_client)).json()['stats']['total'] == 12
    assert list(media_client.app.state.settings.upload_dir.iterdir()) == []
    with media_client.app.state.session() as db:
        assert db.scalar(select(func.count()).select_from(DetectionPrediction)) == 0


@pytest.mark.parametrize('frames,fps,expected', [(2, 4, 2), (241, 4, None)])
def test_video_respects_frame_count_and_duration_limit(media_client, tmp_path, frames, fps, expected):
    response = post_video(media_client, auth(media_client), video(tmp_path, frames, fps))
    if expected is None:
        assert response.status_code == 422 and '60' in response.json()['detail']
        assert media_client.app.state.inference.paths == []
        assert list(media_client.app.state.settings.upload_dir.iterdir()) == []
    else:
        assert response.status_code == 200 and response.json()['sampled_frames'] == expected


@pytest.mark.parametrize('payload,expected', [(b'not-video', 422), (b'RIFFxxxxAVI ' + b'x' * 64, 422),
                                          (b'x' * (50 * 1024 * 1024 + 1), 413)], ids=['invalid', 'corrupt-avi', 'oversized'])
def test_invalid_and_oversized_video_do_not_persist(media_client, payload, expected):
    response = post_video(media_client, auth(media_client), payload)
    assert response.status_code == expected
    assert list(media_client.app.state.settings.upload_dir.iterdir()) == []
    assert media_client.app.state.inference.paths == []


def test_video_burst_is_limited_without_decoding(media_client):
    headers = auth(media_client)
    for _ in range(3):
        assert post_video(media_client, headers, b'not-video').status_code == 422
    response = post_video(media_client, headers, b'not-video')
    assert response.status_code == 429 and 'retry-after' in response.headers
    assert media_client.app.state.inference.paths == []


def test_video_checks_decoded_dimensions_before_sampling(media_client, tmp_path, monkeypatch):
    import cv2
    capture_factory = cv2.VideoCapture

    class OversizedCapture:
        def __init__(self, *args, **kwargs):
            self.capture = capture_factory(*args, **kwargs)

        def get(self, prop):
            return 5000 if prop == cv2.CAP_PROP_FRAME_WIDTH else self.capture.get(prop)

        def __getattr__(self, name):
            return getattr(self.capture, name)

    data = video(tmp_path)
    monkeypatch.setattr(cv2, 'VideoCapture', OversizedCapture)
    response = post_video(media_client, auth(media_client), data)
    assert response.status_code == 422 and '尺寸' in response.json()['detail']
    assert media_client.app.state.inference.paths == []
    assert list(media_client.app.state.settings.upload_dir.iterdir()) == []


@pytest.mark.parametrize('fail_at,plot_id,expected', [(3, None, 503), (None, 'plot-tomato', 422),
                                                    (None, 'missing', 404)])
def test_video_failure_rolls_back_entire_batch(media_client, tmp_path, fail_at, plot_id, expected):
    client = media_client
    client.app.state.inference.fail_at = fail_at
    response = post_video(client, auth(client), video(tmp_path), **({'plot_id': plot_id} if plot_id else {}))
    assert response.status_code == expected
    assert client.get('/api/dashboard',headers=auth(client)).json()['stats']['total'] == 12
    assert list(client.app.state.settings.upload_dir.iterdir()) == []
    with client.app.state.session() as db:
        assert db.scalar(select(func.count()).select_from(DetectionPrediction)) == 0
    assert all(not path.exists() for path in client.app.state.inference.paths)
