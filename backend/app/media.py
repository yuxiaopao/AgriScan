"""Bounded camera previews and honest, sampled video classification."""
from collections import OrderedDict, deque
from contextlib import contextmanager
from datetime import timezone
import io
from importlib.util import find_spec
import logging
import math
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from threading import Lock
from time import monotonic
from uuid import uuid4
import warnings

from fastapi import Depends, File, Form, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

from .db import Detection, DetectionPrediction, Plot, utcnow
from .inference import SUPPORTED_CROPS, prediction_snapshot, public_prediction_model
from .security import current_user
from .runtime_config import client_config_for
from .ownership import associated_plot, owned_plot
from .inference_scheduler import ScheduledProvider

logger = logging.getLogger(__name__)
MAX_FRAME_BYTES = 10 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_VIDEO_SECONDS = 60
MAX_SAMPLED_FRAMES = 8
MAX_PIXELS = 12_000_000
FRAME_MIN_INTERVAL_MS = 750


class MediaRateLimiter:
    """Small process-local admission control; the model has its own inference lock."""
    def __init__(self):
        self.events = OrderedDict()
        self.lock = Lock()

    def check(self, user_id, mode, frame_interval_ms=FRAME_MIN_INTERVAL_MS):
        now = monotonic()
        window, limit = (frame_interval_ms / 1000, 1) if mode == 'frame' else (60, 3)
        key = (user_id, mode)
        with self.lock:
            events = self.events.setdefault(key, deque())
            while events and events[0] <= now - window:
                events.popleft()
            if len(events) >= limit:
                retry = max(1, math.ceil(events[0] + window - now))
                raise HTTPException(429, '请求过于频繁，请稍后重试。', headers={'Retry-After': str(retry)})
            events.append(now)
            self.events.move_to_end(key)
            while len(self.events) > 2048:
                self.events.popitem(last=False)


async def read_bounded(file, maximum):
    try:
        data = await file.read(maximum + 1)
    finally:
        await file.close()
    if len(data) > maximum:
        raise HTTPException(413, f'文件不能超过 {maximum // (1024 * 1024)} MB。')
    return data


def check_prediction(prediction, provider):
    if (prediction.crop not in SUPPORTED_CROPS or prediction.crop not in provider.supported_crops
            or prediction.status not in {'healthy', 'attention'} or not prediction.label
            or prediction.confidence is None or not math.isfinite(prediction.confidence)
            or not 0 <= prediction.confidence <= 1):
        raise HTTPException(503, '模型未返回有效的作物分类结果，请稍后重试。')
    return prediction


def decode_frame(data, destination):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as original:
                if original.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise HTTPException(422, '仅支持 JPEG、PNG、WebP 相机图片。')
                if original.width * original.height > MAX_PIXELS:
                    raise HTTPException(422, '图片分辨率过大，请降低至 1200 万像素以内。')
                original.verify()
            with Image.open(io.BytesIO(data)) as original:
                image = ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((1600, 1600))
                image.save(destination, format='JPEG', quality=90)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, '图片无效或已损坏，请重新拍摄。')


def frame_result(data, folder, provider):
    path = folder / 'camera.jpg'
    decode_frame(data, path)
    return check_prediction(provider.predict(path, None), provider)


def video_suffix(data):
    # Only local binary video containers; playlists and arbitrary URLs never reach FFmpeg.
    if len(data) >= 16 and data[4:8] == b'ftyp':
        return '.mp4'
    if data.startswith(b'\x1aE\xdf\xa3'):
        return '.webm'
    if data[:4] == b'RIFF' and data[8:12] == b'AVI ':
        return '.avi'
    raise HTTPException(422, '视频格式无效，仅支持 MP4、MOV、WebM 或 AVI 视频。')


def sample_video(data, folder, provider, limits=None):
    limits = limits or {'video_max_seconds': MAX_VIDEO_SECONDS, 'video_max_frames': MAX_SAMPLED_FRAMES}
    try:
        import cv2
    except ImportError:
        raise HTTPException(503, '视频解码组件尚未安装，请联系管理员安装媒体依赖。')
    if isinstance(data, Path):
        with data.open('rb') as header:
            video_suffix(header.read(16))
        source = data
    else:
        source = folder / ('source' + video_suffix(data))
        source.write_bytes(data)
    capture = cv2.VideoCapture(str(source), cv2.CAP_FFMPEG, [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000,
    ])
    try:
        if not capture.isOpened():
            raise HTTPException(422, '视频无法解码，请使用常见编码重新导出视频。')
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        count = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width, height = capture.get(cv2.CAP_PROP_FRAME_WIDTH), capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
        if (not all(math.isfinite(value) for value in (fps, count, width, height))
                or not 0 < fps <= 120 or count < 1 or count != int(count)
                or min(width, height) < 1 or max(width, height) > 4096 or width * height > MAX_PIXELS):
            raise HTTPException(422, '视频帧率、尺寸或帧数无效，请使用 4K 以内的常见视频。')
        duration = count / fps
        if duration > limits['video_max_seconds'] or count > 7200:
            raise HTTPException(422, f"视频不能超过 {limits['video_max_seconds']} 秒，请截取较短片段后上传。")
        count = int(count)
        samples = min(limits['video_max_frames'], count)
        indices = [0] if samples == 1 else [round(i * (count - 1) / (samples - 1)) for i in range(samples)]
        results = []
        for index in indices:
            if not capture.set(cv2.CAP_PROP_POS_FRAMES, index):
                raise HTTPException(422, '视频无法准确抽帧，请重新导出后上传。')
            success, frame = capture.read()
            if not success or frame is None:
                raise HTTPException(422, '视频存在无法解码的采样帧，请重新导出后上传。')
            if (frame.ndim != 3 or frame.shape[2] != 3 or frame.shape[0] * frame.shape[1] > MAX_PIXELS
                    or max(frame.shape[:2]) > 4096):
                raise HTTPException(422, '视频帧分辨率超出限制。')
            actual_index = capture.get(cv2.CAP_PROP_POS_FRAMES) - 1
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if (not math.isfinite(actual_index) or abs(actual_index - index) > 0.5
                    or not math.isfinite(timestamp) or not 0 <= timestamp <= limits['video_max_seconds']
                    or (results and timestamp <= results[-1][0])):
                raise HTTPException(422, '视频时间戳无效，无法提供可靠的采样时间，请重新导出视频。')
            target = folder / f'frame-{index}.jpg'
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            image.thumbnail((1600, 1600))
            image.save(target, format='JPEG', quality=90)
            prediction = check_prediction(provider.predict(target, None), provider)
            results.append((round(timestamp, 6), target, prediction))
        # Reject a container whose declared final frame is not its actual end.
        if capture.grab():
            raise HTTPException(422, '视频帧数与容器声明不一致，请重新导出视频。')
        return round(duration, 6), results
    except cv2.error:
        raise HTTPException(422, '视频解码失败，请使用常见编码重新导出视频。')
    finally:
        capture.release()


def detection_data(row):
    plot = associated_plot(row)
    return {
        'id': row.id, 'name': row.name, 'crop': row.crop, 'plot_id': plot.id if plot else None,
        'plot_name': plot.name if plot else '未关联地块', 'status': row.status,
        'result': row.result, 'confidence': row.confidence,
        'candidates': row.prediction.candidates if row.prediction else [],
        'prediction_model': public_prediction_model(row.prediction.model) if row.prediction else None,
        'boxes': row.prediction.model.get('boxes', []) if row.prediction else [],
        'created_at': row.created_at.replace(tzinfo=timezone.utc).isoformat(),
        'image_url': row.image_url, 'is_demo': False, 'note': row.note,
    }


def install_media(app, get_db):
    app.state.media_guard = app.state.inference_scheduler.video_slot
    app.state.media_limiter = MediaRateLimiter()

    def effective_configuration():
        config = client_config_for(app)
        return config.get('features', {}), {
            'image_max_mb': 10, 'video_max_mb': 50, 'video_max_seconds': 60,
            'video_max_frames': 8, 'frame_interval_ms': 750, **config.get('limits', {}),
        }

    @app.get('/api/media/capabilities')
    def media_capabilities():
        features, limits = effective_configuration()
        return {'video_max_mb': limits['video_max_mb'], 'video_max_seconds': limits['video_max_seconds'],
                'video_max_frames': limits['video_max_frames'], 'frame_min_interval_ms': limits['frame_interval_ms'],
                'video_enabled': features.get('video_detection', True) and find_spec('cv2') is not None,
                'live_enabled': features.get('live_detection', True),
                'mode': 'leaf_classification', 'model_ready': app.state.inference.status == 'ready'}

    @contextmanager
    def admitted(user, mode):
        features, limits = effective_configuration()
        if not features.get('live_detection' if mode == 'frame' else 'video_detection', True):
            raise HTTPException(403, '管理员暂时关闭了此检测功能。')
        provider = app.state.inference
        if provider.status != 'ready':
            raise HTTPException(503, '作物分类模型尚未就绪，暂时无法检测图片或视频。')
        app.state.media_limiter.check(user.id, mode, limits['frame_interval_ms'])
        yield ScheduledProvider(app.state.inference_scheduler, provider), limits

    @app.post('/api/media/frame')
    async def camera_frame(file: UploadFile = File(...), user=Depends(current_user)):
        async with app.state.inference_scheduler.legacy_processing():
            return await camera_frame_admitted(file, user)

    async def camera_frame_admitted(file, user):
        with admitted(user, 'frame') as (provider, limits):
            data = await read_bounded(file, limits['image_max_mb'] * 1024 * 1024)
            with TemporaryDirectory(prefix='agriscan-camera-') as folder:
                prediction = await run_in_threadpool(frame_result, data, Path(folder), provider)
        return {
            'id': uuid4().hex, 'name': '相机实时预览', 'crop': prediction.crop, 'plot_id': None,
            'plot_name': '未关联地块', 'status': prediction.status, 'result': prediction.label,
            'confidence': prediction.confidence, 'candidates': prediction.candidates,
            'boxes': prediction.boxes,
            'prediction_model': prediction.model, 'created_at': utcnow().replace(tzinfo=timezone.utc).isoformat(),
            'image_url': None, 'is_demo': False, 'note': '相机实时预览，不自动保存。', 'source': 'camera_frame',
        }

    @app.post('/api/media/video')
    async def uploaded_video(file: UploadFile = File(...), plot_id: str | None = Form(None),
                             note: str = Form(default='', max_length=2000),
                             user=Depends(current_user), db=Depends(get_db)):
        if plot_id:
            owned_plot(db, plot_id, user)
        async with app.state.inference_scheduler.legacy_processing(video=True):
            return await video_admitted(file, plot_id, note, user, db)

    async def video_admitted(file, plot_id, note, user, db):
        plot = owned_plot(db, plot_id, user) if plot_id else None
        with admitted(user, 'video') as (provider, limits):
            data = await read_bounded(file, limits['video_max_mb'] * 1024 * 1024)
            filename = (file.filename or 'video').replace('\\', '/').split('/')[-1][:180]
            video_id = uuid4().hex
            targets, rows = [], []
            with TemporaryDirectory(prefix='agriscan-video-') as folder:
                duration, samples = await run_in_threadpool(sample_video, data, Path(folder), provider, limits)
                if plot_id:
                    plot = owned_plot(db, plot_id, user, lock=True)
                if plot and any(prediction.crop != plot.crop or any(box['crop'] != plot.crop for box in prediction.boxes)
                                for _, _, prediction in samples):
                    raise HTTPException(422, '视频识别作物与所选地块不一致，请更换地块或取消关联后重试。')
                try:
                    for timestamp, source, prediction in samples:
                        image_name = f'{uuid4().hex}.jpg'
                        target = app.state.settings.upload_dir / image_name
                        targets.append(target)
                        shutil.copyfile(source, target)
                        row = Detection(id=uuid4().hex, name=f'{filename[:150]} · {timestamp:.3f}s',
                                        owner_id=user.id,
                                        crop=prediction.crop, plot=plot, status=prediction.status,
                                        result=prediction.label, confidence=prediction.confidence,
                                        image_url=f'/api/uploads/{image_name}', is_demo=False,
                                        note=f'{note.strip()}\n视频采样：{filename} · {timestamp:.3f}s'.strip())
                        if prediction.model:
                            row.prediction = DetectionPrediction(candidates=prediction.candidates, model=prediction_snapshot(prediction))
                        db.add(row)
                        rows.append((timestamp, row))
                    db.flush()
                    results = [{'timestamp_seconds': timestamp, 'detection': detection_data(row)}
                               for timestamp, row in rows]
                    db.commit()
                except Exception as error:
                    db.rollback()
                    for target in targets:
                        try:
                            target.unlink(missing_ok=True)
                        except OSError:
                            logger.warning('Could not remove failed video sample %s.', target.name, exc_info=True)
                    if isinstance(error, HTTPException):
                        raise
                    logger.exception('Could not save video samples.')
                    raise HTTPException(503, '视频采样暂时无法保存，请稍后重试。') from error
        app.state.cache.invalidate(user.id)
        return {'id': video_id, 'filename': filename, 'duration_seconds': duration,
                'sampled_frames': len(results), 'results': results,
                'summary': {'total': len(results), 'healthy': sum(row.status == 'healthy' for _, row in rows),
                            'attention': sum(row.status == 'attention' for _, row in rows)},
                'source': 'sampled_video'}
