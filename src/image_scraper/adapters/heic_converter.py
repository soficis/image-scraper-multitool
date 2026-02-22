"""HEIC/HEIF conversion adapter."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from image_scraper.domain.models import BatchConversionResult
from image_scraper.errors import DependencyError, EngineError


def collect_heic_files(paths: list[Path]) -> list[Path]:
    heic_extensions = {".heic", ".heif"}
    collected: list[Path] = []

    for path in paths:
        if path.is_file() and path.suffix.lower() in heic_extensions:
            collected.append(path)
            continue

        if path.is_dir():
            for candidate in path.rglob("*"):
                if candidate.is_file() and candidate.suffix.lower() in heic_extensions:
                    collected.append(candidate)

    seen: set[Path] = set()
    unique: list[Path] = []
    for item in collected:
        resolved = item.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(item)
    return unique


def convert_heic_files(
    *,
    input_paths: list[Path],
    output_dir: Path,
    output_format: str,
    quality: int,
    stop_event: Event | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> BatchConversionResult:
    try:
        from pillow_heif import register_heif_opener
    except ImportError as error:
        raise DependencyError(
            "pillow_heif",
            "pillow-heif is required for HEIC conversion",
            context={"install": "pip install pillow-heif"},
        ) from error

    try:
        from PIL import Image
    except ImportError as error:
        raise DependencyError(
            "Pillow",
            "Pillow is required for HEIC conversion",
            context={"install": "pip install Pillow"},
        ) from error

    register_heif_opener()

    files = collect_heic_files(input_paths)
    total_files = len(files)
    output_dir.mkdir(parents=True, exist_ok=True)

    if total_files == 0:
        return BatchConversionResult(
            total_files=0,
            converted=0,
            skipped=0,
            errors=[],
            output_dir=output_dir,
        )

    normalized_format = output_format.lower().strip()
    if normalized_format not in {"jpg", "jpeg", "png"}:
        raise EngineError(
            "convert_heic",
            "output_format must be one of: jpg, jpeg, png",
            context={"output_format": output_format},
        )

    quality = max(1, min(quality, 100))
    extension = ".jpg" if normalized_format in {"jpg", "jpeg"} else ".png"

    converted = 0
    skipped = 0
    errors: list[str] = []

    for index, source in enumerate(files, start=1):
        if stop_event and stop_event.is_set():
            break

        if progress_callback is not None:
            progress_callback(index, total_files, source.name)

        destination = output_dir / f"{source.stem}{extension}"
        suffix = 1
        while destination.exists():
            destination = output_dir / f"{source.stem}_{suffix}{extension}"
            suffix += 1

        try:
            with Image.open(source) as opened_image:
                image: Any = opened_image
                if extension == ".jpg":
                    if image.mode in ("RGBA", "LA") or (
                        image.mode == "P" and "transparency" in image.info
                    ):
                        image = image.convert("RGBA")
                        background = Image.new("RGB", image.size, (255, 255, 255))
                        background.paste(image, mask=image.getchannel("A"))
                        image = background
                    else:
                        image = image.convert("RGB")
                    image.save(destination, "JPEG", quality=quality)
                else:
                    if image.mode == "P":
                        image = image.convert("RGBA")
                    compress_level = max(0, min(9, 9 - quality // 11))
                    image.save(destination, "PNG", compress_level=compress_level)
            converted += 1
        except Exception as error:
            skipped += 1
            errors.append(f"{source.name} ({error})")

    return BatchConversionResult(
        total_files=total_files,
        converted=converted,
        skipped=skipped,
        errors=errors,
        output_dir=output_dir,
    )
