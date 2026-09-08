from __future__ import annotations

import httpx

from gimme_collectors.pipeline.fetch import Fetcher, FetchResult


def test_fetcher_caches_and_sinks(tmp_path):
    calls = {"n": 0}
    seen: list[FetchResult] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        assert request.headers["user-agent"].startswith("test-agent")
        return httpx.Response(
            200, json={"ok": calls["n"]}, headers={"content-type": "application/json"}
        )

    fetcher = Fetcher(
        "espn",
        cache_dir=tmp_path,
        user_agent="test-agent/1",
        rate_limit_per_min=6000,
        cache_ttl_seconds=600,
        sink=seen.append,
        transport=httpx.MockTransport(handler),
    )
    with fetcher:
        first, r1 = fetcher.get_json("https://example.test/x")
        second, r2 = fetcher.get_json("https://example.test/x")
        third, r3 = fetcher.get_json("https://example.test/x", use_cache=False)

    assert first == {"ok": 1} and second == {"ok": 1} and third == {"ok": 2}
    assert not r1.from_cache and r2.from_cache and not r3.from_cache
    assert calls["n"] == 2
    assert len(seen) == 2  # only real fetches reach the sink
    assert r1.content_hash == r2.content_hash
