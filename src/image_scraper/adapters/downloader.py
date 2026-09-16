"""Shared image download adapter used by all engines."""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

import requests

from image_scraper.constants import DEFAULT_USER_AGENT
from image_scraper.domain.image_types import best_extension
from image_scraper.domain.models import DownloadBatchResult, DownloadCandidate, TransformOptions
from image_scraper.domain.naming import sanitize_filename
from image_scraper.errors import DownloadError

from .filesystem import append_manifest, ensure_directory, load_manifest, unique_path
from .http_resilience import (
    MAX_ATTEMPTS,
    MAX_DOWNLOAD_BYTES,
    RETRYABLE_STATUS_CODES,
    HostThrottler,
    iter_capped_chunks,
    retry_delay,
)
from .image_processing import compress_image, decode_data_uri, maybe_convert_webp_to_jpg


@dataclass(frozen=True)
class DownloadOptions:
    destination: Path
    filename_prefix: str
    keep_filenames: bool
    timeout: float
    transform: TransformOptions


def _filename_for_candidate(
    *, candidate: DownloadCandidate, index: int, suffix: str, options: DownloadOptions
) -> str:
    original_name = sanitize_filename(candidate.name) if candidate.name else ""
    if options.keep_filenames and original_name:
        if Path(original_name).suffix:
            return original_name
        return f"{original_name}{suffix}"
    return f"{options.filename_prefix}_{index:04d}{suffix}"


def _write_bytes(path: Path, payload: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(payload)


def _write_response(path: Path, response: requests.Response) -> None:
    with path.open("wb") as handle:
        for chunk in iter_capped_chunks(response):
            handle.write(chunk)


def _download_single_url(
    *,
    session: requests.Session,
    candidate_url: str,
    headers: dict[str, str],
    candidate: DownloadCandidate,
    options: DownloadOptions,
    index: int,
    throttler: HostThrottler,
    stop_event: Event | None,
) -> tuple[Path, str]:
    last_error: Exception | None = None
    response: requests.Response | None = None

    for attempt in range(MAX_ATTEMPTS):
        if stop_event and stop_event.is_set():
            break
        throttler.wait(candidate_url)
        try:
            with session.get(
                candidate_url,
                timeout=options.timeout,
                stream=True,
                headers=headers,
            ) as live_response:
                response = live_response
                live_response.raise_for_status()
                declared = live_response.headers.get("Content-Length", "").strip()
                if declared:
                    try:
                        if int(declared) > MAX_DOWNLOAD_BYTES:
                            raise DownloadError(
                                "download_too_large",
                                "declared content length exceeds size limit",
                                context={"url": candidate_url, "bytes": declared},
                            )
                    except ValueError:
                        pass
                suffix = best_extension(
                    original_name=sanitize_filename(candidate.name),
                    fallback_url=candidate_url,
                    content_type=live_response.headers.get("Content-Type", ""),
                )
                filename = _filename_for_candidate(
                    candidate=candidate,
                    index=index,
                    suffix=suffix,
                    options=options,
                )
                target_path = unique_path(options.destination / filename)
                _write_response(target_path, live_response)
                return target_path, candidate_url
        except requests.HTTPError as error:
            last_error = error
            if error.response is not None and error.response.status_code not in (
                RETRYABLE_STATUS_CODES
            ):
                break
            response = error.response
        except DownloadError:
            raise
        # Transient transport failures are retried; other request errors fail fast.
        except (requests.ConnectionError, requests.Timeout) as error:
            last_error = error
        except requests.RequestException as error:
            last_error = error
            break
        if attempt + 1 < MAX_ATTEMPTS and not (stop_event and stop_event.is_set()):
            time.sleep(retry_delay(attempt=attempt, response=response))
            response = None

    if last_error is None:
        raise DownloadError(
            "download_http_candidate",
            "download stopped before any attempt completed",
            context={"url": candidate_url},
        )
    raise last_error


def _download_http_candidate(
    *,
    session: requests.Session,
    candidate: DownloadCandidate,
    options: DownloadOptions,
    index: int,
    throttler: HostThrottler,
    stop_event: Event | None = None,
) -> tuple[Path, str]:
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if candidate.referrer:
        headers["Referer"] = candidate.referrer

    candidate_urls: list[str] = [candidate.url]
    if candidate.fallback_url and candidate.fallback_url != candidate.url:
        candidate_urls.append(candidate.fallback_url)

    last_error: Exception | None = None

    for candidate_url in candidate_urls:
        try:
            return _download_single_url(
                session=session,
                candidate_url=candidate_url,
                headers=headers,
                candidate=candidate,
                options=options,
                index=index,
                throttler=throttler,
                stop_event=stop_event,
            )
        except DownloadError as error:
            last_error = error
        except requests.RequestException as error:
            last_error = error

    if last_error is None:
        raise DownloadError(
            "download_http_candidate",
            "no candidate URLs available for HTTP download",
            context={"url": candidate.url},
        )

    raise last_error


def download_candidates(
    candidates: Iterable[DownloadCandidate],
    options: DownloadOptions,
    *,
    stop_event: Event | None = None,
    session: requests.Session | None = None,
) -> DownloadBatchResult:
    ensure_directory(options.destination)

    seen_urls = load_manifest(options.destination)
    saved = 0
    skipped = 0
    errors: list[str] = []

    own_session = session is None
    active_session = session or requests.Session()
    active_session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    throttler = HostThrottler()

    try:
        for index, candidate in enumerate(candidates, start=1):
            if stop_event and stop_event.is_set():
                break

            source_url = candidate.url
            manifest_key = source_url

            if source_url in seen_urls:
                skipped += 1
                continue

            target_path: Path | None = None

            try:
                if source_url.startswith("data:image"):
                    payload, hinted_extension, manifest_key = decode_data_uri(source_url)
                    suffix = hinted_extension
                    filename = _filename_for_candidate(
                        candidate=DownloadCandidate(source_url, candidate.name or "data-image"),
                        index=index,
                        suffix=suffix,
                        options=options,
                    )
                    target_path = unique_path(options.destination / filename)
                    _write_bytes(target_path, payload)
                else:
                    target_path, _resolved_url = _download_http_candidate(
                        session=active_session,
                        candidate=candidate,
                        options=options,
                        index=index,
                        throttler=throttler,
                        stop_event=stop_event,
                    )

                final_path = target_path
                if final_path is None:
                    raise DownloadError(
                        "download", "target path was not initialized", context={"url": source_url}
                    )

                if options.transform.convert_webp:
                    final_path = maybe_convert_webp_to_jpg(final_path)

                if (
                    options.transform.compression_quality > 0
                    or options.transform.resize_width > 0
                    or options.transform.resize_height > 0
                ):
                    compress_image(
                        final_path,
                        options.transform.compression_quality,
                        options.transform.resize_width,
                        options.transform.resize_height,
                    )

                append_manifest(options.destination, manifest_key)
                seen_urls.add(manifest_key)
                saved += 1

            except (requests.RequestException, DownloadError, OSError) as error:
                skipped += 1
                errors.append(f"{source_url} ({error})")
                if target_path and target_path.exists():
                    try:
                        target_path.unlink()
                    except OSError:
                        pass
    finally:
        if own_session:
            active_session.close()

    return DownloadBatchResult(saved=saved, skipped=skipped, errors=errors)
