"""Per-user velocity and location tracking in Redis.

If Redis is unavailable the tracker degrades instead of failing: it returns
neutral values and marks the signal as degraded, so scoring continues with the
model alone.
"""
import logging
import time
import uuid
from dataclasses import dataclass

try:
    from redis.exceptions import RedisError
except ImportError:  # lets the unit tests run without the redis package installed
    class RedisError(Exception):
        pass

log = logging.getLogger("sentinel.velocity")


@dataclass(frozen=True)
class VelocitySignal:
    velocity: int
    location_jump: bool
    degraded: bool = False


class VelocityTracker:
    def __init__(self, redis_client, window_seconds=3600, location_jump_seconds=60):
        self.redis = redis_client
        self.window = window_seconds
        self.jump_window = location_jump_seconds

    def observe(self, user_id, location, now=None):
        now = time.time() if now is None else now
        vel_key = f"sentinel:vel:{user_id}"
        loc_key = f"sentinel:loc:{user_id}"
        try:
            pipe = self.redis.pipeline(transaction=False)
            pipe.zremrangebyscore(vel_key, 0, now - self.window)
            pipe.zadd(vel_key, {uuid.uuid4().hex: now})
            pipe.zcard(vel_key)
            pipe.expire(vel_key, self.window * 2)
            pipe.get(loc_key)                                   # previous location (None = cache miss)
            pipe.set(loc_key, f"{location}|{now}", ex=self.window)
            results = pipe.execute()
        except RedisError as exc:
            log.warning("Redis unavailable, scoring without velocity signals: %s", exc)
            return VelocitySignal(velocity=1, location_jump=False, degraded=True)

        return VelocitySignal(velocity=int(results[2]),
                              location_jump=self._is_jump(results[4], location, now))

    def _is_jump(self, previous, location, now):
        if previous is None:
            return False                                         # cache miss: no history, no jump
        if isinstance(previous, bytes):
            previous = previous.decode()
        try:
            prev_location, prev_ts = previous.rsplit("|", 1)
            return prev_location != location and (now - float(prev_ts)) <= self.jump_window
        except ValueError:
            return False                                         # malformed cached value is ignored
