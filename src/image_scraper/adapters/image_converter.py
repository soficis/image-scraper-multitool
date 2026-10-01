"""General-purpose image conversion and compression adapter.

Reads anything Pillow can decode plus HEIC/HEIF (via pillow-heif) and writes
one of OUTPUT_FORMATS, or re-encodes each file in its own format to compress
it. Per file: EXIF orientation is applied, the colour (ICC) profile is always
kept, other metadata is kept unless stripped, and output is written to a
temporary file first so a failure never leaves a truncated image behind.
Source files are never modified.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from image_scraper.domain.models import BatchConversionResult
from image_scraper.errors import ConfigurationError, DependencyError

from .filesystem import unique_path

KEEP_FORMAT = "keep"


@dataclass(frozen=True)
class OutputFormat:
    key: str
    label: str
    pillow_format: str
    extension: str
    alpha: bool
    uses_quality: bool
    has_lossless: bool


OUTPUT_FORMATS: dict[str, OutputFormat] = {
    fmt.key: fmt
    for fmt in (
        OutputFormat("jpeg", "JPEG", "JPEG", ".jpg", False, True, False),
        OutputFormat("png", "PNG", "PNG", ".png", True, False, False),
        OutputFormat("webp", "WebP", "WEBP", ".webp", True, True, True),
        # Pillow's AVIF encoder has no lossless mode; quality 100 is closest.
        OutputFormat("avif", "AVIF", "AVIF", ".avif", True, True, False),
        OutputFormat("heic", "HEIC", "HEIF", ".heic", True, True, True),
        OutputFormat("tiff", "TIFF", "TIFF", ".tiff", True, False, False),
        OutputFormat("bmp", "BMP", "BMP", ".bmp", False, False, False),
        OutputFormat("gif", "GIF", "GIF", ".gif", True, False, False),
        OutputFormat("ico", "ICO", "ICO", ".ico", True, False, False),
    )
}

# Source Pillow format -> output key used for "keep original format".
_KEEP_MAP = {
    "JPEG": "jpeg",
    "MPO": "jpeg",
    "PNG": "png",
    "WEBP": "webp",
    "AVIF": "avif",
    "HEIF": "heic",
    "TIFF": "tiff",
    "BMP": "bmp",
    "DIB": "bmp",
    "GIF": "gif",
    "ICO": "ico",
}
# Formats readable only through stubs or external programs, or (MPEG) only
# identified, never decoded: listing them would turn videos into failures.
_UNREADABLE_FORMATS = {"EPS", "PDF", "WMF", "BUFR", "GRIB", "HDF5", "MPEG"}
_KEPT_INFO_KEYS = ("icc_profile", "transparency")


@dataclass(frozen=True)
class ConversionOptions:
    output_format: str = KEEP_FORMAT
    quality: int = 85
    lossless: bool = False
    max_width: int = 0
    max_height: int = 0
    strip_metadata: bool = False
    only_if_smaller: bool = False
    output_dir: Path | None = None  # None: next to each source file

    def validate(self) -> None:
        if self.output_format != KEEP_FORMAT and self.output_format not in OUTPUT_FORMATS:
            raise ConfigurationError(
                "convert_images",
                "unsupported output format",
                context={
                    "output_format": self.output_format,
                    "choices": [KEEP_FORMAT, *OUTPUT_FORMATS],
                },
            )
        if not 1 <= self.quality <= 100:
            raise ConfigurationError(
                "convert_images", "quality must be 1-100", context={"quality": self.quality}
            )
        if self.max_width < 0 or self.max_height < 0:
            raise ConfigurationError(
                "convert_images",
                "max dimensions cannot be negative",
                context={"max_width": self.max_width, "max_height": self.max_height},
            )


@dataclass(frozen=True)
class SourceImage:
    path: Path
    relative_dir: Path  # sub-path below the selected folder; "." for picked files


def _pillow() -> tuple[Any, Any]:
    try:
        from PIL import Image, ImageOps
    except ImportError as error:
        raise DependencyError(
            "Pillow",
            "Pillow is required for image conversion",
            context={"install": "pip install Pillow"},
        ) from error
    # HEIC is optional: without pillow-heif everything else still works.
    with contextlib.suppress(ImportError):
        from pillow_heif import register_heif_opener

        register_heif_opener()
    # Plugins such as AVIF load lazily; without init() Image.SAVE is partial.
    Image.init()
    return Image, ImageOps


def supported_input_extensions() -> frozenset[str]:
    image_module, _ = _pillow()
    return frozenset(
        extension.lower()
        for extension, fmt in image_module.registered_extensions().items()
        if fmt in image_module.OPEN and fmt not in _UNREADABLE_FORMATS
    )


def available_output_formats() -> list[OutputFormat]:
    image_module, _ = _pillow()
    return [fmt for fmt in OUTPUT_FORMATS.values() if fmt.pillow_format in image_module.SAVE]


def collect_images(paths: list[Path], extensions: frozenset[str]) -> list[SourceImage]:
    """Expand files and folders (recursively) into unique convertible images."""
    found: list[SourceImage] = []
    seen: set[Path] = set()

    def add(path: Path, relative_dir: Path) -> None:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            found.append(SourceImage(path=path, relative_dir=relative_dir))

    for path in paths:
        if path.is_file():
            if path.suffix.lower() in extensions:
                add(path, Path("."))
        elif path.is_dir():
            for candidate in sorted(path.rglob("*")):
                if candidate.is_file() and candidate.suffix.lower() in extensions:
                    add(candidate, candidate.parent.relative_to(path))
    return found


def _has_alpha(image: Any) -> bool:
    return image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info


def _to_8bit(image: Any) -> Any:
    # 16-bit and float greyscale clip to white on a direct convert; rescale.
    if image.mode in ("I;16", "I;16B", "I;16L", "I"):
        maximum = 65535 if image.mode.startswith("I;16") else (image.getextrema()[1] or 1)
        return image.convert("I").point(lambda value: value * (255 / maximum)).convert("L")
    if image.mode == "F":
        low, high = image.getextrema()
        span = (high - low) or 1
        return image.point(lambda value: (value - low) * (255 / span)).convert("L")
    return image


def _prepare_mode(image: Any, fmt: OutputFormat, image_module: Any) -> Any:
    image = _to_8bit(image) if fmt.key not in ("png", "tiff") else image
    alpha = _has_alpha(image)

    if alpha and not fmt.alpha:
        rgba = image.convert("RGBA")
        background = image_module.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        background.info = _without_transparency(image.info)
        return background

    allowed: dict[str, tuple[str, ...]] = {
        "jpeg": ("L", "RGB", "CMYK"),
        "png": ("1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA"),
        "bmp": ("1", "L", "P", "RGB"),
        "tiff": ("1", "L", "LA", "I", "I;16", "F", "P", "RGB", "RGBA", "CMYK"),
        "gif": ("1", "L", "P", "RGB", "RGBA"),
    }
    if image.mode in allowed.get(fmt.key, ("RGB", "RGBA")):
        return image
    converted = image.convert("RGBA" if alpha else "RGB")
    converted.info = _without_transparency(image.info)
    return converted


def _without_transparency(info: dict[str, Any]) -> dict[str, Any]:
    # Once alpha lives in a real channel (or is flattened), a palette/colour-key
    # "transparency" entry is stale and some writers misapply it.
    return {key: value for key, value in info.items() if key != "transparency"}


def _colour_family(mode: str) -> str:
    if mode == "CMYK":
        return "cmyk"
    if mode in ("RGB", "RGBA", "P", "PA", "RGBX", "YCbCr"):
        return "rgb"
    return "grey"


def _save_kwargs(
    fmt: OutputFormat, options: ConversionOptions, icc: bytes | None, exif: bytes | None
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    quality = options.quality
    if fmt.key == "jpeg":
        kwargs.update(quality=quality, optimize=True, progressive=True)
        if quality >= 90:
            kwargs["subsampling"] = 0  # 4:4:4 keeps fine colour detail
    elif fmt.key == "png":
        kwargs["optimize"] = True
    elif fmt.key == "webp":
        kwargs.update(quality=quality, method=6, lossless=options.lossless)
    elif fmt.key == "avif":
        kwargs["quality"] = quality
        if quality >= 90:
            kwargs["subsampling"] = "4:4:4"
    elif fmt.key == "heic":
        kwargs["quality"] = -1 if options.lossless else quality
    elif fmt.key == "tiff":
        kwargs["compression"] = "tiff_adobe_deflate"
    elif fmt.key == "gif":
        kwargs["optimize"] = True

    if fmt.key in ("jpeg", "png", "webp", "avif", "heic", "tiff"):
        if icc:
            kwargs["icc_profile"] = icc
        if exif:
            kwargs["exif"] = exif
    return kwargs


def _target_path(
    source: SourceImage,
    fmt: OutputFormat,
    options: ConversionOptions,
    *,
    allow_in_place: bool = False,
) -> Path:
    base_dir = (
        options.output_dir / source.relative_dir
        if options.output_dir is not None
        else source.path.parent
    )
    target = base_dir / f"{source.path.stem}{fmt.extension}"
    if target.resolve() == source.path.resolve():
        if allow_in_place:
            return target
        target = base_dir / f"{source.path.stem}_compressed{fmt.extension}"
    return unique_path(target)


def _convert_one(
    source: SourceImage,
    options: ConversionOptions,
    image_module: Any,
    image_ops: Any,
    *,
    allow_in_place: bool = False,
) -> tuple[Path | None, int, int]:
    """Convert one file. Returns (written path or None if not smaller, in, out bytes)."""
    source_bytes = source.path.stat().st_size
    with image_module.open(source.path) as opened:
        fmt_key = (
            _KEEP_MAP.get(opened.format or "", "png")
            if options.output_format == KEEP_FORMAT
            else options.output_format
        )
        fmt = OUTPUT_FORMATS[fmt_key]
        image = image_ops.exif_transpose(opened)  # first frame, loaded copy

    icc = image.info.get("icc_profile")
    exif_data = image.getexif()
    exif = None if options.strip_metadata or not len(exif_data) else exif_data.tobytes()
    # Continue on a fresh copy holding only ICC/transparency: some writers
    # (HEIF, TIFF) silently re-emit EXIF/XMP from info or from the cached
    # getexif() object, which would defeat strip_metadata.
    kept_info = {key: image.info[key] for key in _KEPT_INFO_KEYS if key in image.info}
    image = image.copy()
    image.info = kept_info

    source_family = _colour_family(image.mode)
    image = _prepare_mode(image, fmt, image_module)
    if _colour_family(image.mode) != source_family:
        # An ICC profile describes one colour space; attaching a CMYK or grey
        # profile to RGB pixels makes viewers render garbage.
        icc = None
    if options.max_width or options.max_height:
        bound = (options.max_width or image.width, options.max_height or image.height)
        image.thumbnail(bound, image_module.Resampling.LANCZOS)

    target = _target_path(source, fmt, options, allow_in_place=allow_in_place)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.part")
    try:
        image.save(temporary, fmt.pillow_format, **_save_kwargs(fmt, options, icc, exif))
        written = temporary.stat().st_size
        if options.only_if_smaller and written >= source_bytes:
            temporary.unlink()
            return None, source_bytes, written
        os.replace(temporary, target)
    except BaseException:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise
    return target, source_bytes, written


def convert_single_image(
    path: Path,
    options: ConversionOptions,
    *,
    delete_original: bool = False,
) -> Path:
    """Convert a single image file using ConversionOptions.

    Returns the Path to the converted image.
    If delete_original is True, any original file with a different path is removed.
    """
    options.validate()
    image_module, image_ops = _pillow()
    if options.output_format != KEEP_FORMAT:
        wanted = OUTPUT_FORMATS.get(options.output_format)
        if wanted and wanted.pillow_format not in image_module.SAVE:
            raise DependencyError(
                wanted.key,
                f"{wanted.label} output is not available in this installation",
                context={"install": "pip install pillow-heif" if wanted.key == "heic" else ""},
            )

    source = SourceImage(path=path, relative_dir=Path("."))
    written, _size_in, _size_out = _convert_one(
        source, options, image_module, image_ops, allow_in_place=delete_original
    )
    if written is None:
        return path
    if delete_original and written.resolve() != path.resolve():
        with contextlib.suppress(OSError):
            path.unlink()
    return written


def convert_images(
    *,
    input_paths: list[Path],
    options: ConversionOptions,
    stop_event: Event | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> BatchConversionResult:
    options.validate()
    image_module, image_ops = _pillow()
    if options.output_format != KEEP_FORMAT:
        wanted = OUTPUT_FORMATS[options.output_format]
        if wanted.pillow_format not in image_module.SAVE:
            raise DependencyError(
                wanted.key,
                f"{wanted.label} output is not available in this installation",
                context={"install": "pip install pillow-heif" if wanted.key == "heic" else ""},
            )

    files = collect_images(input_paths, supported_input_extensions())
    if options.output_dir is not None:
        output_dir = options.output_dir
    elif input_paths:
        output_dir = input_paths[0] if input_paths[0].is_dir() else input_paths[0].parent
    else:
        output_dir = Path(".")
    converted = skipped = failed = bytes_in = bytes_out = 0
    errors: list[str] = []

    for index, source in enumerate(files, start=1):
        if stop_event and stop_event.is_set():
            break
        if progress_callback is not None:
            progress_callback(index, len(files), source.path.name)
        try:
            written, size_in, size_out = _convert_one(source, options, image_module, image_ops)
        except Exception as error:  # Pillow raises many unrelated types per codec
            skipped += 1
            failed += 1
            errors.append(f"{source.path} ({error.__class__.__name__}: {error})")
            continue
        if written is None:
            skipped += 1
            errors.append(f"{source.path} (not smaller: {size_out} >= {size_in} bytes; kept)")
            continue
        converted += 1
        bytes_in += size_in
        bytes_out += size_out

    return BatchConversionResult(
        total_files=len(files),
        converted=converted,
        skipped=skipped,
        errors=errors,
        output_dir=output_dir,
        bytes_in=bytes_in,
        bytes_out=bytes_out,
        failed=failed,
    )
