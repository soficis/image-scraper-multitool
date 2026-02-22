"""Application use-case: batch HEIC conversion."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from image_scraper.adapters.heic_converter import convert_heic_files
from image_scraper.domain.models import BatchConversionResult


def convert_heic_batch(
    *,
    input_paths: list[Path],
    output_dir: Path,
    output_format: str,
    quality: int,
    stop_event: Event | None = None,
) -> BatchConversionResult:
    return convert_heic_files(
        input_paths=input_paths,
        output_dir=output_dir,
        output_format=output_format,
        quality=quality,
        stop_event=stop_event,
    )
