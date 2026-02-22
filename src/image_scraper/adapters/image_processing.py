"""Image post-processing adapter."""

from __future__ import annotations

import base64
import contextlib
import hashlib
from pathlib import Path
from typing import Any

from image_scraper.errors import DependencyError, DownloadError


def _require_pillow() -> Any:
    try:
        from PIL import Image
    except ImportError as error:
        raise DependencyError(
            "pillow",
            "Pillow is required for image processing",
            context={"install": "pip install Pillow"},
        ) from error
    return Image


def maybe_convert_webp_to_jpg(path: Path) -> Path:
    if path.suffix.lower() != ".webp":
        return path

    image_module = _require_pillow()

    target_path = path.with_suffix(".jpg")
    counter = 1
    while target_path.exists():
        target_path = path.with_name(f"{path.stem}_{counter}.jpg")
        counter += 1

    try:
        with image_module.open(path) as image:
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                image = image.convert("RGBA")
                background = image_module.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.getchannel("A"))
                converted = background
            else:
                converted = image.convert("RGB")
            converted.save(target_path, "JPEG", quality=95)
    except Exception as error:  # Pillow errors vary by format
        raise DownloadError(
            "convert_webp",
            "failed converting WebP to JPG",
            context={"source": str(path), "error": str(error)},
        ) from error

    with contextlib.suppress(FileNotFoundError):
        path.unlink()

    return target_path


def compress_image(path: Path, quality: int, max_width: int, max_height: int) -> None:
    if quality <= 0 and max_width <= 0 and max_height <= 0:
        return

    image_module = _require_pillow()

    try:
        with image_module.open(path) as image:
            width, height = image.size
            target_width, target_height = width, height

            if max_width > 0 and target_width > max_width:
                ratio = max_width / target_width
                target_width = max_width
                target_height = int(target_height * ratio)

            if max_height > 0 and target_height > max_height:
                ratio = max_height / target_height
                target_height = max_height
                target_width = int(target_width * ratio)

            if (target_width, target_height) != (width, height):
                image = image.resize((target_width, target_height), image_module.Resampling.LANCZOS)

            save_kwargs: dict[str, object] = {}
            if path.suffix.lower() in {".jpg", ".jpeg"}:
                if image.mode in ("RGBA", "LA") or (
                    image.mode == "P" and "transparency" in image.info
                ):
                    image = image.convert("RGB")
                save_kwargs["quality"] = max(1, min(quality if quality > 0 else 85, 100))

            image.save(path, **save_kwargs)
    except Exception as error:
        raise DownloadError(
            "compress_image",
            "failed to compress or resize image",
            context={"path": str(path), "error": str(error)},
        ) from error


def decode_data_uri(data_url: str) -> tuple[bytes, str, str]:
    if "base64," not in data_url:
        raise DownloadError("decode_data_uri", "data URI is missing base64 payload")

    header, encoded = data_url.split("base64,", 1)
    try:
        payload = base64.b64decode(encoded)
    except Exception as error:
        raise DownloadError(
            "decode_data_uri", "failed to decode data URI payload", context={"error": str(error)}
        ) from error

    if "image/png" in header:
        extension = ".png"
    elif "image/gif" in header:
        extension = ".gif"
    elif "image/webp" in header:
        extension = ".webp"
    else:
        extension = ".jpg"

    manifest_key = f"data:{hashlib.sha256(data_url.encode('utf-8')).hexdigest()}"
    return payload, extension, manifest_key
