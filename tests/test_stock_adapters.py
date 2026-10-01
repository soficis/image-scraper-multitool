"""Pexels/Pixabay adapters: parsing, pagination, auth resolution."""

from __future__ import annotations

from typing import Any

import pytest

import image_scraper.adapters.pexels as pexels_module
import image_scraper.adapters.pixabay as pixabay_module
import image_scraper.adapters.stock_api as stock_api_module
from image_scraper.errors import ConfigurationError


class FakeJsonResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> Any:
        return self._payload


class FakeJsonSession:
    def __init__(self, pages: list[Any]) -> None:
        self._pages = pages
        self.headers: dict[str, str] = {}
        self.calls = 0

    def get(self, *args: Any, **kwargs: Any) -> FakeJsonResponse:
        self.calls += 1
        return FakeJsonResponse(self._pages[min(self.calls - 1, len(self._pages) - 1)])


def _pexels_photo(url: str) -> dict[str, Any]:
    return {"src": {"original": url}}


def test_pexels_paginates_and_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    page1 = {"photos": [_pexels_photo(f"http://x/p{i}.jpg") for i in range(80)]}
    page2 = {"photos": [_pexels_photo("http://x/p0.jpg"), _pexels_photo("http://x/new.jpg")]}
    session = FakeJsonSession([page1, page2])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    candidates = pexels_module._collect_candidates(
        query="cat", limit=85, timeout=5.0, api_key="key"
    )
    assert len(candidates) == 81
    assert session.calls == 2


def test_pixabay_single_short_page_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "hits": [
            {"largeImageURL": "http://y/a.jpg"},
            {"largeImageURL": "http://y/b.jpg"},
            {"largeImageURL": "http://y/c.jpg"},
        ]
    }
    session = FakeJsonSession([payload])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    candidates = pixabay_module._collect_candidates(
        query="cat", limit=10, timeout=5.0, api_key="key"
    )
    assert [c.url for c in candidates] == ["http://y/a.jpg", "http://y/b.jpg", "http://y/c.jpg"]
    assert session.calls == 1


def test_missing_keys_raise_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        stock_api_module.resolve_api_key(
            engine="pexels",
            explicit_key=None,
            env_var="PEXELS_API_KEY",
            signup_url="https://www.pexels.com/api/",
        )
    with pytest.raises(ConfigurationError):
        stock_api_module.resolve_api_key(
            engine="pixabay",
            explicit_key="",
            env_var="PIXABAY_API_KEY",
            signup_url="https://pixabay.com/api/docs/",
        )


def test_env_var_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEXELS_API_KEY", "env-key")
    monkeypatch.setenv("PIXABAY_API_KEY", "env-key-2")
    assert (
        stock_api_module.resolve_api_key(
            engine="pexels",
            explicit_key=None,
            env_var="PEXELS_API_KEY",
            signup_url="https://www.pexels.com/api/",
        )
        == "env-key"
    )
    assert (
        stock_api_module.resolve_api_key(
            engine="pixabay",
            explicit_key=None,
            env_var="PIXABAY_API_KEY",
            signup_url="https://pixabay.com/api/docs/",
        )
        == "env-key-2"
    )


def test_cli_accepts_new_engines_and_keys() -> None:
    from image_scraper.cli.main import _build_options, build_parser

    parser = build_parser()
    options = _build_options(
        parser.parse_args(
            ["cats", "--engine", "pexels", "--engine", "pixabay", "--pexels-api-key", "k1"]
        )
    )
    assert list(options.engines) == ["pexels", "pixabay"]
    assert options.pexels_api_key == "k1"


def test_max_pages_bounds_always_full_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    page = {"photos": [_pexels_photo(f"http://x/p{i}.jpg") for i in range(80)]}
    session = FakeJsonSession([page])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    urls = stock_api_module.fetch_paginated_urls(
        operation="test_collect",
        query="cat",
        search_url="http://x/search",
        base_params={"query": "cat", "per_page": "80"},
        extra_headers=None,
        limit=1000,
        timeout=5.0,
        items_key="photos",
        extract_url=lambda photo: photo["src"]["original"],
        max_pages=2,
    )
    assert len(urls) == 80
    assert session.calls == 2


class _RecordingThrottler:
    instances: list[_RecordingThrottler] = []

    def __init__(self, min_interval: float = 0.0) -> None:
        self.min_interval = min_interval
        _RecordingThrottler.instances.append(self)

    def wait(self, host: str) -> None:
        pass


def test_min_interval_threading(monkeypatch: pytest.MonkeyPatch) -> None:
    _RecordingThrottler.instances.clear()
    monkeypatch.setattr(stock_api_module, "HostThrottler", _RecordingThrottler)
    page = {"photos": [_pexels_photo("http://x/p0.jpg")]}
    session = FakeJsonSession([page])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    pexels_module._collect_candidates(query="cat", limit=1, timeout=5.0, api_key="key")
    assert _RecordingThrottler.instances[-1].min_interval == (
        stock_api_module.HOST_MIN_INTERVAL_SECONDS
    )

    _RecordingThrottler.instances.clear()
    import image_scraper.adapters.openverse as openverse_module

    payload = {"results": [{"url": "http://z/a.jpg"}]}
    session = FakeJsonSession([payload])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    openverse_module._collect_candidates(query="cat", limit=1, timeout=5.0)
    assert _RecordingThrottler.instances[-1].min_interval == 1.0


class _BadJsonResponse(FakeJsonResponse):
    def json(self) -> Any:
        raise ValueError("not json")


class _BadJsonSession(FakeJsonSession):
    def get(self, *args: Any, **kwargs: Any) -> _BadJsonResponse:
        self.calls += 1
        return _BadJsonResponse(None)


def test_unreadable_response_raises_engine_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from image_scraper.errors import EngineError

    session = _BadJsonSession([None])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    with pytest.raises(EngineError):
        pexels_module._collect_candidates(query="cat", limit=5, timeout=5.0, api_key="key")


def test_non_dict_payload_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeJsonSession([[1, 2, 3]])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    urls = stock_api_module.fetch_paginated_urls(
        operation="test_collect",
        query="cat",
        search_url="http://x/search",
        base_params={"query": "cat", "per_page": "80"},
        extra_headers=None,
        limit=5,
        timeout=5.0,
        items_key="photos",
        extract_url=lambda photo: "",
    )
    assert urls == []
    assert session.calls == 1


def test_urls_to_candidates_fallback_names_and_referrer() -> None:
    candidates = stock_api_module.urls_to_candidates(
        ["http://x/photo.jpg", "http://x/", "http://y/pic.png"],
        fallback_prefix="openverse",
        referrer="https://openverse.org/",
    )
    assert [c.url for c in candidates] == ["http://x/photo.jpg", "http://x/", "http://y/pic.png"]
    assert [c.name for c in candidates] == ["photo.jpg", "openverse_2.jpg", "pic.png"]
    assert all(c.referrer == "https://openverse.org/" for c in candidates)
