from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock

from fastapi import Request

from app.core.errors import RateLimitExceededError


@dataclass
class WindowCounter:
    window_start: float
    count: int = 0


@dataclass
class InMemoryRateLimiter:
    window_seconds: int = 60
    _counters: dict[str, WindowCounter] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def check(self, key: str, limit: int) -> None:
        now = time.monotonic()
        with self._lock:
            counter = self._counters.get(key)
            if counter is None or now - counter.window_start >= self.window_seconds:
                self._counters[key] = WindowCounter(window_start=now, count=1)
                return

            if counter.count >= limit:
                raise RateLimitExceededError()

            counter.count += 1


def client_key(request: Request, route_name: str, tenant_id: str | None = None) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "unknown"

    tenant_part = tenant_id or "unknown-tenant"
    return f"{route_name}:{tenant_part}:{client_ip}"
