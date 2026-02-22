"""Shared image download adapter used by all engines."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
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
from .image_processing import compress_image, decode_data_uri, maybe_convert_webp_to_jpg


@dataclass(frozen=True)
class DownloadOptions:
    destination: Path
    filename_prefix: str
    keep_filenames: bool
    timeout: float
    transform: TransformOptions


def _iter_chunks(response: requests.Response, chunk_size: int = 8192) -> Iterator[bytes]:
    for chunk in response.iter_content(chunk_size=chunk_size):
        if chunk:
            yield chunk


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
        for chunk in _iter_chunks(response):
            handle.write(chunk)


def _download_http_candidate(
    *,
    session: requests.Session,
    candidate: DownloadCandidate,
    options: DownloadOptions,
    index: int,
) -> tuple[Path, str]:
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    if candidate.referrer:
        headers["Referer"] = candidate.referrer

    candidate_urls: list[str] = [candidate.url]
    if candidate.fallback_url and candidate.fallback_url != candidate.url:
        candidate_urls.append(candidate.fallback_url)

    last_error: requests.RequestException | None = None

    for candidate_url in candidate_urls:
        try:
            with session.get(
                candidate_url,
                timeout=options.timeout,
                stream=True,
                headers=headers,
            ) as response:
                response.raise_for_status()
                suffix = best_extension(
                    original_name=sanitize_filename(candidate.name),
                    fallback_url=candidate_url,
                    content_type=response.headers.get("Content-Type", ""),
                )
                filename = _filename_for_candidate(
                    candidate=candidate,
                    index=index,
                    suffix=suffix,
                    options=options,
                )
                target_path = unique_path(options.destination / filename)
                _write_response(target_path, response)
                return target_path, candidate_url
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
