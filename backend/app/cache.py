import json
import logging

import redis

logger = logging.getLogger(__name__)


class DashboardCache:
    """Redis is a best-effort cache; DB remains the source of truth."""
    KEY = "agriscan:dashboard:v1"

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

    def get(self, days=7):
        if not self.client:
            return None
        try:
            value = self.client.get(f"{self.KEY}:{days}")
            return json.loads(value) if value else None
        except (redis.RedisError, ValueError):
            return None

    def set(self, value, days=7):
        if self.client:
            try:
                self.client.setex(f"{self.KEY}:{days}", 30, json.dumps(value, ensure_ascii=False))
            except redis.RedisError:
                logger.warning("Redis cache unavailable; serving directly from database.")

    def invalidate(self):
        if self.client:
            try:
                self.client.delete(f"{self.KEY}:7", f"{self.KEY}:30")
            except redis.RedisError:
                logger.warning("Could not invalidate Redis cache; TTL limits staleness to 30 seconds.")

    def close(self):
        if self.client:
            self.client.close()
