"""Downloader hardening: retry, fail-fast, size guard, throttling."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import requests

from image_scraper.adapters.downloader import (
    DownloadOptions,
    HostThrottler,
    download_candidates,
    retry_delay,
)
from image_scraper.domain.models import DownloadCandidate, TransformOptions


class FakeResponse:
    def __init__(
        self,
        status: int,
        *,
        payload: bytes = b"fake-image-bytes",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status
        self._payload = payload
        self.headers = {"Content-Type": "image/jpeg"}
        if headers:
            self.headers.update(headers)

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} error")
            error.response = self
            raise error

    def iter_content(self, chunk_size: int = 8192) -> Iterator[bytes]:
        yield self._payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses
        self.headers: dict[str, str] = {}
        self.calls = 0

    def get(self, *args: Any, **kwargs: Any) -> FakeResponse:
        self.calls += 1
        return self._responses[min(self.calls - 1, len(self._responses) - 1)]

    def close(self) -> None:
        pass


def _options(tmp_path: Path) -> DownloadOptions:
    return DownloadOptions(
        destination=tmp_path / "dl",
        filename_prefix="test",
        keep_filenames=False,
        timeout=5.0,
        transform=TransformOptions(),
    )


def _candidate() -> DownloadCandidate:
    return DownloadCandidate(url="http://example.com/pic.jpg", name="pic.jpg")


def test_retry_on_502_then_success(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(502), FakeResponse(200)])
    batch = download_candidates([_candidate()], _options(tmp_path), session=session)
    assert batch.saved == 1
    assert session.calls == 2


def test_no_retry_on_404(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(404)])
    batch = download_candidates([_candidate()], _options(tmp_path), session=session)
    assert batch.saved == 0
    assert batch.skipped == 1
    assert session.calls == 1


def test_unsupported_scheme_skips_without_network(tmp_path: Path) -> None:
    session = FakeSession([FakeResponse(200)])
    candidate = DownloadCandidate(url="ftp://example.com/pic.jpg", name="pic.jpg")
    batch = download_candidates([candidate], _options(tmp_path), session=session)
    assert batch.saved == 0
    assert batch.skipped == 1
    assert session.calls == 0


def test_oversize_declared_length_skips_without_retry(tmp_path: Path) -> None:
    session = FakeSession(
        [FakeResponse(200, payload=b"x", headers={"Content-Length": str(200 * 1024 * 1024)})]
    )
    batch = download_candidates([_candidate()], _options(tmp_path), session=session)
    assert batch.saved == 0
    assert session.calls == 1


def test_retry_after_header_is_honored() -> None:
    response = FakeResponse(429, headers={"Retry-After": "7"})
    delay = retry_delay(attempt=0, response=response)
    assert 7.0 <= delay <= 7.5


def test_backoff_grows_with_attempt() -> None:
    first = retry_delay(attempt=0, response=None)
    third = retry_delay(attempt=2, response=None)
    assert third > first


def test_throttler_spaces_same_host_requests() -> None:
    import time

    throttler = HostThrottler(min_interval=0.2)
    throttler.wait("http://example.com/a.jpg")
    start = time.monotonic()
    throttler.wait("http://example.com/b.jpg")
    assert time.monotonic() - start >= 0.15


def test_on_saved_hook_failure_keeps_file(tmp_path: Path) -> None:
    import base64

    from image_scraper.adapters.downloader import DownloadOptions, download_candidates
    from image_scraper.domain.models import DownloadCandidate, TransformOptions

    payload = base64.b64encode(b"\xff\xd8\xff\xe0fakejpeg").decode()
    candidate = DownloadCandidate(url=f"data:image/jpeg;base64,{payload}", name="a.jpg")

    def broken_hook(_candidate: DownloadCandidate, _path: Path) -> None:
        raise OSError("disk full")

    result = download_candidates(
        [candidate],
        DownloadOptions(
            destination=tmp_path,
            filename_prefix="t",
            keep_filenames=False,
            timeout=5.0,
            transform=TransformOptions(),
        ),
        on_saved=broken_hook,
    )
    assert result.saved == 1
    assert result.skipped == 0
    assert any("post-save hook failed" in error for error in result.errors)
    assert any(path.suffix for path in tmp_path.iterdir() if path.name.startswith("t_"))


def test_html_response_falls_back_to_fallback_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # First URL returns HTML (e.g. login/block wall); fallback URL returns JPEG
    responses = [
        FakeResponse(
            200, payload=b"<html>Login required</html>", headers={"Content-Type": "text/html"}
        ),
        FakeResponse(200, payload=b"jpeg-image-bytes", headers={"Content-Type": "image/jpeg"}),
    ]
    session = FakeSession(responses)
    monkeypatch.setattr("image_scraper.adapters.downloader.requests.Session", lambda: session)

    candidate = DownloadCandidate(
        url="https://example.com/blocked_page",
        name="test.jpg",
        fallback_url="https://example.com/valid_thumbnail.jpg",
    )
    result = download_candidates(
        [candidate],
        DownloadOptions(
            destination=tmp_path,
            filename_prefix="t",
            keep_filenames=False,
            timeout=5.0,
            transform=TransformOptions(),
        ),
    )
    assert result.saved == 1
    assert result.skipped == 0
    saved_file = next(tmp_path.iterdir())
    assert saved_file.read_bytes() == b"jpeg-image-bytes"
