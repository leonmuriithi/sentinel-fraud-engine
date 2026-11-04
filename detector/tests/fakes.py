"""Test doubles for Redis and Kafka so the suite runs with no external services."""
import random
from collections import deque

from sentinel.velocity import RedisError


class FakePipeline:
    def __init__(self, redis):
        self._redis = redis
        self._ops = []

    def __getattr__(self, name):
        def queue(*args, **kwargs):
            self._ops.append((name, args, kwargs))
            return self
        return queue

    def execute(self):
        return [getattr(self._redis, "_" + n)(*a, **k) for n, a, k in self._ops]


class FakeRedis:
    def __init__(self):
        self.zsets, self.strings = {}, {}

    def pipeline(self, transaction=False):
        return FakePipeline(self)

    def _zremrangebyscore(self, key, lo, hi):
        z = self.zsets.setdefault(key, {})
        stale = [m for m, s in z.items() if lo <= s <= hi]
        for m in stale:
            del z[m]
        return len(stale)

    def _zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(mapping)
        return len(mapping)

    def _zcard(self, key):
        return len(self.zsets.get(key, {}))

    def _expire(self, key, ttl):
        return True

    def _get(self, key):
        return self.strings.get(key)

    def _set(self, key, value, ex=None):
        self.strings[key] = value
        return True


class DownRedis(FakeRedis):
    """Every pipeline execution fails, as if Redis were unreachable."""
    def pipeline(self, transaction=False):
        class _P(FakePipeline):
            def execute(self):
                raise RedisError("connection refused")
        return _P(self)


class FlakyRedis(FakeRedis):
    """Fails a fixed share of pipeline executions, deterministically."""
    def __init__(self, failure_rate, seed=1):
        super().__init__()
        self._rng = random.Random(seed)
        self._rate = failure_rate

    def pipeline(self, transaction=False):
        outer = self

        class _P(FakePipeline):
            def execute(self):
                if outer._rng.random() < outer._rate:
                    raise RedisError("timeout")
                return super().execute()
        return _P(self)


class FakeMessage:
    def __init__(self, value=None, error=None, key=None):
        self._value, self._error, self._key = value, error, key

    def value(self):
        return self._value

    def error(self):
        return self._error

    def key(self):
        return self._key


class FakeConsumer:
    """Plays back a script of messages, errors and exceptions."""
    def __init__(self, script):
        self._script = deque(script)
        self.commits = []

    def poll(self, timeout):
        if not self._script:
            return None
        item = self._script.popleft()
        if isinstance(item, Exception):
            raise item
        return item

    def commit(self, message=None, asynchronous=False):
        self.commits.append(message)


class FakeProducer:
    def __init__(self, fail_times=0):
        self.produced = []
        self.fail_times = fail_times

    def produce(self, topic, key=None, value=None):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise BufferError("local queue full")
        self.produced.append((topic, key, value))

    def flush(self, timeout=None):
        return 0
