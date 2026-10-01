"""Unit tests for cross-platform folder opener."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from image_scraper.ui.platform_open import open_in_file_manager


def test_open_in_file_manager_windows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        "image_scraper.ui.platform_open.os.startfile",
        lambda p: called.append(str(p)),
        raising=False,
    )

    folder = tmp_path / "win_folder"
    folder.mkdir()
    assert open_in_file_manager(folder) is True
    assert called == [str(folder)]


def test_open_in_file_manager_macos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    mock_run = MagicMock()
    monkeypatch.setattr("image_scraper.ui.platform_open.subprocess.run", mock_run)

    folder = tmp_path / "mac_folder"
    folder.mkdir()
    assert open_in_file_manager(folder) is True
    mock_run.assert_called_once_with(["open", str(folder)], check=True)


def test_open_in_file_manager_linux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    mock_run = MagicMock()
    monkeypatch.setattr("image_scraper.ui.platform_open.subprocess.run", mock_run)

    folder = tmp_path / "linux_folder"
    folder.mkdir()
    assert open_in_file_manager(folder) is True
    mock_run.assert_called_once_with(["xdg-open", str(folder)], check=True)


def test_open_in_file_manager_nonexistent(tmp_path: Path) -> None:
    folder = tmp_path / "does_not_exist"
    assert open_in_file_manager(folder) is False
