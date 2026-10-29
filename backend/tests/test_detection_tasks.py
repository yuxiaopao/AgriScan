"""Exercise real task transport, ownership, concurrency and commit cancellation."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db import Detection, Plot, User
from app.inference import InferenceResult
from test_api import auth, client, picture
from test_media import video
from test_user_isolation import account_headers, account_id, create_plot


class Probe:
    status = 'ready'
    supported_crops = ['玉米']
    active = {'name': 'SYNTHETIC_QUEUE_TEST', 'task': 'detect'}

    def __init__(self):
        self.entered, self.release = Event(), Event()
        self.release.set()
        self.lock = Lock()
        self.active_calls = self.peak = self.calls = 0
        self.paths = []

    def predict(self, path, crop=None):
        with self.lock:
            self.calls += 1
            self.active_calls += 1
            self.peak = max(self.peak, self.active_calls)
            self.paths.append(path)
        self.entered.set()
        try:
            assert self.release.wait(8), 'test did not release inference'
            return InferenceResult('healthy', '玉米健康', .92,
                                   [{'key': 'corn', 'crop': '玉米', 'label': '玉米健康', 'confidence': .92}],
                                   {'name': 'SYNTHETIC_QUEUE_TEST', 'task': 'detect',
                                    'verification': {'status': 'agree', 'scope': 'whole_image',
                                                     'classification': {'label': '玉米健康', 'confidence': .9}}}, '玉米')
        finally:
            with self.lock:
                self.active_calls -= 1


@pytest.fixture()
def queued_client(client):
    client.app.state.inference = Probe()
    yield client
    client.app.state.inference.release.set()


def reserve(client, headers, data=None, **overrides):
    data = data if data is not None else picture()
    body = {'client_request_id': str(uuid4()), 'kind': 'image', 'filename': 'sample.png',
            'content_type': 'image/png', 'size_bytes': len(data), **overrides}
    response = client.post('/api/detection-tasks', headers=headers, json=body)
    return response, body


def submit(client, headers, data=None, **overrides):
    data = data if data is not None else picture()
    response, _ = reserve(client, headers, data, **overrides)
    assert response.status_code == 201, response.text
    task = response.json()
    response = client.put(f"/api/detection-tasks/{task['id']}/file", headers=headers, content=data)
    assert response.status_code == 202, response.text
    return task['id']


def wait_task(client, headers, task_id, statuses=('completed', 'failed', 'cancelled')):
    deadline = monotonic() + 8
    while monotonic() < deadline:
        response = client.get('/api/detection-tasks/' + task_id, headers=headers)
        assert response.status_code == 200, response.text
        task = response.json()
        if task['status'] in statuses:
            return task
        sleep(.02)
    raise AssertionError(f'task did not reach {statuses}: {task}')


def test_task_upload_persists_owned_snapshot_and_returns_only_record_ids(queued_client):
    client, headers = queued_client, auth(queued_client)
    task_id = submit(client, headers, filename='C:\\fake\\leaf.png', note='后台采样')
    task = wait_task(client, headers, task_id)
    assert task['status'] == 'completed' and len(task['result_ids']) == 1
    assert task['filename'] == 'leaf.png' and task['received_bytes'] == task['total_bytes']
    row = client.get('/api/detections/' + task['result_ids'][0], headers=headers).json()
    assert row['name'] == 'leaf.png' and row['note'] == '后台采样'
    assert row['prediction_model']['verification']['status'] == 'agree'
    assert client.get(row['image_url'], headers=headers).status_code == 200
    assert not client.app.state.detection_tasks.root.exists()
    assert client.delete('/api/detection-tasks/' + task_id, headers=headers).json() == task
    assert client.put('/api/detection-tasks/' + task_id + '/file', headers=headers, content=picture()).status_code == 409


def test_reservation_is_idempotent_but_parameter_changes_conflict(queued_client):
    client, headers = queued_client, auth(queued_client)
    first, body = reserve(client, headers)
    again = client.post('/api/detection-tasks', headers=headers, json=body)
    assert again.status_code == 201 and again.json() == first.json()
    changed = client.post('/api/detection-tasks', headers=headers, json={**body, 'note': 'different'})
    assert changed.status_code == 409
    assert len(client.get('/api/detection-tasks', headers=headers).json()) == 1


def test_all_task_actions_require_same_owner_and_session(queued_client):
    client = queued_client
    owner, other = auth(client), account_headers(client, 'queue_other')
    task, _ = reserve(client, owner)
    task_id = task.json()['id']
    same_user_new_session = auth(client)
    for headers in [other, same_user_new_session]:
        assert client.get('/api/detection-tasks', headers=headers).json() == []
        for method, suffix in [('get', ''), ('delete', ''), ('put', '/file')]:
            assert getattr(client, method)('/api/detection-tasks/' + task_id + suffix, headers=headers).status_code == 404
    assert client.get('/api/detection-tasks').status_code == 401
    assert client.post('/api/detection-tasks', json={}).status_code == 401


def test_queue_admission_bounds_global_per_user_and_staged_bytes(queued_client, monkeypatch):
    client = queued_client
    headers = [auth(client), account_headers(client, 'queue_b'), account_headers(client, 'queue_c')]
    for owner in headers[:2]:
        for _ in range(4):
            assert reserve(client, owner)[0].status_code == 201
        full = reserve(client, owner)[0]
        assert full.status_code == 429 and full.headers['retry-after'] == '2'
    assert reserve(client, headers[2])[0].status_code == 429
    for task in client.get('/api/detection-tasks', headers=headers[0]).json():
        client.delete('/api/detection-tasks/' + task['id'], headers=headers[0])
    monkeypatch.setattr(client.app.state.detection_tasks, 'MAX_STAGED_BYTES', 1)
    assert reserve(client, headers[2])[0].status_code == 429


def test_invalid_declared_and_actual_sizes_and_real_decode_fail_safely(queued_client):
    client, headers = queued_client, auth(queued_client)
    assert reserve(client, headers, size_bytes=11 * 1024 * 1024)[0].status_code == 413
    task, _ = reserve(client, headers, size_bytes=1)
    task_id = task.json()['id']
    response = client.put('/api/detection-tasks/' + task_id + '/file', headers=headers, content=picture())
    assert response.status_code == 413
    assert wait_task(client, headers, task_id)['status'] == 'failed'
    task, _ = reserve(client, headers)
    task_id = task.json()['id']
    assert client.put('/api/detection-tasks/' + task_id + '/file', headers=headers, content=b'x').status_code == 422
    task_id = submit(client, headers, b'not an image')
    task = wait_task(client, headers, task_id)
    assert task['status'] == 'failed' and task['result_ids'] == []
    assert client.app.state.inference.calls == 0
    assert client.get('/api/detections', headers=headers).json() == []
    assert not client.app.state.detection_tasks.root.exists()


def test_concurrent_tasks_and_legacy_images_share_one_model_lane(queued_client):
    client, headers = queued_client, auth(queued_client)
    probe = client.app.state.inference
    probe.release.clear()
    first = submit(client, headers)
    assert probe.entered.wait(3)
    second = submit(client, headers)
    with ThreadPoolExecutor(1) as executor:
        legacy = executor.submit(lambda: client.post('/api/detections', headers=headers,
                                 files={'file': ('legacy.png', picture(), 'image/png')}))
        sleep(.1)
        probe.release.set()
        assert legacy.result(timeout=8).status_code == 201
    assert wait_task(client, headers, first)['status'] == 'completed'
    assert wait_task(client, headers, second)['status'] == 'completed'
    assert probe.calls == 3 and probe.peak == 1


def test_cancel_running_and_queued_tasks_saves_nothing(queued_client):
    client, headers = queued_client, auth(queued_client)
    probe = client.app.state.inference
    probe.release.clear()
    first = submit(client, headers)
    assert probe.entered.wait(3)
    second, third = submit(client, headers), submit(client, headers)
    sleep(.05)
    cancelled = client.delete('/api/detection-tasks/' + third, headers=headers).json()
    assert cancelled['status'] == 'cancelled'
    for task_id in [first, second]:
        task = client.delete('/api/detection-tasks/' + task_id, headers=headers).json()
        assert task['status'] == 'cancelling'
    probe.release.set()
    for task_id in [first, second, third]:
        assert wait_task(client, headers, task_id)['status'] == 'cancelled'
    assert probe.calls == 1  # Cancelled lane waiters never enter ONNX.
    assert client.get('/api/detections', headers=headers).json() == []
    assert not client.app.state.detection_tasks.root.exists()


def test_logout_cancels_running_task_and_new_session_cannot_see_it(queued_client):
    client, headers = queued_client, auth(queued_client)
    probe = client.app.state.inference
    probe.release.clear()
    task_id = submit(client, headers)
    assert probe.entered.wait(3)
    assert client.post('/api/auth/logout', headers=headers).status_code == 200
    probe.release.set()
    deadline = monotonic() + 4
    while client.app.state.detection_tasks.tasks[task_id].status == 'cancelling' and monotonic() < deadline:
        sleep(.02)
    assert client.app.state.detection_tasks.tasks[task_id].status == 'cancelled'
    new_headers = auth(client)
    assert client.get('/api/detection-tasks', headers=new_headers).json() == []
    assert client.get('/api/detections', headers=new_headers).json() == []


def test_session_revocation_and_plot_transfer_rechecked_before_commit(queued_client):
    client = queued_client
    headers, other = auth(client), account_headers(client, 'queue_new_plot_owner')
    plot = create_plot(client, headers, crop='玉米')
    probe = client.app.state.inference
    probe.release.clear()
    task_id = submit(client, headers, plot_id=plot['id'])
    assert probe.entered.wait(3)
    with client.app.state.session() as db:
        db.get(Plot, plot['id']).owner_id = account_id(client, other)
        db.commit()
    probe.release.set()
    task = wait_task(client, headers, task_id)
    assert task['status'] == 'failed' and task['result_ids'] == []
    assert client.get('/api/detections', headers=headers).json() == []


def test_reservation_expires_and_service_restart_is_explicit_not_recreated(queued_client):
    client, headers = queued_client, auth(queued_client)
    response, _ = reserve(client, headers)
    task_id = response.json()['id']
    manager = client.app.state.detection_tasks
    with manager.condition:
        manager.tasks[task_id].activity -= 181
    assert wait_task(client, headers, task_id)['status'] == 'failed'
    with manager.condition:
        manager.tasks.clear()  # A process-local registry is intentionally not durable.
    response = client.get('/api/detection-tasks/' + task_id, headers=headers)
    assert response.status_code == 404 and '重启' in response.json()['detail']
    assert client.get('/api/detection-tasks', headers=headers).json() == []


def test_video_cancellation_discards_entire_batch_and_frees_lane(queued_client, tmp_path):
    client, headers = queued_client, auth(queued_client)
    probe = client.app.state.inference
    probe.release.clear()
    task_id = submit(client, headers, video(tmp_path), kind='video', filename='sample.avi', content_type='video/x-msvideo')
    assert probe.entered.wait(3)
    assert client.delete('/api/detection-tasks/' + task_id, headers=headers).json()['status'] == 'cancelling'
    probe.release.set()
    assert wait_task(client, headers, task_id)['status'] == 'cancelled'
    assert probe.calls == 1 and client.get('/api/detections', headers=headers).json() == []
    image_id = submit(client, headers)
    assert wait_task(client, headers, image_id)['status'] == 'completed'


def test_video_and_images_interleave_and_video_result_ids_are_owned(queued_client, tmp_path):
    client, headers = queued_client, auth(queued_client)
    probe = client.app.state.inference
    probe.release.clear()
    video_id = submit(client, headers, video(tmp_path), kind='video', filename='sample.avi', content_type='video/x-msvideo')
    assert probe.entered.wait(3)
    image_id = submit(client, headers)
    # Wait until the second worker has queued behind the current video frame.
    deadline = monotonic() + 3
    while len(client.app.state.inference_scheduler.waiters) < 1 and monotonic() < deadline:
        sleep(.01)
    probe.release.set()
    assert wait_task(client, headers, image_id)['status'] == 'completed'
    task = wait_task(client, headers, video_id)
    assert task['status'] == 'completed' and len(task['result_ids']) == 8
    assert probe.peak == 1
    assert 'image.jpg' == probe.paths[1].name  # FIFO yields between video frames.
    assert all(client.get('/api/detections/' + row_id, headers=headers).status_code == 200 for row_id in task['result_ids'])


def test_no_model_image_sampling_runs_in_background_with_explicit_crop(client):
    headers = auth(client)
    assert reserve(client, headers)[0].status_code == 422
    assert reserve(client, headers, kind='video', content_type='video/mp4')[0].status_code == 422
    task_id = submit(client, headers, crop='玉米')
    task = wait_task(client, headers, task_id)
    assert task['status'] == 'completed' and len(task['result_ids']) == 1
    row = client.get('/api/detections/' + task['result_ids'][0], headers=headers).json()
    assert row['status'] == 'awaiting_model' and row['crop'] == '玉米'
    assert row['boxes'] == [] and row['prediction_model'] is None


def test_raw_upload_io_is_bounded_and_explicit_cancel_interrupts_idle_stream(queued_client):
    import asyncio
    from fastapi import HTTPException
    client, headers = queued_client, auth(queued_client)
    manager = client.app.state.detection_tasks
    task_ids = [reserve(client, headers)[0].json()['id'] for _ in range(3)]

    async def exercise():
        started = [asyncio.Event(), asyncio.Event()]
        gates = [asyncio.Event(), asyncio.Event()]
        class SlowRequest:
            def __init__(self, index): self.index = index
            async def stream(self):
                started[self.index].set()
                await gates[self.index].wait()
                yield picture()
        uploads = [asyncio.create_task(manager.upload(SlowRequest(index), manager.tasks[task_ids[index]])) for index in range(2)]
        try:
            await asyncio.gather(*(event.wait() for event in started))
            with pytest.raises(HTTPException) as full:
                await manager.upload(SlowRequest(0), manager.tasks[task_ids[2]])
            assert full.value.status_code == 429
            with manager.condition:
                manager.cancel_task(manager.tasks[task_ids[0]])
            cancelled = await asyncio.wait_for(uploads[0], timeout=2)
            assert cancelled['status'] == 'cancelled' and cancelled['result_ids'] == []
            with manager.condition:
                manager.cancel_task(manager.tasks[task_ids[1]])
            assert (await asyncio.wait_for(uploads[1], timeout=2))['status'] == 'cancelled'
        finally:
            for gate in gates: gate.set()
            await asyncio.gather(*uploads, return_exceptions=True)
    asyncio.run(exercise())
    assert not manager.root.exists()


def test_revoked_credentials_and_disabled_feature_prevent_commit(queued_client):
    client, headers = queued_client, auth(queued_client)
    probe = client.app.state.inference
    probe.release.clear()
    task_id = submit(client, headers)
    assert probe.entered.wait(3)
    with client.app.state.session() as db:
        user = db.scalar(select(User).where(User.username == 'admin'))
        user.token_version += 1
        db.commit()
    probe.release.set()
    manager = client.app.state.detection_tasks
    deadline = monotonic() + 4
    while manager.tasks[task_id].status not in {'failed', 'cancelled'} and monotonic() < deadline:
        sleep(.02)
    assert manager.tasks[task_id].status == 'failed' and manager.tasks[task_id].result_ids == []
    assert client.get('/api/detections', headers=auth(client)).json() == []


def test_disabled_feature_during_inference_prevents_new_save(queued_client):
    from test_runtime_config import patch
    client, headers = queued_client, auth(queued_client)
    probe = client.app.state.inference
    probe.release.clear()
    task_id = submit(client, headers)
    assert probe.entered.wait(3)
    response = patch(client, headers, features={'image_detection': False})
    assert response.status_code == 200, response.text
    probe.release.set()
    task = wait_task(client, headers, task_id)
    assert task['status'] == 'failed' and task['result_ids'] == []
    assert client.get('/api/detections', headers=headers).json() == []
    assert reserve(client, headers)[0].status_code == 403


def test_storage_failure_rolls_back_all_records_and_cleans_staging(queued_client, monkeypatch):
    import app.detection_tasks as module
    client, headers = queued_client, auth(queued_client)
    def fail(*args, **kwargs): raise OSError('synthetic private storage detail must not escape')
    monkeypatch.setattr(module.shutil, 'copyfile', fail)
    task_id = submit(client, headers)
    task = wait_task(client, headers, task_id)
    assert task['status'] == 'failed' and 'private storage' not in task['error']
    assert task['result_ids'] == [] and client.get('/api/detections', headers=headers).json() == []
    assert list(client.app.state.settings.upload_dir.iterdir()) == []


def test_staging_directory_error_releases_upload_slot_and_marks_failed(queued_client, monkeypatch):
    import asyncio
    from fastapi import HTTPException
    from pathlib import Path
    client, headers = queued_client, auth(queued_client)
    task_id = reserve(client, headers)[0].json()['id']
    manager = client.app.state.detection_tasks
    original = Path.mkdir
    def broken(path, *args, **kwargs):
        if path == manager.root: raise OSError('synthetic unavailable staging volume')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'mkdir', broken)
    class Request:
        async def stream(self): yield picture()
    with pytest.raises(HTTPException) as failed:
        asyncio.run(manager.upload(Request(), manager.tasks[task_id]))
    assert failed.value.status_code == 503 and 'staging volume' not in failed.value.detail
    assert manager.tasks[task_id].status == 'failed'
    assert manager.upload_slots.acquire(blocking=False)
    assert manager.upload_slots.acquire(blocking=False)
    assert not manager.upload_slots.acquire(blocking=False)
    manager.upload_slots.release(); manager.upload_slots.release()


def test_cache_error_after_commit_keeps_completed_result_and_cancel_is_idempotent(queued_client, monkeypatch):
    client, headers = queued_client, auth(queued_client)
    def fail(*args, **kwargs): raise RuntimeError('synthetic cache outage')
    monkeypatch.setattr(client.app.state.cache, 'invalidate', fail)
    task_id = submit(client, headers)
    task = wait_task(client, headers, task_id)
    assert task['status'] == 'completed' and len(task['result_ids']) == 1
    assert client.get('/api/detections/' + task['result_ids'][0], headers=headers).status_code == 200
    assert client.delete('/api/detection-tasks/' + task_id, headers=headers).json() == task
