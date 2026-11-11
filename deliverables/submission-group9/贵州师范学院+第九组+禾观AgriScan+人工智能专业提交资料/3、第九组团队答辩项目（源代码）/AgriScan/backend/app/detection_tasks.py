"""Session-private, bounded background detection without a second model process."""
import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hmac
import logging
import os
import shutil
from threading import BoundedSemaphore, Condition, RLock, Thread
from time import monotonic, time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request
from PIL import ImageOps
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from .db import Detection, DetectionPrediction, RevokedToken, User
from .inference import SUPPORTED_CROPS, prediction_snapshot
from .inference_scheduler import ScheduledProvider
from .media import sample_video
from .ownership import _lock_query, owned_plot
from .security import credential_signature, current_user

ACTIVE = {'awaiting_upload', 'uploading', 'queued', 'processing', 'cancelling'}
TERMINAL = {'completed', 'cancelled', 'failed'}
logger = logging.getLogger(__name__)


class TaskBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_request_id: UUID
    kind: Literal['image', 'video']
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(gt=0, strict=True)
    note: str = Field(default='', max_length=2000)
    plot_id: str | None = Field(default=None, max_length=32)
    crop: str | None = Field(default=None, max_length=40)

    @field_validator('crop', 'plot_id')
    @classmethod
    def empty_is_none(cls, value):
        return value.strip() or None if value is not None else None


@dataclass
class Task:
    id: str
    user_id: str
    session: dict
    body: TaskBody
    status: str = 'awaiting_upload'
    received: int = 0
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated: str = ''
    activity: float = field(default_factory=monotonic)
    error: str | None = None
    result_ids: list = field(default_factory=list)
    cancel: bool = False

    def public(self):
        return {'id': self.id, 'client_request_id': str(self.body.client_request_id),
                'kind': self.body.kind, 'filename': clean_filename(self.body.filename),
                'status': self.status, 'received_bytes': self.received,
                'total_bytes': self.body.size_bytes, 'created_at': self.created,
                'updated_at': self.updated or self.created, 'error': self.error,
                'result_ids': list(self.result_ids)}


def clean_filename(value):
    return value.replace('\\', '/').split('/')[-1][:180] or '田间采样'


class TaskCancelled(Exception):
    pass


class DetectionTasks:
    MAX_ACTIVE = 8
    MAX_PER_USER = 4
    MAX_STAGED_BYTES = 200 * 1024 * 1024
    UPLOAD_IDLE_SECONDS = 180
    HISTORY_SECONDS = 3600

    def __init__(self, app, read_image):
        self.app, self.read_image = app, read_image
        self.condition = Condition(RLock())
        self.tasks = OrderedDict()
        self.upload_slots = BoundedSemaphore(2)
        self.threads = []
        self.closing = False
        self.video_running = False
        self.root = app.state.settings.upload_dir / '.task-staging'

    def start(self):
        # These are disposable process-local inputs, never persisted job records.
        if self.root.is_symlink():
            raise RuntimeError('Task staging directory must not be a symbolic link')
        if self.root.exists():
            shutil.rmtree(self.root)
        for index in range(2):
            thread = Thread(target=self.worker, name=f'agriscan-task-{index}', daemon=True)
            self.threads.append(thread)
            thread.start()

    def close(self):
        with self.condition:
            self.closing = True
            for task in self.tasks.values():
                if task.status in ACTIVE:
                    task.cancel = True
                    if task.status not in {'processing', 'cancelling', 'uploading'}:
                        self.finish(task, 'cancelled')
            self.condition.notify_all()
        # A running ORT call finishes before its worker exits; shutdown never
        # disposes its DB engine or removes its files underneath it.
        for thread in self.threads:
            thread.join()
        if self.root.exists():
            shutil.rmtree(self.root)

    def touch(self, task):
        task.activity = monotonic()
        task.updated = datetime.now(timezone.utc).isoformat()

    def folder(self, task):
        return self.root / task.id

    def cleanup(self, task):
        try:
            shutil.rmtree(self.folder(task), ignore_errors=True)
            if self.root.exists() and not any(self.root.iterdir()):
                self.root.rmdir()
        except OSError:
            pass

    def finish(self, task, status, error=None):
        task.status, task.error = status, error
        self.touch(task)
        self.cleanup(task)
        self.condition.notify_all()

    def expire(self):
        now = monotonic()
        for task in list(self.tasks.values()):
            if task.status == 'awaiting_upload' and now - task.activity >= self.UPLOAD_IDLE_SECONDS:
                self.finish(task, 'failed', '等待上传已超时，请重新提交。')
            if task.status in TERMINAL and now - task.activity > self.HISTORY_SECONDS:
                del self.tasks[task.id]
        terminal = [task.id for task in self.tasks.values() if task.status in TERMINAL]
        for task_id in terminal[:-256]:
            del self.tasks[task_id]

    def owned(self, task_id, user, session):
        task = self.tasks.get(task_id)
        if not task or task.user_id != user.id or task.session['jti'] != session['jti']:
            raise HTTPException(404, '任务不存在，或服务已重启，请重新提交。')
        return task

    def validate(self, body, db, user):
        snapshot = self.app.state.runtime_config.refresh()
        features, limits = snapshot.data['features'], snapshot.data['limits']
        if not features.get('image_detection' if body.kind == 'image' else 'video_detection', True):
            raise HTTPException(403, '管理员暂时关闭了此检测功能。')
        maximum = (limits['image_max_mb'] if body.kind == 'image' else limits['video_max_mb']) * 1024 * 1024
        if body.size_bytes > maximum:
            raise HTTPException(413, f'文件不能超过 {maximum // (1024 * 1024)} MB。')
        if body.crop and body.crop not in SUPPORTED_CROPS:
            raise HTTPException(422, '请选择支持的作物类型。')
        if body.kind == 'video' and body.crop:
            raise HTTPException(422, '视频检测由模型自动识别作物，请勿指定作物。')
        if body.plot_id:
            plot = owned_plot(db, body.plot_id, user, lock=True)
            if body.crop and body.crop != plot.crop:
                raise HTTPException(422, '作物类型与所选地块不一致。')
        if self.app.state.inference.status != 'ready' and (body.kind != 'image' or not body.crop):
            raise HTTPException(422, '模型尚未就绪，图片采样请指定作物；视频需模型就绪后检测。')
        return limits

    def session_user(self, task, db):
        user = db.scalar(_lock_query(db, select(User).where(User.id == task.user_id), True))
        if (not user or not user.is_active or time() >= task.session['exp']
                or db.get(RevokedToken, task.session['jti'])
                or not hmac.compare_digest(task.session['credential'],
                                           credential_signature(user, self.app.state.settings.jwt_secret))):
            raise HTTPException(401, '登录会话已失效，任务已停止。')
        return user

    def checkpoint(self, task):
        with self.condition:
            if task.cancel or self.closing:
                raise TaskCancelled()
        with self.app.state.session() as db:
            user = self.session_user(task, db)
            return self.validate(task.body, db, user)

    def reserve(self, body, user, session):
        with self.condition:
            self.expire()
            for task in self.tasks.values():
                if task.user_id == user.id and task.session['jti'] == session['jti'] and task.body.client_request_id == body.client_request_id:
                    if task.body != body:
                        raise HTTPException(409, '同一提交编号的参数不一致，请创建新的任务。')
                    return task.public()
            with self.app.state.session() as db:
                self.validate(body, db, user)
            active = [task for task in self.tasks.values() if task.status in ACTIVE]
            if (self.closing or len(active) >= self.MAX_ACTIVE
                    or sum(task.user_id == user.id for task in active) >= self.MAX_PER_USER
                    or sum(task.body.size_bytes for task in active) + body.size_bytes > self.MAX_STAGED_BYTES):
                raise HTTPException(429, '检测队列已满，请稍后重试。', headers={'Retry-After': '2'})
            task = Task(uuid4().hex, user.id, dict(session), body)
            self.tasks[task.id] = task
            self.condition.notify_all()
            return task.public()

    def cancel_task(self, task):
        if task.status in TERMINAL:
            return task.public()
        task.cancel = True
        if task.status in {'processing', 'cancelling', 'uploading'}:
            task.status = 'cancelling'
            self.touch(task)
        else:
            self.finish(task, 'cancelled')
        self.condition.notify_all()
        return task.public()

    def cancel_session(self, jti):
        with self.condition:
            for task in self.tasks.values():
                if task.session['jti'] == jti:
                    self.cancel_task(task)

    def cancel_user(self, user_id):
        with self.condition:
            for task in self.tasks.values():
                if task.user_id == user_id:
                    self.cancel_task(task)

    async def read_chunk(self, stream, task):
        pending = asyncio.create_task(anext(stream))
        deadline = monotonic() + self.UPLOAD_IDLE_SECONDS
        try:
            while not pending.done():
                await asyncio.wait({pending}, timeout=min(.25, max(0, deadline - monotonic())))
                with self.condition:
                    if task.cancel or self.closing:
                        raise TaskCancelled()
                if not pending.done() and monotonic() >= deadline:
                    raise asyncio.TimeoutError()
            return pending.result()
        finally:
            if not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)

    async def upload(self, request, task):
        with self.condition:
            if task.status != 'awaiting_upload':
                raise HTTPException(409, '任务已接收文件或已结束，请查询任务状态。')
            if not self.upload_slots.acquire(blocking=False):
                raise HTTPException(429, '已有两项文件正在上传，请稍后重试。', headers={'Retry-After': '2'})
            task.status = 'uploading'
            self.touch(task)
            folder = self.folder(task)
        try:
            with self.condition:
                if task.cancel or self.closing:
                    raise TaskCancelled()
                self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
                os.chmod(self.root, 0o700)
                folder.mkdir(mode=0o700)
            with (folder / 'input').open('xb') as output:
                os.chmod(folder / 'input', 0o600)
                stream = request.stream().__aiter__()
                while True:
                    try:
                        chunk = await self.read_chunk(stream, task)
                    except StopAsyncIteration:
                        break
                    with self.condition:
                        if task.cancel or self.closing:
                            raise TaskCancelled()
                        if task.received + len(chunk) > task.body.size_bytes:
                            raise HTTPException(413, '实际文件大小超过声明限制，请重新提交。')
                        output.write(chunk)
                        task.received += len(chunk)
                        self.touch(task)
            with self.condition:
                if task.cancel or self.closing:
                    raise TaskCancelled()
                if task.received != task.body.size_bytes:
                    raise HTTPException(422, '文件上传不完整，请重新提交。')
                task.status = 'queued'
                self.touch(task)
                self.condition.notify_all()
                return task.public()
        except TaskCancelled:
            with self.condition:
                self.finish(task, 'cancelled')
                return task.public()
        except BaseException as error:
            with self.condition:
                if task.cancel:
                    self.finish(task, 'cancelled')
                else:
                    self.finish(task, 'failed', '文件上传中断或无效，请重新提交。')
            if isinstance(error, HTTPException):
                raise
            if isinstance(error, asyncio.TimeoutError):
                raise HTTPException(408, '文件上传超时，请重新提交。') from None
            if isinstance(error, Exception):
                raise HTTPException(503, '文件暂时无法保存，请稍后重新提交。') from None
            raise
        finally:
            self.upload_slots.release()

    def worker(self):
        while True:
            with self.condition:
                self.expire()
                if self.closing:
                    return
                task = next((task for task in self.tasks.values() if task.status == 'queued'
                             and (task.body.kind != 'video' or not self.video_running)), None)
                if task is None:
                    self.condition.wait(timeout=1)
                    continue
                task.status = 'processing'
                if task.body.kind == 'video':
                    self.video_running = True
                self.touch(task)
            try:
                with self.app.state.inference_scheduler.processing(video=task.body.kind == 'video'):
                    self.process(task)
            except TaskCancelled:
                with self.condition:
                    self.finish(task, 'cancelled')
            except Exception as error:
                with self.condition:
                    if task.cancel:
                        self.finish(task, 'cancelled')
                    else:
                        messages = {401: '登录会话已失效，任务已停止。', 403: '管理员暂时关闭了此检测功能。',
                                    404: '所选地块不存在或已不属于当前账号。',
                                    413: '文件超过当前大小限制，请重新提交。', 422: '文件无效，或识别作物与所选地块不一致。'}
                        self.finish(task, 'failed', messages.get(getattr(error, 'status_code', 0),
                                                                 '检测暂时无法完成，请稍后重新提交。'))
            finally:
                with self.condition:
                    if task.body.kind == 'video':
                        self.video_running = False
                    self.condition.notify_all()

    def process(self, task):
        limits = self.checkpoint(task)
        folder, body = self.folder(task), task.body
        provider = ScheduledProvider(self.app.state.inference_scheduler, self.app.state.inference,
                                     lambda: self.checkpoint(task))
        if body.kind == 'image':
            # Reuse the same decoded-pixel validation/EXIF/metadata semantics.
            image = self.read_image((folder / 'input').read_bytes(), limits['image_max_mb'] * 1024 * 1024)
            target = folder / 'image.jpg'
            try:
                with ImageOps.exif_transpose(image) as oriented, oriented.convert('RGB') as normalized:
                    normalized.save(target, format='JPEG', quality=90)
            finally:
                image.close()
            prediction = provider.predict(target, body.crop)
            samples = [(None, target, prediction)]
        else:
            self.checkpoint(task)
            _, samples = sample_video(folder / 'input', folder, provider, limits)
        targets = []
        try:
            # This lock arbitrates explicit cancellation/logout against commit.
            # It is never held during decoding, inference, or network upload.
            with self.condition, self.app.state.session() as db:
                if task.cancel or self.closing:
                    raise TaskCancelled()
                user = self.session_user(task, db)
                self.validate(body, db, user)
                plot = owned_plot(db, body.plot_id, user, lock=True) if body.plot_id else None
                rows = []
                for timestamp, source, prediction in samples:
                    crop = body.crop or prediction.crop
                    crops = {box['crop'] for box in prediction.boxes} or {crop}
                    if crop not in SUPPORTED_CROPS:
                        raise HTTPException(503, '模型未返回有效的作物识别结果。')
                    if plot and any(found != plot.crop for found in crops):
                        raise HTTPException(422, '检测作物与所选地块不一致。')
                    filename = f'{uuid4().hex}.jpg'
                    target = self.app.state.settings.upload_dir / filename
                    targets.append(target)
                    shutil.copyfile(source, target)
                    name = clean_filename(body.filename)
                    note = body.note.strip()
                    if timestamp is not None:
                        name = f'{name[:150]} · {timestamp:.3f}s'
                        note = f'{note}\n视频采样：{clean_filename(body.filename)} · {timestamp:.3f}s'.strip()
                    row = Detection(owner_id=user.id, name=name, crop=crop, plot=plot, status=prediction.status,
                                    result=prediction.label, confidence=prediction.confidence,
                                    image_url=f'/api/uploads/{filename}', is_demo=False, note=note)
                    if prediction.model:
                        row.prediction = DetectionPrediction(candidates=prediction.candidates,
                                                             model=prediction_snapshot(prediction))
                    db.add(row)
                    rows.append(row)
                db.flush()
                result_ids = [row.id for row in rows]
                db.commit()
                task.result_ids = result_ids
                self.finish(task, 'completed')
        except BaseException:
            for target in targets:
                target.unlink(missing_ok=True)
            raise
        try:
            self.app.state.cache.invalidate(task.user_id)
        except Exception:
            # Commit already won: an auxiliary cache failure cannot turn a
            # saved detection into a retryable task and create duplicate rows.
            logger.warning('Could not invalidate completed detection task cache.')


def install_detection_tasks(app, read_image):
    manager = DetectionTasks(app, read_image)
    app.state.detection_tasks = manager

    @app.post('/api/detection-tasks', status_code=201)
    def reserve_task(body: TaskBody, request: Request, user=Depends(current_user)):
        return manager.reserve(body, user, request.state.token_payload)

    @app.get('/api/detection-tasks')
    def list_tasks(request: Request, user=Depends(current_user)):
        with manager.condition:
            manager.expire()
            return [task.public() for task in manager.tasks.values()
                    if task.user_id == user.id and task.session['jti'] == request.state.token_payload['jti']]

    @app.get('/api/detection-tasks/{task_id}')
    def get_task(task_id: str, request: Request, user=Depends(current_user)):
        with manager.condition:
            manager.expire()
            return manager.owned(task_id, user, request.state.token_payload).public()

    @app.put('/api/detection-tasks/{task_id}/file', status_code=202)
    async def upload_task(task_id: str, request: Request, user=Depends(current_user)):
        with manager.condition:
            manager.expire()
            task = manager.owned(task_id, user, request.state.token_payload)
        return await manager.upload(request, task)

    @app.delete('/api/detection-tasks/{task_id}')
    def cancel_task(task_id: str, request: Request, user=Depends(current_user)):
        with manager.condition:
            return manager.cancel_task(manager.owned(task_id, user, request.state.token_payload))
