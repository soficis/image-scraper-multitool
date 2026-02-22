"""Domain layer exports."""

from .image_types import best_extension
from .models import (
    BatchConversionResult,
    CustomPageOptions,
    DownloadBatchResult,
    DownloadCandidate,
    GoogleOptions,
    ScrapeOptions,
    ScrapeResult,
    TransformOptions,
)
from .naming import sanitize_filename, slugify

__all__ = [
    "BatchConversionResult",
    "CustomPageOptions",
    "DownloadBatchResult",
    "DownloadCandidate",
    "GoogleOptions",
    "ScrapeOptions",
    "ScrapeResult",
    "TransformOptions",
    "best_extension",
    "sanitize_filename",
    "slugify",
]
