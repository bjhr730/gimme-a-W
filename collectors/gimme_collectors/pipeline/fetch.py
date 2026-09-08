"""Polite HTTP fetching: per-source throttle, on-disk cache, raw-page capture.

Every response is cached on disk keyed by URL so a parser bug never forces a
re-fetch, and every fetch can be forwarded to a sink (the raw_page table).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    content_type: str | None
    body: str
    fetched_at: datetime
    from_cache: bool

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()

    def json(self) -> Any:
        return json.loads(self.body)


RawSink = Callable[[FetchResult], None]


class Fetcher:
    """One fetcher per source. Not thread-safe; collectors are sequential by design."""

    def __init__(
        self,
        source: str,
        *,
        cache_dir: Path,
        user_agent: str,
        rate_limit_per_min: int = 60,
        cache_ttl_seconds: int = 600,
        timeout: float = 60.0,
        retries: int = 2,
        sink: RawSink | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.source = source
        self.cache_dir = cache_dir / source
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = 60.0 / max(rate_limit_per_min, 1)
        self.ttl = cache_ttl_seconds
        self.retries = max(retries, 0)
        self.sink = sink
        self._last_request = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/json, text/html;q=0.5"},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    # ---------------------------------------------------------------- cache

    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / (hashlib.sha256(url.encode("utf-8")).hexdigest() + ".json")

    def _read_cache(self, url: str) -> FetchResult | None:
        path = self._cache_path(url)
        if not path.is_file():
            return None
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        fetched_at = datetime.fromisoformat(entry["fetched_at"])
        if (datetime.now(UTC) - fetched_at).total_seconds() > self.ttl:
            return None
        return FetchResult(
            url=url,
            status_code=entry["status_code"],
            content_type=entry.get("content_type"),
            body=entry["body"],
            fetched_at=fetched_at,
            from_cache=True,
        )

    def _write_cache(self, result: FetchResult) -> None:
        payload = {
            "url": result.url,
            "status_code": result.status_code,
            "content_type": result.content_type,
            "fetched_at": result.fetched_at.isoformat(),
            "body": result.body,
        }
        self._cache_path(result.url).write_text(json.dumps(payload), encoding="utf-8")

    # ---------------------------------------------------------------- fetch

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last_request)
        if wait > 0:
            time.sleep(wait)
        self._last_request = time.monotonic()

    def _get_with_retry(self, url: str) -> httpx.Response:
        """Retry transport errors and timeouts with exponential backoff (1s, 2s, ...)."""
        for attempt in range(self.retries + 1):
            try:
                return self._client.get(url)
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt == self.retries:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")

    def get(self, url: str, *, use_cache: bool = True) -> FetchResult:
        if use_cache:
            cached = self._read_cache(url)
            if cached is not None:
                return cached
        self._throttle()
        response = self._get_with_retry(url)
        response.raise_for_status()
        result = FetchResult(
            url=url,
            status_code=response.status_code,
            content_type=response.headers.get("content-type"),
            body=response.text,
            fetched_at=datetime.now(UTC),
            from_cache=False,
        )
        self._write_cache(result)
        if self.sink is not None:
            self.sink(result)
        return result

    def get_json(self, url: str, *, use_cache: bool = True) -> tuple[Any, FetchResult]:
        result = self.get(url, use_cache=use_cache)
        return result.json(), result

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Fetcher:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
