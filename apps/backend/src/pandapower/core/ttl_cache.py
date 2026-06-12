"""Tiny in-process TTL cache for hot, frequently-polled read endpoints.

Admin status screens poll every 5-30s and each call fans out into several
`count="exact"` queries (full COUNT scans on large tables). Caching the
*result* for a few seconds collapses N concurrent pollers (and multiple open
tabs) into at most one DB hit per TTL window, which is the single biggest
relief for Supabase compute. Approximate freshness is fine for status panels.

Usage:

    from pandapower.core.ttl_cache import cached

    @router.get("/status")
    @cached(ttl=20)
    async def get_status(...):
        ...

The cache key ignores `Depends`-injected args (Supabase client, etc.) by
keying only on the endpoint and its hashable positional/keyword args.
"""
from __future__ import annotations

import asyncio
import functools
import time
from typing import Any, Callable

_store: dict[Any, tuple[float, Any]] = {}
_locks: dict[Any, asyncio.Lock] = {}


def _key(fn: Callable, args: tuple, kwargs: dict) -> Any:
    hashable_args = tuple(a for a in args if isinstance(a, (str, int, float, bool, type(None))))
    hashable_kwargs = tuple(
        (k, v) for k, v in sorted(kwargs.items())
        if isinstance(v, (str, int, float, bool, type(None)))
    )
    return (fn.__module__, fn.__qualname__, hashable_args, hashable_kwargs)


def cached(ttl: float = 20.0) -> Callable:
    """Cache an async endpoint's return value for `ttl` seconds.

    Concurrent callers within the window share a single in-flight computation
    (via a per-key lock), so a burst of pollers never stampedes the DB.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _key(fn, args, kwargs)
            now = time.monotonic()

            hit = _store.get(key)
            if hit is not None and (now - hit[0]) < ttl:
                return hit[1]

            lock = _locks.setdefault(key, asyncio.Lock())
            async with lock:
                # Re-check: another coroutine may have filled it while we waited.
                hit = _store.get(key)
                now = time.monotonic()
                if hit is not None and (now - hit[0]) < ttl:
                    return hit[1]

                result = await fn(*args, **kwargs)
                _store[key] = (time.monotonic(), result)
                return result

        return wrapper

    return decorator


def invalidate_all() -> None:
    """Drop every cached entry (e.g. after a manual trigger mutates counts)."""
    _store.clear()
