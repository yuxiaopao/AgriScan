"""One fair inference lane for the single, shared pair of ONNX sessions."""
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from threading import BoundedSemaphore, Condition, Lock

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool


class InferenceScheduler:
    def __init__(self):
        self.condition = Condition()
        self.waiters = deque()
        self.running = False
        self.process_slots = BoundedSemaphore(2)
        self.legacy_slots = BoundedSemaphore(8)
        self.video_slot = Lock()

    def predict(self, provider, path, crop=None, checkpoint=None):
        ticket = object()
        with self.condition:
            self.waiters.append(ticket)
            self.condition.wait_for(lambda: not self.running and self.waiters[0] is ticket)
            self.waiters.popleft()
            self.running = True
        try:
            if checkpoint:
                checkpoint()
            return provider.predict(path, crop)
        finally:
            with self.condition:
                self.running = False
                self.condition.notify_all()

    @contextmanager
    def processing(self, video=False):
        # Bound simultaneous full-resolution image/video decoders as well as ORT.
        if video:
            self.video_slot.acquire()
        try:
            with self.process_slots:
                yield
        finally:
            if video:
                self.video_slot.release()

    @asynccontextmanager
    async def legacy_processing(self, video=False):
        if not self.legacy_slots.acquire(blocking=False):
            raise HTTPException(429, '检测队列已满，请稍后重试。', headers={'Retry-After': '2'})
        acquired = False
        video_acquired = False
        try:
            if video:
                await run_in_threadpool(self.video_slot.acquire)
                video_acquired = True
            await run_in_threadpool(self.process_slots.acquire)
            acquired = True
            yield
        finally:
            if acquired:
                self.process_slots.release()
            if video_acquired:
                self.video_slot.release()
            self.legacy_slots.release()


class ScheduledProvider:
    """Preserve predict(path, crop) and provider metadata for media callers."""
    def __init__(self, scheduler, provider, checkpoint=None):
        self.scheduler, self.provider, self.checkpoint = scheduler, provider, checkpoint

    def __getattr__(self, name):
        return getattr(self.provider, name)

    def predict(self, path, crop=None):
        if self.checkpoint:
            self.checkpoint()
        result = self.scheduler.predict(self.provider, path, crop, self.checkpoint)
        if self.checkpoint:
            self.checkpoint()
        return result
