"""`convert` subcommand: dispatch, argument validation, exit codes, real runs."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from PIL import Image

import image_scraper.cli.main as cli_main
from image_scraper.adapters.image_converter import supported_input_extensions
from image_scraper.cli.main import main


def _photo(path: Path, size: tuple[int, int] = (64, 32)) -> Path:
    Image.linear_gradient("L").resize(size).convert("RGB").save(path)
    return path


def test_convert_writes_requested_format(tmp_path: Path) -> None:
    source = _photo(tmp_path / "a.png")
    assert main(["convert", str(source), "--to", "webp"]) == 0
    with Image.open(tmp_path / "a.webp") as out:
        assert out.format == "WEBP"


@pytest.mark.parametrize(("alias", "suffix"), [("jpg", ".jpg"), ("tif", ".tiff"), ("JPEG", ".jpg")])
def test_format_aliases(tmp_path: Path, alias: str, suffix: str) -> None:
    source = _photo(tmp_path / "a.png")
    assert main(["convert", str(source), "--to", alias]) == 0
    assert (tmp_path / f"a{suffix}").exists()


def test_default_keeps_format_and_compresses_beside_original(tmp_path: Path) -> None:
    source = tmp_path / "shot.jpg"
    Image.effect_noise((256, 256), 80).convert("RGB").save(source, quality=100)
    assert main(["convert", str(source), "--quality", "40"]) == 0
    assert (tmp_path / "shot_compressed.jpg").stat().st_size < source.stat().st_size


def test_options_are_passed_through(tmp_path: Path) -> None:
    folder = tmp_path / "in"
    (folder / "sub").mkdir(parents=True)
    _photo(folder / "sub" / "big.png", size=(400, 200))
    out = tmp_path / "out"
    code = main(
        ["convert", str(folder), "--to", "png", "--max-width", "100", "--output-dir", str(out)]
    )
    assert code == 0
    with Image.open(out / "sub" / "big.png") as resized:
        assert resized.size == (100, 50)


def test_failed_file_gives_exit_1_but_others_are_written(tmp_path: Path) -> None:
    (tmp_path / "broken.jpg").write_bytes(b"not an image")
    _photo(tmp_path / "good.png")
    assert main(["convert", str(tmp_path), "--to", "webp"]) == 1
    assert (tmp_path / "good.webp").exists()


def test_not_smaller_skip_is_not_a_failure(tmp_path: Path) -> None:
    source = tmp_path / "noisy.jpg"
    Image.effect_noise((128, 128), 120).convert("RGB").save(source, quality=10)
    assert main(["convert", str(source), "--to", "png", "--only-smaller"]) == 0
    assert not (tmp_path / "noisy.png").exists()


def test_no_images_found_is_exit_1(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("x")
    assert main(["convert", str(tmp_path)]) == 1


@pytest.mark.parametrize(
    "argv",
    [
        ["convert"],
        ["convert", "does-not-exist"],
        ["convert", ".", "--to", "psd"],
        ["convert", ".", "--to", "png", "--lossless"],
    ],
)
def test_invalid_arguments_exit_2(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(argv)
    assert info.value.code == 2


def test_invalid_quality_is_exit_1(tmp_path: Path) -> None:
    source = _photo(tmp_path / "a.png")
    assert main(["convert", str(source), "--to", "jpg", "--quality", "0"]) == 1


def test_list_formats(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["convert", "--list-formats"]) == 0
    printed = capsys.readouterr().out
    assert ".heic" in printed and "webp (.webp)" in printed
    assert ".mpeg" not in printed


def test_videos_are_not_treated_as_images() -> None:
    assert ".mpeg" not in supported_input_extensions()
    assert ".mpg" not in supported_input_extensions()


def test_query_still_scrapes_and_scrape_word_is_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries: list[str] = []

    def fake_scrape(options: object) -> list[object]:
        queries.append(options.query)  # type: ignore[attr-defined]
        return []

    monkeypatch.setattr(cli_main, "scrape_images", fake_scrape)
    assert main(["kittens"]) == 0
    assert main(["scrape", "puppies"]) == 0
    assert main(["scrape", "convert"]) == 0  # searching for the word itself
    assert queries == ["kittens", "puppies", "convert"]


def test_debug_level_shows_progress_without_pillow_noise(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    source = _photo(tmp_path / "a.png")
    with caplog.at_level(logging.DEBUG):
        assert main(["convert", str(source), "--to", "webp", "--log-level", "DEBUG"]) == 0
    messages = [record.getMessage() for record in caplog.records]
    assert any("[1/1] a.png" in message for message in messages)
    assert logging.getLogger("image_scraper").level == logging.DEBUG
    assert logging.getLogger().level >= logging.INFO
