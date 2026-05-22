from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


async def with_timeout[T](operation: Awaitable[T], timeout_seconds: float) -> T:
    return await asyncio.wait_for(operation, timeout=timeout_seconds)


async def retry_async[T](
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    initial_delay_seconds: float = 0.05,
) -> T:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await operation()
        except Exception as exc:  # noqa: BLE001 - example utility should preserve final error
            last_error = exc
            if attempt < attempts - 1:
                await asyncio.sleep(initial_delay_seconds * (2**attempt))
    assert last_error is not None
    raise last_error
