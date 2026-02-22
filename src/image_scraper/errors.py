"""Custom error model for the scraper."""

from __future__ import annotations

from collections.abc import Mapping


class ImageScraperError(RuntimeError):
    """Base error with operation context."""

    def __init__(
        self,
        operation: str,
        message: str,
        *,
        context: Mapping[str, object] | None = None,
    ) -> None:
        self.operation = operation
        self.message = message
        self.context = dict(context or {})
        super().__init__(self.__str__())

    def __str__(self) -> str:
        if not self.context:
            return f"{self.operation}: {self.message}"
        context_text = ", ".join(f"{key}={value!r}" for key, value in sorted(self.context.items()))
        return f"{self.operation}: {self.message} ({context_text})"


class ConfigurationError(ImageScraperError):
    """Invalid user configuration."""


class DependencyError(ImageScraperError):
    """Missing optional dependency."""


class EngineError(ImageScraperError):
    """Scraper engine failure."""


class DownloadError(ImageScraperError):
    """Image download/write failure."""
