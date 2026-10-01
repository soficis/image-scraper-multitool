"""Openverse adapter: anonymous JSON search, pagination, URL extraction."""

from __future__ import annotations

from typing import Any

import pytest

import image_scraper.adapters.openverse as openverse_module
import image_scraper.adapters.stock_api as stock_api_module


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
        self.param_log: list[Any] = []

    def get(self, *args: Any, **kwargs: Any) -> FakeJsonResponse:
        self.calls += 1
        self.param_log.append(kwargs.get("params"))
        return FakeJsonResponse(self._pages[min(self.calls - 1, len(self._pages) - 1)])


def _openverse_result(url: str) -> dict[str, Any]:
    return {"url": url, "title": "t", "license": "by"}


def test_openverse_paginates_and_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    page1 = {"results": [_openverse_result(f"http://o/p{i}.jpg") for i in range(20)]}
    page2 = {
        "results": [_openverse_result("http://o/p0.jpg"), _openverse_result("http://o/new.jpg")]
    }
    session = FakeJsonSession([page1, page2])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    candidates = openverse_module._collect_candidates(query="cat", limit=25, timeout=5.0)
    assert len(candidates) == 21
    assert session.calls == 2
    assert all(c.referrer == "https://openverse.org/" for c in candidates)


def test_openverse_single_short_page_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {"results": [_openverse_result("http://o/a.jpg")]}
    session = FakeJsonSession([payload])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    candidates = openverse_module._collect_candidates(query="cat", limit=10, timeout=5.0)
    assert [c.url for c in candidates] == ["http://o/a.jpg"]
    assert session.calls == 1


def test_openverse_extract_falls_back_to_thumbnail() -> None:
    assert openverse_module._extract_url({"thumbnail": "http://o/t.jpg"}) == "http://o/t.jpg"
    assert openverse_module._extract_url({"url": "http://o/u.jpg"}) == "http://o/u.jpg"
    assert openverse_module._extract_url({}) == ""
    assert openverse_module._extract_url(None) == ""
    assert openverse_module._extract_url([1, 2]) == ""


def test_openverse_uses_anonymous_tier_params(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeJsonSession([{"results": []}])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    openverse_module._collect_candidates(query="cat", limit=5, timeout=5.0)
    params = session.param_log[0]
    assert params["page_size"] == "20"
    assert params["q"] == "cat"


def test_cli_accepts_openverse() -> None:
    from image_scraper.cli.main import _build_options, build_parser

    parser = build_parser()
    options = _build_options(parser.parse_args(["cats", "--engine", "openverse"]))
    assert list(options.engines) == ["openverse"]


def test_validate_accepts_openverse() -> None:
    from pathlib import Path

    from image_scraper.domain.models import ScrapeOptions

    options = ScrapeOptions(query="cats", engines=["openverse"], output_dir=Path("downloads"))
    options.validate()


def test_openverse_does_not_send_fake_per_page(monkeypatch: pytest.MonkeyPatch) -> None:
    session = FakeJsonSession([{"results": []}])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    openverse_module._collect_candidates(query="cat", limit=5, timeout=5.0)
    assert "per_page" not in session.param_log[0]


def test_openverse_never_requests_past_anonymous_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    counter = iter(range(10_000))
    full_page = lambda: {  # noqa: E731
        "results": [_openverse_result(f"http://o/{next(counter)}.jpg") for _ in range(20)]
    }
    session = FakeJsonSession([full_page() for _ in range(20)])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    monkeypatch.setattr(stock_api_module.HostThrottler, "wait", lambda self, url: None)
    candidates = openverse_module._collect_candidates(query="cat", limit=500, timeout=5.0)
    assert len(candidates) == openverse_module.ANONYMOUS_MAX_RESULTS
    assert max(int(params["page"]) for params in session.param_log) == 12


class _FailingLaterPageSession(FakeJsonSession):
    def get(self, *args: Any, **kwargs: Any) -> FakeJsonResponse:
        if self.calls >= 1:
            self.calls += 1
            raise stock_api_module.requests.HTTPError("401 Client Error")
        return super().get(*args, **kwargs)


def test_later_page_failure_keeps_collected_urls(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    page1 = {"results": [_openverse_result(f"http://o/p{i}.jpg") for i in range(20)]}
    session = _FailingLaterPageSession([page1])
    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: session)
    candidates = openverse_module._collect_candidates(query="cat", limit=40, timeout=5.0)
    assert len(candidates) == 20
    assert "keeping 20 collected URLs" in caplog.text


def test_first_page_failure_still_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from image_scraper.errors import EngineError

    class _AlwaysFail(FakeJsonSession):
        def get(self, *args: Any, **kwargs: Any) -> FakeJsonResponse:
            raise stock_api_module.requests.ConnectionError("down")

    monkeypatch.setattr(stock_api_module.requests, "Session", lambda: _AlwaysFail([]))
    with pytest.raises(EngineError):
        openverse_module._collect_candidates(query="cat", limit=5, timeout=5.0)


def test_attribution_csv_rows_and_formula_guard(tmp_path: Any) -> None:
    import csv

    from image_scraper.domain.models import DownloadCandidate

    result = {
        "url": "http://o/a.jpg",
        "title": '=HYPERLINK("http://evil")',
        "creator": "Ada",
        "license": "by",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "foreign_landing_url": "https://flickr.com/p/1",
        "attribution": '"a" by Ada is licensed under CC BY 4.0.',
    }
    metadata = {"http://o/a.jpg": openverse_module._attribution_row(result)}
    write = openverse_module._attribution_writer(tmp_path, metadata)
    write(DownloadCandidate(url="http://o/a.jpg"), tmp_path / "openverse_0001.jpg")
    write(DownloadCandidate(url="http://o/unknown.jpg"), tmp_path / "openverse_0002.jpg")

    with (tmp_path / openverse_module.ATTRIBUTION_FILENAME).open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["file"] for row in rows] == ["openverse_0001.jpg", "openverse_0002.jpg"]
    assert rows[0]["creator"] == "Ada"
    assert rows[0]["title"].startswith("'=")
    assert rows[0]["source_page"] == "https://flickr.com/p/1"
    assert rows[1]["license"] == ""


def test_scrape_openverse_reports_cap_and_wires_attribution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from image_scraper.domain.models import DownloadBatchResult, TransformOptions

    seen_hooks: list[Any] = []

    def fake_download(candidates: Any, options: Any, **kwargs: Any) -> DownloadBatchResult:
        seen_hooks.append(kwargs.get("on_saved"))
        return DownloadBatchResult(saved=0, skipped=0, errors=[])

    monkeypatch.setattr(openverse_module, "_collect_candidates", lambda **_k: [])
    monkeypatch.setattr(openverse_module, "download_candidates", fake_download)
    result = openverse_module.scrape_openverse(
        query="cat",
        limit=300,
        destination=tmp_path,
        keep_filenames=False,
        transform=TransformOptions(),
        timeout=5.0,
    )
    assert seen_hooks and callable(seen_hooks[0])
    assert any("capped at 240" in error for error in result.errors)


def test_api_timeout_is_separate_from_bing_timeout() -> None:
    from image_scraper.cli.main import _build_options, build_parser

    options = _build_options(
        build_parser().parse_args(["cats", "--engine", "openverse", "--api-timeout", "42"])
    )
    assert options.api_timeout == 42.0
    assert options.bing_timeout == 15.0


def test_api_timeout_must_be_positive() -> None:
    from pathlib import Path

    from image_scraper.domain.models import ScrapeOptions
    from image_scraper.errors import ConfigurationError

    with pytest.raises(ConfigurationError):
        ScrapeOptions(
            query="cats", engines=["openverse"], output_dir=Path("d"), api_timeout=0
        ).validate()
