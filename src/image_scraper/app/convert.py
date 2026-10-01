"""Application use-case: batch image conversion and compression."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event

from image_scraper.adapters.image_converter import ConversionOptions, convert_images
from image_scraper.domain.models import BatchConversionResult


def convert_image_batch(
    *,
    input_paths: list[Path],
    options: ConversionOptions,
    stop_event: Event | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> BatchConversionResult:
    return convert_images(
        input_paths=input_paths,
        options=options,
        stop_event=stop_event,
        progress_callback=progress_callback,
    )


def format_bytes(count: int) -> str:
    size = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def summarize_conversion(result: BatchConversionResult) -> str:
    summary = (
        f"Convert: {result.converted}/{result.total_files} written, "
        f"{result.skipped} skipped"
        + (f" ({result.failed} failed)" if result.failed else "")
        + f" -> {result.output_dir}"
    )
    if result.converted and result.bytes_in:
        change = (result.bytes_out - result.bytes_in) / result.bytes_in * 100
        summary += (
            f" | {format_bytes(result.bytes_in)} -> {format_bytes(result.bytes_out)} "
            f"({change:+.0f}%)"
        )
    return summary
