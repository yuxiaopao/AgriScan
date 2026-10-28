"""Synthetic detector output validates geometry/API contracts, never model accuracy."""
import hashlib
import io
import json

from fastapi.testclient import TestClient
import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
from PIL import Image
import pytest

from app.config import Settings
from app.detection_inference import OnnxDetectionProvider
from app.main import create_app
from test_api import auth
from test_assistant import fake_provider


def fixture_manifest(folder, rows=None, **overrides):
    folder.mkdir(parents=True, exist_ok=True)
    if rows is None:
        rows = [[160, 240, 480, 400, 0.9, 1], [32, 176, 96, 224, 0.8, 1], [0, 160, 640, 480, 0.7, 0]]
    values = np.array([rows], dtype=np.float32)
    graph = helper.make_graph([helper.make_node('Constant', [], ['output'],
                                               value=numpy_helper.from_array(values))],
                              'SYNTHETIC_DETECTION_ONLY',
                              [helper.make_tensor_value_info('images', TensorProto.FLOAT, [1, 3, 640, 640])],
                              [helper.make_tensor_value_info('output', TensorProto.FLOAT, list(values.shape))])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid('', 17)], ir_version=9)
    path = folder / 'model.onnx'
    onnx.save(model, path)
    metadata = {'name': 'SYNTHETIC_DETECTION_ONLY', 'task': 'detect', 'validation_passed': True,
                'onnx_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'image_size': 640, 'threshold': 0.25,
                'preprocessing': 'letterbox-rgb-div255', 'output_format': 'end2end_xyxy_score_class',
                'coordinate_space': 'normalized_xyxy', 'classes': [
                    {'key': 'tomato-healthy', 'crop': '番茄', 'healthy': True, 'label': '番茄健康'},
                    {'key': 'tomato-blight', 'crop': '番茄', 'healthy': False, 'label': '番茄早疫病'},
                    {'key': 'corn-healthy', 'crop': '玉米', 'healthy': True, 'label': '玉米健康'},
                ], **overrides}
    metadata['metadata_sha256'] = hashlib.sha256(json.dumps(metadata['classes'], sort_keys=True,
                                                            ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    manifest = folder / 'manifest.json'
    manifest.write_text(json.dumps(metadata, ensure_ascii=False), encoding='utf-8')
    return manifest


def detector_client(tmp_path, rows=None):
    manifest = fixture_manifest(tmp_path / 'fixture', rows)
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'detector.db'}", upload_dir=tmp_path / 'uploads',
                        model_manifest=str(manifest), redis_url='', demo_mode=True, llm_enabled=False,
                        admin_username='admin', admin_password='admin12345', email_verification_enabled=False)
    return TestClient(create_app(settings))


def image_bytes():
    data = io.BytesIO()
    Image.new('RGB', (200, 100), '#558944').save(data, format='PNG')
    return data.getvalue()


def upload(client, headers, **fields):
    return client.post('/api/detections', headers=headers, data=fields,
                       files={'file': ('leaf.png', image_bytes(), 'image/png')})


def test_real_detector_outputs_are_unletterboxed_persisted_and_sent_to_assistant(tmp_path, monkeypatch):
    with detector_client(tmp_path) as client:
        calls = fake_provider(client, monkeypatch)
        headers = auth(client)
        response = upload(client, headers)
        assert response.status_code == 201, response.text
        row = response.json()
        assert row['crop'] == '番茄' and row['result'] == '番茄早疫病' and row['status'] == 'attention'
        assert row['boxes'][0]['bbox'] == pytest.approx([0.25, 0.25, 0.75, 0.75])
        assert len(row['boxes']) == 3
        assert [item['confidence'] for item in row['candidates']] == pytest.approx([0.9, 0.7])
        assert row['prediction_model']['task'] == 'detect' and 'boxes' not in row['prediction_model']
        assert client.get('/api/detections/' + row['id']).json() == row
        assert client.get('/api/models').json()['active']['test_top1'] is None
        interpreted = client.post(f"/api/assistant/detections/{row['id']}/analysis", headers=headers)
        assert interpreted.status_code == 200, interpreted.text
        prompt = calls[0][-1]['content'][0]['text']
        facts = json.loads(prompt.split('检测记录：', 1)[1])
        assert facts['检测目标框（原图归一化xyxy，并非病斑精确边界）'] == row['boxes']
        assert facts['检测结果'] == row['result']
        assert '独立检测置信度' in prompt and '不是病斑精确边界' in prompt
        assert '单标签分类候选' not in prompt


def test_multiple_crops_cannot_be_mistakenly_associated_to_one_plot(tmp_path):
    with detector_client(tmp_path, [[0, 160, 640, 480, 0.9, 0], [0, 160, 320, 400, 0.8, 2]]) as client:
        response = upload(client, auth(client), plot_id='plot-tomato')
        assert response.status_code == 422 and '地块' in response.json()['detail']
        assert '玉米' in response.json()['detail'] and '番茄' in response.json()['detail']
        assert list(client.app.state.settings.upload_dir.iterdir()) == []
        assert client.get('/api/dashboard').json()['stats']['total'] == 12


@pytest.mark.parametrize('secondary_class,expected', [(0, 200), (2, 422)])
def test_admin_plot_association_checks_every_saved_target_without_partial_edits(tmp_path, secondary_class, expected):
    with detector_client(tmp_path, [[0, 160, 640, 480, 0.9, 1],
                                    [0, 160, 320, 400, 0.8, secondary_class]]) as client:
        headers = auth(client)
        created = upload(client, headers).json()
        assert created['crop'] == '番茄' and created['plot_id'] is None
        response = client.patch('/api/admin/detections/' + created['id'], headers=headers,
                                json={'name': '复核后的样本', 'note': '管理员复核', 'plot_id': 'plot-tomato'})
        assert response.status_code == expected, response.text
        stored = client.get('/api/detections/' + created['id']).json()
        if expected == 422:
            assert '地块' in response.json()['detail'] and '玉米' in response.json()['detail']
            assert stored == created
            assert client.get('/api/admin/audit?action=detection.update', headers=headers).json()['total'] == 0
            metadata = client.patch('/api/admin/detections/' + created['id'], headers=headers,
                                    json={'note': '保留混样观察，暂不关联地块', 'plot_id': None})
            assert metadata.status_code == 200 and metadata.json()['plot_id'] is None
            stored = metadata.json()
        else:
            assert stored['plot_id'] == 'plot-tomato' and stored['name'] == '复核后的样本'
        assert all(stored[field] == created[field] for field in
                   ('crop', 'result', 'confidence', 'boxes', 'candidates', 'prediction_model'))


@pytest.mark.parametrize('rows,expected', [
    ([[0, 0, 640, 640, 0.01, 0]], 422),
    ([[0, 0, 640, 640, float('nan'), 0]], 503),
    ([[0, 0, 640, 640, 0.9, 99]], 503),
    ([[400, 200, 100, 300, 0.9, 0]], 503),
])
def test_invalid_or_missing_targets_never_create_fake_results(tmp_path, rows, expected):
    with detector_client(tmp_path, rows) as client:
        assert upload(client, auth(client)).status_code == expected
        assert client.get('/api/dashboard').json()['stats']['total'] == 12
        assert list(client.app.state.settings.upload_dir.iterdir()) == []
        guard = client.app.state.inference.guard
        assert guard.acquire(blocking=False)
        guard.release()


def test_detector_respects_model_lock_and_explicit_crop(tmp_path):
    with detector_client(tmp_path) as client:
        headers = auth(client)
        guard = client.app.state.inference.guard
        guard.acquire()
        try:
            assert upload(client, headers).status_code == 503
        finally:
            guard.release()
        assert upload(client, headers, crop='玉米').status_code == 422
        assert upload(client, headers, crop='番茄').status_code == 201


def test_detection_manifest_rejects_wrong_sha_and_unvalidated_artifact(tmp_path):
    path = fixture_manifest(tmp_path / 'one', onnx_sha256='wrong')
    with pytest.raises(ValueError, match='SHA256'):
        OnnxDetectionProvider(path)
    path = fixture_manifest(tmp_path / 'two', validation_passed=False)
    with pytest.raises(ValueError, match='validated'):
        OnnxDetectionProvider(path)


def test_boxes_follow_the_exif_corrected_saved_image(tmp_path):
    image = Image.new('RGB', (80, 40), '#668f47')
    exif = Image.Exif()
    exif[274] = 6
    data = io.BytesIO()
    image.save(data, format='JPEG', exif=exif)
    with detector_client(tmp_path) as client:
        response = client.post('/api/detections', headers=auth(client),
                               files={'file': ('portrait.jpg', data.getvalue(), 'image/jpeg')})
        assert response.status_code == 201, response.text
        row = response.json()
        assert row['boxes'][0]['bbox'] == pytest.approx([0, 0.375, 1, 0.625])
        with Image.open(io.BytesIO(client.get(row['image_url']).content)) as saved:
            assert saved.size == (40, 80) and not saved.getexif()


def test_camera_and_video_keep_actual_detection_boxes(tmp_path):
    from test_media import video
    with detector_client(tmp_path) as client:
        headers = auth(client)
        frame = client.post('/api/media/frame', headers=headers,
                            files={'file': ('camera.png', image_bytes(), 'image/png')})
        assert frame.status_code == 200 and len(frame.json()['boxes']) == 3
        assert client.get('/api/dashboard').json()['stats']['total'] == 12
        result = client.post('/api/media/video', headers=headers,
                             files={'file': ('leaf.avi', video(tmp_path, frames=2, fps=1), 'video/x-msvideo')})
        assert result.status_code == 200, result.text
        assert result.json()['sampled_frames'] == 2
        for item in result.json()['results']:
            row = item['detection']
            assert len(row['boxes']) == 3 and row['prediction_model']['task'] == 'detect'
            assert client.get('/api/detections/' + row['id']).json() == row
