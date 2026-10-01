"""Image conversion/compression against real files written by Pillow."""

from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any

import pytest
from PIL import Image, ImageCms

from image_scraper.adapters.image_converter import (
    KEEP_FORMAT,
    OUTPUT_FORMATS,
    ConversionOptions,
    collect_images,
    convert_images,
    supported_input_extensions,
)
from image_scraper.domain.models import BatchConversionResult
from image_scraper.errors import ConfigurationError

ORIENTATION = 0x0112
GPS_IFD = 0x8825
MAKE = 0x010F


def _photo(path: Path, size: tuple[int, int] = (64, 32), **save: Any) -> Path:
    image = Image.linear_gradient("L").resize(size).convert("RGB")
    image.save(path, **save)
    return path


def _exif(orientation: int = 1, gps: bool = True) -> bytes:
    exif = Image.Exif()
    exif[ORIENTATION] = orientation
    exif[MAKE] = "TestCam"
    if gps:
        exif.get_ifd(GPS_IFD)[2] = (51.0, 30.0, 0.0)  # GPSLatitude
    return exif.tobytes()


def _srgb_icc() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _run(paths: list[Path], **options: Any) -> BatchConversionResult:
    return convert_images(input_paths=paths, options=ConversionOptions(**options))


def _pixel(image: Image.Image, xy: tuple[int, int]) -> tuple[int, ...]:
    value = image.getpixel(xy)
    assert isinstance(value, tuple), value
    return value


def _grey(image: Image.Image, xy: tuple[int, int]) -> int:
    value = image.getpixel(xy)
    assert isinstance(value, int), value
    return value


def _outputs(folder: Path, suffix: str) -> list[Path]:
    return sorted(path for path in folder.rglob(f"*{suffix}"))


@pytest.mark.parametrize("key", sorted(OUTPUT_FORMATS))
def test_every_output_format_round_trips(tmp_path: Path, key: str) -> None:
    source = _photo(tmp_path / "src.png")
    out = tmp_path / "out"
    result = _run([source], output_format=key, output_dir=out)
    assert result.converted == 1, result.errors
    (written,) = _outputs(out, OUTPUT_FORMATS[key].extension)
    with Image.open(written) as reopened:
        assert reopened.format == OUTPUT_FORMATS[key].pillow_format
        reopened.load()


def test_heic_input_is_read(tmp_path: Path) -> None:
    pytest.importorskip("pillow_heif")
    source = _photo(tmp_path / "phone.heic", format="HEIF")
    result = _run([source], output_format="jpeg")
    assert result.converted == 1, result.errors
    assert (tmp_path / "phone.jpg").exists()


def test_alpha_is_flattened_on_white_for_jpeg(tmp_path: Path) -> None:
    source = tmp_path / "logo.png"
    Image.new("RGBA", (8, 8), (255, 0, 0, 0)).save(source)
    _run([source], output_format="jpeg")
    with Image.open(tmp_path / "logo.jpg") as out:
        assert out.mode == "RGB"
        red, green, blue = _pixel(out, (4, 4))
        assert min(red, green, blue) > 240  # white, not black


def test_alpha_is_kept_for_webp(tmp_path: Path) -> None:
    source = tmp_path / "logo.png"
    Image.new("RGBA", (8, 8), (255, 0, 0, 0)).save(source)
    _run([source], output_format="webp", lossless=True)
    with Image.open(tmp_path / "logo.webp") as out:
        assert out.mode == "RGBA"
        assert _pixel(out, (4, 4))[3] == 0


def test_exif_orientation_is_applied(tmp_path: Path) -> None:
    source = _photo(tmp_path / "rotated.jpg", size=(60, 20), exif=_exif(orientation=6))
    _run([source], output_format="png")
    with Image.open(tmp_path / "rotated.png") as out:
        assert out.size == (20, 60)
        assert out.getexif().get(ORIENTATION) in (None, 1)


@pytest.mark.parametrize("key", ["jpeg", "webp", "png", "avif", "heic", "tiff"])
def test_strip_metadata_removes_exif_and_gps(tmp_path: Path, key: str) -> None:
    if key == "heic":
        pytest.importorskip("pillow_heif")
    source = _photo(tmp_path / "gps.jpg", exif=_exif())
    out = tmp_path / "out"
    _run([source], output_format=key, output_dir=out, strip_metadata=True)
    (written,) = _outputs(out, OUTPUT_FORMATS[key].extension)
    with Image.open(written) as reopened:
        exif = reopened.getexif()
        assert exif.get(MAKE) is None
        assert not exif.get_ifd(GPS_IFD)


def test_metadata_kept_by_default(tmp_path: Path) -> None:
    source = _photo(tmp_path / "cam.jpg", exif=_exif())
    _run([source], output_format="webp")
    with Image.open(tmp_path / "cam.webp") as out:
        assert out.getexif().get(MAKE) == "TestCam"


def test_icc_profile_is_preserved(tmp_path: Path) -> None:
    icc = _srgb_icc()
    source = _photo(tmp_path / "p3.jpg", icc_profile=icc)
    _run([source], output_format="webp", strip_metadata=True)
    with Image.open(tmp_path / "p3.webp") as out:
        assert out.info.get("icc_profile") == icc


def test_cmyk_profile_not_attached_to_rgb_output(tmp_path: Path) -> None:
    source = tmp_path / "print.jpg"
    Image.new("CMYK", (8, 8), (0, 50, 50, 0)).save(source, icc_profile=b"fake-cmyk-profile")
    result = _run([source], output_format="webp")
    assert result.converted == 1, result.errors
    with Image.open(tmp_path / "print.webp") as out:
        assert out.mode == "RGB"
        assert "icc_profile" not in out.info


def test_resize_fits_within_bounds_and_never_upscales(tmp_path: Path) -> None:
    big = _photo(tmp_path / "big.png", size=(400, 200))
    small = _photo(tmp_path / "small.png", size=(50, 25))
    out = tmp_path / "out"
    _run([big, small], output_format="png", max_width=100, max_height=100, output_dir=out)
    with Image.open(out / "big.png") as resized, Image.open(out / "small.png") as untouched:
        assert resized.size == (100, 50)
        assert untouched.size == (50, 25)


def test_keep_format_compresses_next_to_source_without_overwriting(tmp_path: Path) -> None:
    source = _photo(tmp_path / "shot.jpg", size=(256, 256), quality=100)
    original = source.read_bytes()
    result = _run([source], output_format=KEEP_FORMAT, quality=40)
    assert result.converted == 1, result.errors
    assert source.read_bytes() == original
    compressed = tmp_path / "shot_compressed.jpg"
    assert compressed.stat().st_size < len(original)
    assert result.bytes_in == len(original)
    assert result.bytes_out == compressed.stat().st_size


def test_only_if_smaller_discards_larger_output(tmp_path: Path) -> None:
    # Heavy noise at low JPEG quality: lossless PNG of it is far larger.
    source = tmp_path / "noisy.jpg"
    Image.effect_noise((128, 128), 120).convert("RGB").save(source, quality=10)
    result = _run([source], output_format="png", only_if_smaller=True)
    assert result.converted == 0
    assert result.skipped == 1
    assert "not smaller" in result.errors[0]
    assert not (tmp_path / "noisy.png").exists()
    assert not list(tmp_path.glob(".*.part"))


def test_folder_structure_is_mirrored_and_per_file_source_dirs(tmp_path: Path) -> None:
    root = tmp_path / "photos"
    (root / "2024" / "trip").mkdir(parents=True)
    _photo(root / "a.png")
    _photo(root / "2024" / "trip" / "b.png")
    out = tmp_path / "out"
    _run([root], output_format="jpeg", output_dir=out)
    assert (out / "a.jpg").exists()
    assert (out / "2024" / "trip" / "b.jpg").exists()

    _run([root], output_format="webp")
    assert (root / "a.webp").exists()
    assert (root / "2024" / "trip" / "b.webp").exists()


def test_name_collisions_get_unique_names(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    out = tmp_path / "out"
    _run([_photo(first / "x.png"), _photo(second / "x.png")], output_format="jpeg", output_dir=out)
    assert sorted(path.name for path in out.iterdir()) == ["x.jpg", "x_1.jpg"]


def test_sixteen_bit_greyscale_is_scaled_not_clipped(tmp_path: Path) -> None:
    source = tmp_path / "deep.png"
    Image.new("I;16", (4, 4), 32768).save(source)
    _run([source], output_format="jpeg")
    with Image.open(tmp_path / "deep.jpg") as out:
        assert 110 < _grey(out.convert("L"), (1, 1)) < 145


def test_corrupt_file_is_reported_and_batch_continues(tmp_path: Path) -> None:
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"not an image")
    good = _photo(tmp_path / "good.png")
    result = _run([broken, good], output_format="jpeg")
    assert result.converted == 1
    assert result.skipped == 1
    assert "broken.jpg" in result.errors[0]
    assert not list(tmp_path.glob(".*.part"))


def test_stop_event_halts_batch(tmp_path: Path) -> None:
    sources = [_photo(tmp_path / f"{index}.png") for index in range(3)]
    stop = Event()
    stop.set()
    result = convert_images(
        input_paths=sources, options=ConversionOptions(output_format="jpeg"), stop_event=stop
    )
    assert result.converted == 0


def test_collect_filters_unsupported_and_deduplicates(tmp_path: Path) -> None:
    image = _photo(tmp_path / "a.png")
    (tmp_path / "notes.txt").write_text("x")
    found = collect_images([tmp_path, image], supported_input_extensions())
    assert [source.path.name for source in found] == ["a.png"]


def test_supported_inputs_cover_common_formats() -> None:
    extensions = supported_input_extensions()
    for extension in (".jpg", ".png", ".webp", ".avif", ".gif", ".tiff", ".bmp", ".ico"):
        assert extension in extensions
    assert ".eps" not in extensions


def test_invalid_options_rejected() -> None:
    with pytest.raises(ConfigurationError):
        ConversionOptions(output_format="psd").validate()
    with pytest.raises(ConfigurationError):
        ConversionOptions(quality=0).validate()
    with pytest.raises(ConfigurationError):
        ConversionOptions(max_width=-1).validate()


def test_gif_from_rgba_keeps_transparency(tmp_path: Path) -> None:
    source = tmp_path / "sprite.png"
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    image.putpixel((2, 2), (255, 0, 0, 255))
    image.save(source)
    _run([source], output_format="gif")
    with Image.open(tmp_path / "sprite.gif") as out:
        rgba = out.convert("RGBA")
        assert _pixel(rgba, (0, 0))[3] == 0
        assert _pixel(rgba, (2, 2))[3] == 255


def test_summary_reports_size_change() -> None:
    from image_scraper.app.convert import summarize_conversion
    from image_scraper.domain.models import BatchConversionResult

    result = BatchConversionResult(
        total_files=2,
        converted=2,
        skipped=0,
        errors=[],
        output_dir=Path("out"),
        bytes_in=4 * 1024 * 1024,
        bytes_out=1024 * 1024,
    )
    assert "4.0 MB -> 1.0 MB (-75%)" in summarize_conversion(result)


def test_convert_single_image_and_delete_original(tmp_path: Path) -> None:
    from image_scraper.adapters.downloader import resolve_download_conversion
    from image_scraper.adapters.image_converter import convert_single_image
    from image_scraper.domain.models import TransformOptions

    # 1. Test convert_single_image with delete_original=True (e.g. WebP to JPEG)
    source = _photo(tmp_path / "photo.webp")
    assert source.exists()
    out = convert_single_image(
        source,
        ConversionOptions(output_format="jpeg"),
        delete_original=True,
    )
    assert out.suffix.lower() == ".jpg"
    assert out.exists()
    assert not source.exists()  # Original WebP deleted

    # 2. Test resolve_download_conversion backward compatibility
    # convert_webp flag
    opts, delete = resolve_download_conversion(
        TransformOptions(convert_webp=True), Path("test.webp")
    )
    assert opts is not None and opts.output_format == "jpeg" and delete is True

    # non-webp with convert_webp
    opts, delete = resolve_download_conversion(
        TransformOptions(convert_webp=True), Path("test.png")
    )
    assert opts is None and delete is False

    # unified format
    opts, delete = resolve_download_conversion(TransformOptions(format="webp"), Path("test.png"))
    assert opts is not None and opts.output_format == "webp" and delete is False
