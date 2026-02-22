"""Filesystem adapter helpers."""

from __future__ import annotations

from pathlib import Path

from image_scraper.constants import IMAGE_MANIFEST_FILENAME
from image_scraper.errors import DownloadError


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def unique_path(base_path: Path) -> Path:
    if not base_path.exists():
        return base_path

    counter = 1
    while True:
        candidate = base_path.with_name(f"{base_path.stem}_{counter}{base_path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def manifest_path(destination: Path) -> Path:
    return destination / IMAGE_MANIFEST_FILENAME


def load_manifest(destination: Path) -> set[str]:
    path = manifest_path(destination)
    if not path.exists():
        return set()
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise DownloadError(
            "load_manifest",
            "failed to read URL manifest",
            context={"path": str(path), "error": str(error)},
        ) from error
    return {line.strip() for line in content.splitlines() if line.strip()}


def append_manifest(destination: Path, url: str) -> None:
    path = manifest_path(destination)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{url}\n")
    except OSError as error:
        raise DownloadError(
            "append_manifest",
            "failed to write URL manifest",
            context={"path": str(path), "url": url, "error": str(error)},
        ) from error
