"""Tests for user settings persistence functions."""

from __future__ import annotations

from pathlib import Path

from image_scraper.ui.settings import get_settings_path, load_settings, save_settings


def test_settings_round_trip(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    data = {"bing": False, "num_images": 42, "output_dir": "/custom/path", "dark_mode": True}
    save_settings(data, path=settings_file)
    loaded = load_settings(path=settings_file)
    assert loaded == data


def test_corrupt_json_returns_empty_dict(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{ this is not valid json }", encoding="utf-8")
    loaded = load_settings(path=settings_file)
    assert loaded == {}


def test_non_dict_json_returns_empty_dict(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("[1, 2, 3]", encoding="utf-8")
    loaded = load_settings(path=settings_file)
    assert loaded == {}


def test_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    settings_file = tmp_path / "does_not_exist.json"
    assert load_settings(path=settings_file) == {}


def test_get_settings_path_returns_path() -> None:
    path = get_settings_path()
    assert isinstance(path, Path)
    assert path.name == "settings.json"
