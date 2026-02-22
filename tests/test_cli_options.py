import pytest

from image_scraper.cli.main import _build_options, build_parser
from image_scraper.domain.models import ScrapeOptions
from image_scraper.errors import ConfigurationError


def parse_options(argv: list[str]) -> ScrapeOptions:
    parser = build_parser()
    return _build_options(parser.parse_args(argv))


def test_default_engines_are_bing_and_google() -> None:
    options = parse_options(["kittens"])
    assert list(options.engines) == ["bing", "google"]


def test_custom_engine_mode_builds_custom_only() -> None:
    options = parse_options(["https://example.com", "--engine", "custom"])
    assert list(options.engines) == ["custom"]


def test_google_options_accept_explicit_resolutions() -> None:
    options = parse_options(
        [
            "mountains",
            "--engine",
            "google",
            "--google-min-resolution",
            "800",
            "600",
            "--google-max-resolution",
            "1920",
            "1080",
        ]
    )
    assert options.google.min_resolution == (800, 600)
    assert options.google.max_resolution == (1920, 1080)


def test_validation_rejects_non_positive_limit() -> None:
    options = parse_options(["cats", "--num-images", "0"])
    with pytest.raises(ConfigurationError):
        options.validate()
