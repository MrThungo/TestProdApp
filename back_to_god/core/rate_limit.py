from __future__ import annotations

import time
from collections import deque

from flask import request


_attempts: dict[str, deque[float]] = {}


def _client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip() or "unknown"
    return request.remote_addr or "unknown"


def _bucket(scope: str, key: str) -> str:
    compact_key = " ".join((key or "").strip().lower().split())[:180]
    return f"{scope}:{_client_ip()}:{compact_key}"


def _prune(bucket: str, window_seconds: int, now: float) -> deque[float]:
    window = _attempts.get(bucket)
    if window is None:
        window = deque()
        _attempts[bucket] = window
    while window and now - window[0] >= window_seconds:
        window.popleft()
    return window


def is_limited(scope: str, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
    now = time.time()
    bucket = _bucket(scope, key)
    window = _prune(bucket, window_seconds, now)
    if len(window) < limit:
        return False, 0
    retry_after = max(1, int(window_seconds - (now - window[0])))
    return True, retry_after


def record_attempt(scope: str, key: str, *, window_seconds: int) -> None:
    now = time.time()
    bucket = _bucket(scope, key)
    window = _prune(bucket, window_seconds, now)
    window.append(now)


def clear_attempts(scope: str, key: str) -> None:
    _attempts.pop(_bucket(scope, key), None)
