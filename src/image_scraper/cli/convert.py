"""`convert` subcommand: batch image conversion and compression."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from image_scraper.adapters.image_converter import (
    KEEP_FORMAT,
    OUTPUT_FORMATS,
    ConversionOptions,
    available_output_formats,
    supported_input_extensions,
)
from image_scraper.app.convert import convert_image_batch, summarize_conversion
from image_scraper.errors import ImageScraperError

LOGGER = logging.getLogger("image_scraper")

FORMAT_ALIASES = {"jpg": "jpeg", "tif": "tiff", "heif": "heic"}
EXIT_OK = 0
EXIT_FAILED = 1  # configuration error, nothing to convert, or any file failed
EXIT_INTERRUPTED = 130


def _output_format(value: str) -> str:
    key = FORMAT_ALIASES.get(value.lower(), value.lower())
    if key != KEEP_FORMAT and key not in OUTPUT_FORMATS:
        choices = ", ".join([KEEP_FORMAT, *OUTPUT_FORMATS, *FORMAT_ALIASES])
        raise argparse.ArgumentTypeError(f"unknown format {value!r} (choose from {choices})")
    return key


def build_convert_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="image_scraper_multitool.py convert",
        description=(
            "Convert and/or compress images. Folders are scanned recursively; "
            "originals are never modified."
        ),
        epilog=(
            "examples:\n"
            "  convert photos/ --to webp --quality 80\n"
            "  convert IMG_0001.heic IMG_0002.heic --to jpg --strip-metadata\n"
            "  convert shots/ --max-width 1920 --only-smaller --output-dir small/"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("inputs", nargs="*", type=Path, help="Image files and/or folders.")
    parser.add_argument(
        "--to",
        dest="output_format",
        type=_output_format,
        default=KEEP_FORMAT,
        metavar="FORMAT",
        help="Output format: keep (default; re-encode each file in its own format to "
        "compress it), jpeg/jpg, png, webp, avif, heic, tiff, bmp, gif, ico.",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=85,
        help="Quality 1-100 for JPEG, WebP, AVIF, HEIC (default: 85).",
    )
    parser.add_argument(
        "--lossless", action="store_true", help="Lossless encoding (WebP and HEIC only)."
    )
    parser.add_argument(
        "--max-width", type=int, default=0, help="Shrink to fit this width (0 = no limit)."
    )
    parser.add_argument(
        "--max-height", type=int, default=0, help="Shrink to fit this height (0 = no limit)."
    )
    parser.add_argument(
        "--strip-metadata",
        action="store_true",
        help="Remove EXIF, GPS location and camera info (colour profiles are kept).",
    )
    parser.add_argument(
        "--only-smaller",
        action="store_true",
        help="Discard outputs that are not smaller than their original.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Write here, mirroring input folder structure (default: next to each original).",
    )
    parser.add_argument(
        "--list-formats", action="store_true", help="Print supported formats and exit."
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Logging verbosity (DEBUG shows per-file progress).",
    )
    return parser


def _parse(parser: argparse.ArgumentParser, argv: Sequence[str]) -> argparse.Namespace:
    args = parser.parse_args(argv)
    if args.list_formats:
        return args
    if not args.inputs:
        parser.error("at least one input file or folder is required")
    missing = [str(path) for path in args.inputs if not path.exists()]
    if missing:
        parser.error(f"input not found: {', '.join(missing)}")
    if args.lossless and args.output_format not in (KEEP_FORMAT, "webp", "heic"):
        parser.error("--lossless only applies to webp and heic output")
    return args


def _print_formats() -> None:
    readable = " ".join(sorted(supported_input_extensions()))
    writable = ", ".join(f"{fmt.key} ({fmt.extension})" for fmt in available_output_formats())
    print(f"Reads:  {readable}")
    print(f"Writes: {writable}")


def convert_main(argv: Sequence[str]) -> int:
    parser = build_convert_parser()
    args = _parse(parser, argv)
    level = getattr(logging, args.log_level)
    # DEBUG applies to this app only; Pillow's own debug output (plugin
    # imports, PNG chunk dumps) would bury the per-file progress lines.
    logging.basicConfig(level=max(level, logging.INFO), format="[%(levelname)s] %(message)s")
    LOGGER.setLevel(level)
    if args.list_formats:
        _print_formats()
        return EXIT_OK

    options = ConversionOptions(
        output_format=args.output_format,
        quality=args.quality,
        lossless=args.lossless,
        max_width=args.max_width,
        max_height=args.max_height,
        strip_metadata=args.strip_metadata,
        only_if_smaller=args.only_smaller,
        output_dir=args.output_dir,
    )

    def progress(index: int, total: int, name: str) -> None:
        LOGGER.debug("[%d/%d] %s", index, total, name)

    try:
        result = convert_image_batch(
            input_paths=list(args.inputs), options=options, progress_callback=progress
        )
    except ImageScraperError as error:
        LOGGER.error("%s", error)
        return EXIT_FAILED
    except KeyboardInterrupt:
        LOGGER.error("Interrupted; files already written are kept.")
        return EXIT_INTERRUPTED

    if result.total_files == 0:
        LOGGER.error("No supported images found in the given inputs.")
        return EXIT_FAILED

    LOGGER.info("%s", summarize_conversion(result))
    for message in result.errors:
        LOGGER.warning("skipped: %s", message)
    return EXIT_FAILED if result.failed else EXIT_OK
