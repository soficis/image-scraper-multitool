"""Per-engine isolation: one failing engine must not abort the rest."""

from __future__ import annotations

from pathlib import Path

import pytest

import image_scraper.app.scrape as scrape_module
from image_scraper.domain.models import ScrapeOptions, ScrapeResult
from image_scraper.errors import EngineError


def _options(tmp_path: Path, engines: list[str]) -> ScrapeOptions:
    return ScrapeOptions(
        query="kittens",
        engines=engines,  # type: ignore[arg-type]
        limit=3,
        output_dir=tmp_path / "out",
    )


def test_failing_engine_yields_error_result_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(**kwargs: object) -> ScrapeResult:
        raise EngineError("bing_collect", "boom")

    monkeypatch.setattr(scrape_module, "scrape_bing", boom)
    results = scrape_module.scrape_images(_options(tmp_path, ["bing"]))
    assert len(results) == 1
    assert results[0].engine == "bing"
    assert results[0].saved == 0
    assert len(results[0].errors) == 1
    assert "boom" in results[0].errors[0]


def test_second_engine_still_runs_after_first_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def boom(**kwargs: object) -> ScrapeResult:
        calls.append("bing")
        raise EngineError("bing_collect", "boom")

    def ok(**kwargs: object) -> ScrapeResult:
        calls.append("google")
        destination = tmp_path / "out" / "google" / "kittens"
        return ScrapeResult(
            engine="google",
            requested=3,
            saved=1,
            skipped=0,
            errors=[],
            destination=destination,
        )

    monkeypatch.setattr(scrape_module, "scrape_bing", boom)
    monkeypatch.setattr(scrape_module, "scrape_google", ok)
    results = scrape_module.scrape_images(_options(tmp_path, ["bing", "google"]))
    assert calls == ["bing", "google"]
    assert len(results) == 2
    assert results[0].errors and results[0].saved == 0
    assert results[1].saved == 1 and not results[1].errors


def test_unexpected_exception_is_contained(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**kwargs: object) -> ScrapeResult:
        raise RuntimeError("weird")

    monkeypatch.setattr(scrape_module, "scrape_bing", boom)
    results = scrape_module.scrape_images(_options(tmp_path, ["bing"]))
    assert len(results) == 1
    assert "RuntimeError" in results[0].errors[0]
