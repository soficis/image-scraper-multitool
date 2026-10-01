"""Google collect loop and retry orchestration against a fake WebDriver."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from selenium.common.exceptions import (
    InvalidSessionIdException,
    JavascriptException,
    StaleElementReferenceException,
)

import image_scraper.adapters.chromedriver as chromedriver_module
import image_scraper.adapters.google as google_module
import image_scraper.adapters.google_collect as collect_module
from image_scraper.adapters.http_resilience import MAX_ATTEMPTS
from image_scraper.domain.models import DownloadBatchResult, TransformOptions
from image_scraper.errors import EngineError


class FakeImage:
    def __init__(self, src: str) -> None:
        self._src = src

    def get_attribute(self, name: str) -> str:
        return self._src if name == "src" else ""


class FakeCard:
    def __init__(self, key: str, click_error: Exception | None = None) -> None:
        self.key = key
        self.id = key
        self.click_error = click_error

    def get_attribute(self, name: str) -> str:
        return self.key if name == "data-docid" else ""

    def find_element(self, by: str, value: str) -> Any:
        if value == "img":
            return FakeImage(f"https://example.com/{self.key}.jpg")
        raise LookupError("no anchor")


class FakeDriver:
    def __init__(self, cards: list[FakeCard], page_source: str = "<html></html>") -> None:
        self.cards = cards
        self.page_source = page_source
        self.current_url = "https://www.google.com/search?tbm=isch&q=owls"

    def get(self, url: str) -> None:
        pass

    def execute_script(self, script: str, *args: Any) -> Any:
        if "click()" in script:
            for card in self.cards:
                if args and args[0] is card and card.click_error is not None:
                    raise card.click_error
        return None

    def find_element(self, by: str, value: str) -> Any:
        raise LookupError("no show-more")


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collect_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(google_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(collect_module, "dismiss_cookie_banner", lambda _d: None)
    monkeypatch.setattr(collect_module, "find_preview_images", lambda _d: [])


def _collect(driver: FakeDriver, monkeypatch: pytest.MonkeyPatch, limit: int = 2) -> list[str]:
    monkeypatch.setattr(collect_module, "find_cards", lambda _d: driver.cards)
    candidates = collect_module.collect_candidates(
        driver=driver,
        query="owls",
        limit=limit,
        min_resolution=(0, 0),
        max_resolution=(0, 0),
        max_missed=2,
        stop_event=None,
    )
    return [candidate.url for candidate in candidates]


def test_javascript_error_on_one_card_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver([FakeCard("a", JavascriptException("boom")), FakeCard("b"), FakeCard("c")])
    assert _collect(driver, monkeypatch) == [
        "https://example.com/b.jpg",
        "https://example.com/c.jpg",
    ]


def test_stale_card_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver([FakeCard("a", StaleElementReferenceException()), FakeCard("b")])
    assert _collect(driver, monkeypatch, limit=1) == ["https://example.com/b.jpg"]


def test_dead_session_raises_engine_error(monkeypatch: pytest.MonkeyPatch) -> None:
    driver = FakeDriver([FakeCard("a", InvalidSessionIdException("gone")), FakeCard("b")])
    with pytest.raises(EngineError) as info:
        _collect(driver, monkeypatch)
    assert info.value.operation == "google_collect"


def test_final_harvest_skipped_after_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    from threading import Event

    stop = Event()
    stop.set()
    driver = FakeDriver([], page_source='["https://example.com/triple.jpg",900,1200]')
    monkeypatch.setattr(collect_module, "find_cards", lambda _d: driver.cards)
    candidates = collect_module.collect_candidates(
        driver=driver,
        query="owls",
        limit=5,
        min_resolution=(0, 0),
        max_resolution=(0, 0),
        max_missed=2,
        stop_event=stop,
    )
    assert candidates == []


class _QuitDriver:
    def quit(self) -> None:
        pass


def _run_scrape_google(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, outcomes: list[Any], sleeps: list[float]
) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(google_module, "resolve_chromedriver_path", lambda _p: None)
    monkeypatch.setattr(google_module, "create_chrome_driver", lambda **_k: _QuitDriver())
    monkeypatch.setattr(google_module.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        google_module,
        "download_candidates",
        lambda *_a, **_k: DownloadBatchResult(saved=0, skipped=0, errors=[]),
    )

    def fake_collect(**_kwargs: Any) -> list[Any]:
        calls.append("collect")
        outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(google_module, "collect_candidates", fake_collect)
    google_module.scrape_google(
        query="owls",
        limit=1,
        destination=tmp_path,
        keep_filenames=False,
        transform=TransformOptions(),
        chromedriver_path=None,
        headless=True,
        min_resolution=(0, 0),
        max_resolution=(0, 0),
        max_missed=2,
    )
    return calls


def test_scrape_google_retries_stale_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sleeps: list[float] = []
    calls = _run_scrape_google(
        monkeypatch, tmp_path, [StaleElementReferenceException(), []], sleeps
    )
    assert len(calls) == 2
    assert len(sleeps) == 1


def test_scrape_google_no_sleep_after_final_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sleeps: list[float] = []
    with pytest.raises(EngineError):
        _run_scrape_google(monkeypatch, tmp_path, [StaleElementReferenceException()], sleeps)
    assert len(sleeps) == MAX_ATTEMPTS - 1


def test_scrape_google_non_stale_error_does_not_retry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []

    def record(*_a: Any, **_k: Any) -> list[Any]:
        calls.append("collect")
        raise JavascriptException("broken")

    monkeypatch.setattr(google_module, "resolve_chromedriver_path", lambda _p: None)
    monkeypatch.setattr(google_module, "create_chrome_driver", lambda **_k: _QuitDriver())
    monkeypatch.setattr(google_module, "collect_candidates", record)
    with pytest.raises(EngineError):
        google_module.scrape_google(
            query="owls",
            limit=1,
            destination=tmp_path,
            keep_filenames=False,
            transform=TransformOptions(),
            chromedriver_path=None,
            headless=True,
            min_resolution=(0, 0),
            max_resolution=(0, 0),
            max_missed=2,
        )
    assert calls == ["collect"]


class _CdpDriver:
    def __init__(self, agent: str, fail: bool = False) -> None:
        self.agent = agent
        self.fail = fail
        self.commands: list[tuple[str, dict[str, Any]]] = []

    def execute_cdp_cmd(self, command: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("no cdp")
        self.commands.append((command, params))
        return {"userAgent": self.agent} if command == "Browser.getVersion" else {}


def test_headless_user_agent_is_masked() -> None:
    driver = _CdpDriver("Mozilla/5.0 (X11) AppleWebKit/537.36 HeadlessChrome/140.0 Safari/537.36")
    chromedriver_module.mask_headless_user_agent(driver)
    assert driver.commands[-1] == (
        "Network.setUserAgentOverride",
        {"userAgent": "Mozilla/5.0 (X11) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"},
    )


def test_headed_user_agent_left_alone() -> None:
    driver = _CdpDriver("Mozilla/5.0 Chrome/140.0")
    chromedriver_module.mask_headless_user_agent(driver)
    assert [command for command, _ in driver.commands] == ["Browser.getVersion"]


def test_user_agent_mask_failure_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    chromedriver_module.mask_headless_user_agent(_CdpDriver("", fail=True))
    assert "could not mask headless user agent" in caplog.text
