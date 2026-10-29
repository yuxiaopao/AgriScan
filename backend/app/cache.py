import json
import logging

import redis

logger = logging.getLogger(__name__)


class DashboardCache:
    """Redis is a best-effort cache; DB remains the source of truth."""
    KEY = "agriscan:dashboard:v2"

    def __init__(self, url):
        self.client = redis.Redis.from_url(url, socket_connect_timeout=0.4, socket_timeout=0.4) if url else None

    def status(self):
        if not self.client:
            return "disabled"
        try:
            self.client.ping()
            return "connected"
        except redis.RedisError:
            return "unavailable"

    def key(self, days, user_id):
        scope = 'anonymous-demo' if user_id is None else 'user:' + user_id
        return f'{self.KEY}:{scope}:{days}'

    def get(self, days=7, user_id=None):
        if not self.client:
            return None
        try:
            value = self.client.get(self.key(days, user_id))
            return json.loads(value) if value else None
        except (redis.RedisError, ValueError):
            return None

    def set(self, value, days=7, user_id=None):
        if self.client:
            try:
                self.client.setex(self.key(days, user_id), 30, json.dumps(value, ensure_ascii=False))
            except redis.RedisError:
                logger.warning("Redis cache unavailable; serving directly from database.")

    def invalidate(self, user_id=None):
        if self.client:
            try:
                if user_id is not None:
                    self.client.delete(self.key(7, user_id), self.key(30, user_id))
                else:
                    batch = []
                    for key in self.client.scan_iter(match=f'{self.KEY}:*', count=128):
                        batch.append(key)
                        if len(batch) == 128:
                            self.client.delete(*batch)
                            batch = []
                    if batch:
                        self.client.delete(*batch)
            except redis.RedisError:
                logger.warning("Could not invalidate Redis cache; TTL limits staleness to 30 seconds.")

    def close(self):
        if self.client:
            self.client.close()
