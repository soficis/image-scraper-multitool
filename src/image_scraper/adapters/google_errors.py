"""Selenium error classification shared by the Google adapter modules."""

from __future__ import annotations


def error_summary(error: Exception) -> str:
    first_line = str(error).splitlines()[0].strip() if str(error) else ""
    if not first_line:
        return error.__class__.__name__
    return f"{error.__class__.__name__}: {first_line}"


def selenium_exceptions() -> tuple[tuple[type[Exception], ...], tuple[type[Exception], ...]]:
    """Return (stale, session_dead) exception types.

    Every Selenium error subclasses WebDriverException, so only errors that
    mean the browser session itself is gone count as fatal; anything else on
    a single card is skipped. Selenium is imported lazily because the driver
    factory has already raised DependencyError when it is missing.
    """
    from selenium.common.exceptions import (
        InvalidSessionIdException,
        NoSuchWindowException,
        StaleElementReferenceException,
    )

    return (StaleElementReferenceException,), (InvalidSessionIdException, NoSuchWindowException)
