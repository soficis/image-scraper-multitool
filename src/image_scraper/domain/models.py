"""Typed models used across app, adapters, and UI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Literal

from image_scraper.errors import ConfigurationError

EngineName = Literal["bing", "google", "custom"]


@dataclass(frozen=True)
class TransformOptions:
    convert_webp: bool = False
    compression_quality: int = 0
    resize_width: int = 0
    resize_height: int = 0

    def validate(self) -> None:
        if not 0 <= self.compression_quality <= 100:
            raise ConfigurationError(
                "validate_transform",
                "compression_quality must be between 0 and 100",
                context={"compression_quality": self.compression_quality},
            )
        if self.resize_width < 0 or self.resize_height < 0:
            raise ConfigurationError(
                "validate_transform",
                "resize dimensions must be zero or positive",
                context={"resize_width": self.resize_width, "resize_height": self.resize_height},
            )


@dataclass(frozen=True)
class GoogleOptions:
    chromedriver_path: Path | None = None
    headless: bool = True
    min_resolution: tuple[int, int] = (0, 0)
    max_resolution: tuple[int, int] = (0, 0)
    max_missed: int = 10

    def validate(self) -> None:
        min_width, min_height = self.min_resolution
        max_width, max_height = self.max_resolution

        if min_width < 0 or min_height < 0:
            raise ConfigurationError(
                "validate_google",
                "minimum resolution values must be zero or positive",
                context={"min_resolution": self.min_resolution},
            )
        if max_width < 0 or max_height < 0:
            raise ConfigurationError(
                "validate_google",
                "maximum resolution values must be zero or positive",
                context={"max_resolution": self.max_resolution},
            )
        if max_width and min_width and max_width < min_width:
            raise ConfigurationError(
                "validate_google",
                "max width cannot be smaller than min width",
                context={"min_width": min_width, "max_width": max_width},
            )
        if max_height and min_height and max_height < min_height:
            raise ConfigurationError(
                "validate_google",
                "max height cannot be smaller than min height",
                context={"min_height": min_height, "max_height": max_height},
            )
        if self.max_missed <= 0:
            raise ConfigurationError(
                "validate_google",
                "max_missed must be positive",
                context={"max_missed": self.max_missed},
            )


@dataclass(frozen=True)
class CustomPageOptions:
    recursion_depth: int = 0

    def validate(self) -> None:
        if self.recursion_depth < 0:
            raise ConfigurationError(
                "validate_custom_page",
                "recursion_depth must be zero or positive",
                context={"recursion_depth": self.recursion_depth},
            )


@dataclass(frozen=True)
class ScrapeOptions:
    query: str
    engines: Sequence[EngineName]
    limit: int = 10
    output_dir: Path = Path("downloads")
    keep_filenames: bool = False
    transform: TransformOptions = field(default_factory=TransformOptions)
    bing_timeout: float = 15.0
    google: GoogleOptions = field(default_factory=GoogleOptions)
    custom_page: CustomPageOptions = field(default_factory=CustomPageOptions)

    def validate(self) -> None:
        query = self.query.strip()
        if not query:
            raise ConfigurationError("validate_scrape", "query cannot be empty")
        if self.limit <= 0:
            raise ConfigurationError(
                "validate_scrape",
                "limit must be positive",
                context={"limit": self.limit},
            )
        if self.bing_timeout <= 0:
            raise ConfigurationError(
                "validate_scrape",
                "bing_timeout must be positive",
                context={"bing_timeout": self.bing_timeout},
            )
        if not self.engines:
            raise ConfigurationError("validate_scrape", "at least one engine must be selected")

        unknown = sorted(set(self.engines) - {"bing", "google", "custom"})
        if unknown:
            raise ConfigurationError(
                "validate_scrape",
                "unsupported engines requested",
                context={"engines": unknown},
            )

        self.transform.validate()
        self.google.validate()
        self.custom_page.validate()


@dataclass(frozen=True)
class DownloadCandidate:
    url: str
    name: str = ""
    referrer: str = ""
    fallback_url: str = ""


@dataclass(frozen=True)
class DownloadBatchResult:
    saved: int
    skipped: int
    errors: list[str]


@dataclass(frozen=True)
class ScrapeResult:
    engine: EngineName
    requested: int
    saved: int
    skipped: int
    errors: list[str]
    destination: Path


@dataclass(frozen=True)
class BatchConversionResult:
    total_files: int
    converted: int
    skipped: int
    errors: list[str]
    output_dir: Path


@dataclass(frozen=True)
class RuntimeControl:
    stop_event: Event | None = None
