"""Query expansion: variant generation and multi-variant Bing collection."""

from __future__ import annotations

import json
from typing import Any

import pytest

import image_scraper.adapters.bing as bing_module
from image_scraper.domain.expansion import expand_query


def test_expand_query_adds_plural_and_modifiers() -> None:
    assert expand_query("cat") == ["cat", "cats", "cat photo", "cat wallpaper", "cat picture"]


def test_expand_query_skips_plural_when_already_plural() -> None:
    variants = expand_query("cats")
    assert variants[0] == "cats"
    assert "catss" not in variants


def test_expand_query_normalizes_whitespace_and_empty() -> None:
    assert expand_query("  vintage  car ")[:2] == ["vintage car", "vintage cars"]
    assert expand_query("   ") == []


def _anchor(url: str) -> str:
    payload = json.dumps({"murl": url, "turl": url.replace(".jpg", "_t.jpg")})
    return f"<a class='iusc' m='{payload}'></a>"


class FakeBingResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        pass


class FakeBingSession:
    def __init__(self, pages: dict[str, str]) -> None:
        self._pages = pages
        self.headers: dict[str, str] = {}
        self.queries: list[str] = []

    def get(self, *args: Any, **kwargs: Any) -> FakeBingResponse:
        query = kwargs["params"]["q"]
        self.queries.append(query)
        return FakeBingResponse(self._pages.get(query, ""))


def test_multi_variant_collection_dedupes_across_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        "cat": _anchor("http://x/1.jpg") + _anchor("http://x/2.jpg"),
        "cats": _anchor("http://x/2.jpg") + _anchor("http://x/3.jpg"),
    }
    session = FakeBingSession(pages)
    monkeypatch.setattr(bing_module.requests, "Session", lambda: session)
    candidates = bing_module._collect_candidates(
        query="cat", limit=10, timeout=5.0, variants=["cat", "cats"]
    )
    assert [c.url for c in candidates] == ["http://x/1.jpg", "http://x/2.jpg", "http://x/3.jpg"]
    assert session.queries == ["cat", "cats"]


def test_collection_stops_at_limit_without_fetching_more_variants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {"cat": _anchor("http://x/1.jpg") + _anchor("http://x/2.jpg")}
    session = FakeBingSession(pages)
    monkeypatch.setattr(bing_module.requests, "Session", lambda: session)
    candidates = bing_module._collect_candidates(
        query="cat", limit=2, timeout=5.0, variants=["cat", "cats"]
    )
    assert len(candidates) == 2
    assert session.queries == ["cat"]


def test_first_variant_failure_raises_when_nothing_collected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import requests

    from image_scraper.errors import EngineError

    class FailingSession(FakeBingSession):
        def get(self, *args: Any, **kwargs: Any) -> FakeBingResponse:
            raise requests.ConnectionError("down")

    monkeypatch.setattr(bing_module.requests, "Session", lambda: FailingSession({}))
    with pytest.raises(EngineError):
        bing_module._collect_candidates(query="cat", limit=5, timeout=5.0)
