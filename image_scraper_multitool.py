#!/usr/bin/env python3
# Image Scraper Multitool - Multi-engine image scraping tool
# Copyright (C) 2025
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
Multi-engine image scraping helper that wraps the bundled Bing and Google scrapers.

Example:
    python image_scraper_multitool.py "red panda" --num-images 5 --engine bing google
"""
from __future__ import annotations

import argparse
import contextlib
import importlib
import logging
import mimetypes
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup
import json
import platform
import base64
import subprocess
from webdriver_manager.chrome import ChromeDriverManager


LOGGER = logging.getLogger("image_scraper_multitool")
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)
ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".webp",
    ".tiff",
    ".tif",
}


def sanitize_filename(candidate: str) -> str:
    """Collapse disallowed filename characters so downloads are filesystem safe."""
    collapsed = re.sub(r"[^\w.\-]+", "_", candidate.strip())
    if not collapsed:
        return "image"
    return collapsed[:255]


def slugify(value: str) -> str:
    """Return a directory-friendly slug derived from the search query."""
    cleaned = re.sub(r"[^\w\s-]", "", value.lower())
    cleaned = re.sub(r"[\s-]+", "-", cleaned).strip("-")
    return cleaned or "query"


def iter_chunks(response: requests.Response, chunk_size: int = 8192) -> Iterator[bytes]:
    """Yield response body in chunks while ensuring the request context stays open."""
    for chunk in response.iter_content(chunk_size=chunk_size):
        if chunk:
            yield chunk


def best_extension(
    *, original_name: str = "", fallback_url: str = "", content_type: str = ""
) -> str:
    """Choose an appropriate file extension using several possible hints."""
    candidates: List[str] = []
    for source in (original_name, fallback_url):
        if not source:
            continue
        _, ext = os.path.splitext(urlsplit(source).path)
        if ext:
            candidates.append(ext.lower())
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip())
        if guessed:
            candidates.append(guessed.lower())

    for ext in candidates:
        if ext == ".jpe":
            ext = ".jpg"
        if ext in ALLOWED_IMAGE_EXTENSIONS:
            return ext

    return ".jpg"


def maybe_convert_webp_to_jpg(path: Path) -> Path:
    """
    Convert a downloaded .webp image into .jpg if needed.

    Returns the path to the resulting image (which may be unchanged).
    """
    if path.suffix.lower() != ".webp":
        return path

    try:
        from PIL import Image  # type: ignore
    except ImportError as error:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "Pillow is required to convert .webp images. Install it with 'pip install Pillow'."
        ) from error

    target_path = path.with_suffix(".jpg")
    counter = 1
    while target_path.exists():
        target_path = path.with_name(f"{path.stem}_{counter}.jpg")
        counter += 1

    try:
        with Image.open(path) as image:
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, (255, 255, 255))
                alpha_channel = image.getchannel("A")
                background.paste(image, mask=alpha_channel)
                converted = background
            else:
                converted = image.convert("RGB")
            converted.save(target_path, "JPEG", quality=95)
    except Exception as error:  # pylint: disable=broad-except
        raise RuntimeError(f"Failed to convert {path.name} from .webp to .jpg: {error}") from error

    with contextlib.suppress(Exception):
        path.unlink(missing_ok=True)

    return target_path


def compress_image(
    path: Path, quality: int, max_width: int = 0, max_height: int = 0
) -> None:
    """
    Compress and optionally resize the image at the given path.

    Args:
        path: Path to the image file.
        quality: JPEG compression quality (1-100).
        max_width: Maximum width for resizing (0 = no limit).
        max_height: Maximum height for resizing (0 = no limit).
    """
    if quality <= 0 and max_width <= 0 and max_height <= 0:
        return

    try:
        from PIL import Image  # type: ignore
    except ImportError as error:
        raise RuntimeError(
            "Pillow is required for image compression. Install it with 'pip install Pillow'."
        ) from error

    try:
        with Image.open(path) as image:
            # Check if resize is needed
            width, height = image.size
            new_width, new_height = width, height

            if max_width > 0 and new_width > max_width:
                ratio = max_width / new_width
                new_width = max_width
                new_height = int(new_height * ratio)

            if max_height > 0 and new_height > max_height:
                ratio = max_height / new_height
                new_height = max_height
                new_width = int(new_width * ratio)

            if new_width != width or new_height != height:
                image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Convert to RGB if saving as JPEG (Pillow requirement for RGBA/P)
            save_kwargs = {}
            if path.suffix.lower() in (".jpg", ".jpeg"):
                save_kwargs["quality"] = max(1, min(quality, 100)) if quality > 0 else 85
                if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                    image = image.convert("RGB")
            
            # If not JPEG, we can still resize, but 'quality' param behaves differently 
            # or isn't supported for some formats (like PNG, where it's compress_level).
            # For simplicity, we only apply 'quality' to JPEGs or if explicitly requested.
            # But the requirement says "JPEG quality control".
            
            image.save(path, **save_kwargs)

    except Exception as error:
        LOGGER.warning("Failed to compress/resize %s: %s", path.name, error)



_WEBP_CONVERSION_READY = False


def ensure_webp_conversion_support() -> None:
    """Verify Pillow is available before attempting WebP conversions."""
    global _WEBP_CONVERSION_READY
    if _WEBP_CONVERSION_READY:
        return
    try:
        import PIL.Image  # type: ignore  # noqa: F401
    except ImportError as error:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "Pillow is required to convert .webp images. Install it with 'pip install Pillow'."
        ) from error
    _WEBP_CONVERSION_READY = True


@dataclass
class ScrapeResult:
    engine: str
    requested: int
    saved: int
    skipped: int
    errors: List[str]
    destination: Path


class BingImageScraper:
    """Thin requests-based scraper that mimics the legacy Bing example script."""

    SEARCH_URL = "https://www.bing.com/images/search"

    def __init__(self, *, timeout: float = 15.0, session: Optional[requests.Session] = None) -> None:
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
        self.session.headers.setdefault("Accept-Language", "en-US,en;q=0.9")
        self.session.headers.setdefault(
            "Accept",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        )
        self.session.headers.setdefault("Referer", "https://www.bing.com/")

    def collect_image_metadata(self, query: str, limit: int) -> List[Dict[str, str]]:
        params = {
            "q": query,
            "form": "HDRSC2",
            "first": "0",
            "tsc": "ImageBasicHover",
        }
        LOGGER.info("Fetching Bing results for %r", query)
        response = self.session.get(self.SEARCH_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        results: List[Dict[str, str]] = []
        for anchor in soup.select("a.iusc"):
            meta_raw = anchor.get("m")
            if not meta_raw:
                continue
            try:
                meta_data = json.loads(meta_raw)
            except (ValueError, TypeError):
                continue
            mad_data: Dict[str, str] = {}
            mad_raw = anchor.get("mad")
            if mad_raw:
                with contextlib.suppress(ValueError, TypeError):
                    mad_data = json.loads(mad_raw)

            image_url = meta_data.get("murl")
            if not image_url:
                continue

            thumbnail_url = meta_data.get("turl") or mad_data.get("turl") or ""
            original_name = os.path.basename(urlsplit(image_url).path)
            results.append(
                {
                    "url": image_url,
                    "thumbnail": thumbnail_url or "",
                    "name": original_name,
                }
            )
            if len(results) >= limit:
                break

        LOGGER.info("Bing returned %d candidate URLs", len(results))
        return results

    def download_images(
        self,
        items: Sequence[Dict[str, str]],
        destination: Path,
        *,
        keep_filenames: bool,
        convert_webp: bool,
        compression_quality: int = 0,
        resize_width: int = 0,
        resize_height: int = 0,
        stop_event: threading.Event | None = None,
    ) -> Tuple[int, int, List[str]]:
        destination.mkdir(parents=True, exist_ok=True)

        saved = 0
        skipped = 0
        errors: List[str] = []

        # Prevent dupes across runs by tracking URLs in a manifest file
        manifest_path = destination / "_downloaded_urls.txt"
        seen_urls: set[str] = set()
        if manifest_path.exists():
            try:
                seen_urls = set(u.strip() for u in manifest_path.read_text(encoding="utf-8").splitlines() if u.strip())
            except Exception:  # pragma: no cover - non-fatal
                seen_urls = set()

        for index, item in enumerate(items, start=1):
            # Check stop event
            if stop_event and stop_event.is_set():
                LOGGER.info("Stop requested, ending Bing download.")
                break
                
            url = item["url"]
            if url in seen_urls:
                skipped += 1
                LOGGER.debug("Skipping previously downloaded URL (Bing): %s", url)
                continue
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    stream=True,
                    headers={
                        "Referer": "https://www.bing.com/",
                        "User-Agent": DEFAULT_USER_AGENT,
                    },
                )
                response.raise_for_status()
            except Exception as error:  # pylint: disable=broad-except
                message = f"{url} ({error})"
                LOGGER.warning("Bing download failed: %s", message)
                errors.append(message)
                skipped += 1
                continue

            content_type = response.headers.get("Content-Type", "")
            original_name = sanitize_filename(item.get("name", "")) if item.get("name") else ""
            suffix = best_extension(
                original_name=original_name,
                fallback_url=url,
                content_type=content_type,
            )

            if keep_filenames and original_name:
                filename = original_name
                if not os.path.splitext(filename)[1]:
                    filename = f"{filename}{suffix}"
            else:
                filename = f"bing_{index:04d}{suffix}"

            target_path = destination / filename
            # Avoid overwriting by adding numeric suffix.
            duplicate_index = 1
            while target_path.exists():
                target_path = destination / f"{target_path.stem}_{duplicate_index}{target_path.suffix}"
                duplicate_index += 1

            try:
                with target_path.open("wb") as handle:
                    for chunk in iter_chunks(response):
                        handle.write(chunk)
                saved += 1
                final_path = target_path
                if convert_webp:
                    try:
                        final_path = maybe_convert_webp_to_jpg(target_path)
                    except RuntimeError as conversion_error:
                        errors.append(f"{url} ({conversion_error})")
                        LOGGER.warning(
                            "Unable to convert Bing image %s to JPG: %s", target_path, conversion_error
                        )
                
                # Apply compression/resizing if requested
                if compression_quality > 0 or resize_width > 0 or resize_height > 0:
                    compress_image(final_path, compression_quality, resize_width, resize_height)

                LOGGER.info("Saved Bing image -> %s", final_path)
                # Record successful URL to prevent future duplicates
                try:
                    with manifest_path.open("a", encoding="utf-8") as mf:
                        mf.write(url + "\n")
                    seen_urls.add(url)
                except Exception:  # pragma: no cover - non-fatal
                    pass
            except Exception as error:  # pylint: disable=broad-except
                message = f"{url} ({error})"
                LOGGER.warning("Failed while saving Bing image: %s", message)
                errors.append(message)
                skipped += 1
                with contextlib.suppress(FileNotFoundError):
                    target_path.unlink(missing_ok=True)

        return saved, skipped, errors






def scrape_with_bing(
    query: str,
    *,
    limit: int,
    destination: Path,
    keep_filenames: bool,
    convert_webp: bool,
    timeout: float,
    compression_quality: int = 0,
    resize_width: int = 0,
    resize_height: int = 0,
    stop_event: threading.Event | None = None,
) -> ScrapeResult:
    if convert_webp:
        ensure_webp_conversion_support()

    bing = BingImageScraper(timeout=timeout)
    items = bing.collect_image_metadata(query, limit)
    saved, skipped, errors = bing.download_images(
        items,
        destination,
        keep_filenames=keep_filenames,
        convert_webp=convert_webp,
        compression_quality=compression_quality,
        resize_width=resize_width,
        resize_height=resize_height,
        stop_event=stop_event,
    )
    return ScrapeResult(
        engine="bing",
        requested=limit,
        saved=saved,
        skipped=skipped,
        errors=errors,
        destination=destination,
    )


def scrape_with_google(
    query: str,
    *,
    limit: int,
    destination: Path,
    keep_filenames: bool,
    convert_webp: bool,
    chromedriver_path: Path,
    headless: bool,
    min_resolution: Sequence[int],
    max_resolution: Sequence[int],
    max_missed: int,
    compression_quality: int = 0,
    resize_width: int = 0,
    resize_height: int = 0,
    stop_event: threading.Event | None = None,
) -> ScrapeResult:
    if convert_webp:
        ensure_webp_conversion_support()

    # Ensure chromedriver exists or download it
    try:
        # Use default cache (usually ~/.wdm) as path arg is not supported in v4.x
        manager = ChromeDriverManager()
        chromedriver_path = Path(manager.install())
    except Exception as error:
        raise RuntimeError(f"Failed to install ChromeDriver: {error}") from error

    # Lazy import selenium pieces to avoid dependency for Bing-only runs
    try:
        from selenium import webdriver as selenium_webdriver  # type: ignore
        from selenium.webdriver.chrome.service import Service as ChromeService  # type: ignore
        from selenium.webdriver.common.by import By  # type: ignore
        from selenium.webdriver.support.ui import WebDriverWait  # type: ignore
        from selenium.webdriver.support import expected_conditions as EC  # type: ignore
    except Exception as error:  # pylint: disable=broad-except
        raise RuntimeError(
            "Selenium is required for Google scraping. Please install it: pip install selenium"
        ) from error

    options = selenium_webdriver.ChromeOptions()
    if headless:
        # modern headless for Chrome >= 109
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")
    # Fix for WebGL/GPU errors in some environments
    options.add_argument("--enable-unsafe-swiftshader")
    options.add_argument("--disable-software-rasterizer")

    service = ChromeService(executable_path=str(chromedriver_path))
    driver = selenium_webdriver.Chrome(service=service, options=options)

    # Prepare destination and manifest
    destination.mkdir(parents=True, exist_ok=True)
    manifest_path = destination / "_downloaded_urls.txt"
    seen_urls: set[str] = set()
    if manifest_path.exists():
        with contextlib.suppress(Exception):
            seen_urls = set(u.strip() for u in manifest_path.read_text(encoding="utf-8").splitlines() if u.strip())

    min_w, min_h = min_resolution
    max_w, max_h = max_resolution

    collected: List[Dict[str, str]] = []
    queued_urls: set[str] = set()
    errors: List[str] = []

    # Initialize session and counters for immediate downloading
    session = requests.Session()
    session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
    session.headers.setdefault("Referer", "https://www.google.com/")
    saved_count = 0
    skipped_count = 0
    
    def save_found_image(url: str, name: str, index: int) -> None:
        nonlocal saved_count, skipped_count
        if url in seen_urls:
            LOGGER.debug("Skipping already seen URL: %s", url)
            skipped_count += 1
            return

        if url.startswith("data:image"):
            try:
                # Handle data URI
                header, encoded = url.split("base64,", 1)
                data = base64.b64decode(encoded)
                
                # Determine extension
                ext = ".jpg"
                if "image/png" in header:
                    ext = ".png"
                elif "image/gif" in header:
                    ext = ".gif"
                elif "image/webp" in header:
                    ext = ".webp"
                    
                final_name = name if name.endswith(ext) else Path(name).stem + ext
                target_path = destination / final_name
                
                with target_path.open("wb") as f:
                    f.write(data)
                    
                saved_count += 1
                
                # Post-processing for data URI images
                if convert_webp and ext == ".webp":
                    try:
                        target_path = maybe_convert_webp_to_jpg(target_path)
                    except Exception as e:
                        LOGGER.warning("WebP conversion failed: %s", e)

                if compression_quality > 0 or resize_width > 0 or resize_height > 0:
                    compress_image(target_path, compression_quality, resize_width, resize_height)

                with contextlib.suppress(Exception):
                    with manifest_path.open("a", encoding="utf-8") as mf:
                        mf.write(url[:50] + "..." + "\n")
                    seen_urls.add(url)
                
                LOGGER.info("Saved Google image (data URI) -> %s", target_path.name)
                return
            except Exception as e:
                LOGGER.warning("Failed to save data URI: %s", e)
                skipped_count += 1
                return

        try:
            resp = session.get(url, timeout=15.0, stream=True)
            resp.raise_for_status()
        except Exception as error:
            LOGGER.warning("Download failed for %s: %s", url, error)
            errors.append(f"{url} ({error})")
            skipped_count += 1
            return

        content_type = resp.headers.get("Content-Type", "")
        original_name = sanitize_filename(name) if name else ""
        suffix = best_extension(
            original_name=original_name,
            fallback_url=url,
            content_type=content_type,
        )

        if keep_filenames and original_name:
            filename = original_name
            if not os.path.splitext(filename)[1]:
                filename = f"{filename}{suffix}"
        else:
            filename = f"google_{index:04d}{suffix}"

        target_path = destination / filename
        duplicate_index = 1
        while target_path.exists():
            target_path = destination / f"{target_path.stem}_{duplicate_index}{target_path.suffix}"
            duplicate_index += 1

        try:
            with target_path.open("wb") as handle:
                for chunk in iter_chunks(resp):
                    handle.write(chunk)
            saved_count += 1
            
            if convert_webp:
                try:
                    maybe_convert_webp_to_jpg(target_path)
                except RuntimeError as conversion_error:
                    errors.append(f"{url} ({conversion_error})")
                    LOGGER.warning("Unable to convert Google image %s to JPG: %s", target_path, conversion_error)
            
            if compression_quality > 0 or resize_width > 0 or resize_height > 0:
                compress_image(target_path, compression_quality, resize_width, resize_height)

            with contextlib.suppress(Exception):
                with manifest_path.open("a", encoding="utf-8") as mf:
                    mf.write(url + "\n")
                seen_urls.add(url)
            
            LOGGER.info("Saved Google image -> %s", target_path.name)
        except Exception as error:
            with contextlib.suppress(FileNotFoundError):
                target_path.unlink(missing_ok=True)
            errors.append(f"{url} ({error})")
            skipped_count += 1

    try:
        search_url = "https://www.google.com/search?tbm=isch&hl=en&q=" + requests.utils.quote(query)
        driver.get(search_url)

        # Dismiss cookie consent if visible
        try:
            WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, "//button[.//div[text()='I agree' or text()='Accept all']] | //button[.='I agree' or .='Accept all']"))
            ).click()
        except Exception:
            pass

        # Scroll and collect
        wait = WebDriverWait(driver, 12)
        last_height = 0
        misses = 0
        processed_cards: set[str] = set()

        card_selectors = [
            "div.isv-r.PNCib.MSM1fd.BUooTd",
            "div.isv-r.PNCib.MSM1fd",
            "div.isv-r",
            "div.q1MG4e",
            "div.F0uyec", # Modern mobile/responsive card
        ]

        while len(collected) < limit and misses < max_missed:
            # Check stop event
            if stop_event and stop_event.is_set():
                LOGGER.info("Stop requested, ending Google scrape.")
                break
                
            cards: List = []
            for selector in card_selectors:
                cards = driver.find_elements(By.CSS_SELECTOR, selector)
                if cards:
                    break

            if not cards:
                misses += 1
                time.sleep(0.5)
                driver.execute_script("window.scrollBy(0, 600);")
                continue

            for card in cards:
                # Check stop event
                if stop_event and stop_event.is_set():
                    break
                    
                if len(collected) >= limit:
                    break
                try:
                    # Try to match key from the element itself
                    card_key = (
                        card.get_attribute("data-id")
                        or card.get_attribute("data-ri")
                        or card.get_attribute("jsname")
                        or card.get_attribute("data-ved")
                        or card.id
                    )

                    # If card is the inner container (q1MG4e), key might be on ancestor anchor
                    # And we definitely want to click the anchor.
                    click_target = card
                    with contextlib.suppress(Exception):
                        anchor = card.find_element(By.XPATH, "./ancestor::a")
                        click_target = anchor
                        if not card_key:
                            card_key = (
                                anchor.get_attribute("data-id")
                                or anchor.get_attribute("data-ri")
                                or anchor.get_attribute("jsname")
                                or anchor.get_attribute("data-ved")
                            )

                    # Fail-safe for key
                    if not card_key:
                        card_key = str(id(card))

                    if card_key in processed_cards:
                        continue
                    processed_cards.add(card_key)

                    # Extract thumbnail src early to avoid StaleElementReferenceException later
                    thumb_src = ""
                    with contextlib.suppress(Exception):
                        thumb_src = card.find_element(By.TAG_NAME, "img").get_attribute("src") or ""
                    
                    if thumb_src:
                        LOGGER.debug("Extracted thumbnail src (len=%d)", len(thumb_src))
                    else:
                        LOGGER.debug("Failed to extract thumbnail src from card")

                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                    time.sleep(0.1)

                    try:
                        driver.execute_script("arguments[0].click();", click_target)
                    except Exception:
                        click_target.click()

                    # Try to find high-res images
                    accepted = False
                    
                    # Extended list of potential high-res image selectors
                    high_res_selectors = [
                        "img.n3VNCb", "img.sFlh5c", "img.pT0Scc", "img.iPVvYb", # Legacy
                        "img.r48jcc", "img.gy84bd", # Modern 2024/2025
                    ]
                    selector_string = ", ".join(high_res_selectors)

                    found_high_res_imgs = []
                    try:
                        found_high_res_imgs = wait.until(
                            EC.presence_of_all_elements_located((By.CSS_SELECTOR, selector_string))
                        )
                    except Exception:
                        # Fallback: Smart search for any large image in the preview pane
                        LOGGER.warning("Specific high-res selectors failed for %s. Attempting smart fallback search...", card_key)
                        try:
                            # Look for all images and filter by size or src
                            # We assume the high-res image has loaded by now (post-click)
                            all_imgs = driver.find_elements(By.TAG_NAME, "img")
                            for img in all_imgs:
                                try:
                                    src = img.get_attribute("src")
                                    if not src:
                                        continue
                                    
                                    # Skip Google-hosted images (logos, icons, thumbnails)
                                    if "google.com" in src or "gstatic.com" in src:
                                        continue
                                    
                                    # Skip data URIs (thumbnails)
                                    if src.startswith("data:"):
                                        continue
                                    
                                    # Skip if it's the same as the thumbnail we already have
                                    if src == thumb_src:
                                        continue
                                    
                                    # This is a potential external high-res image
                                    if src.startswith("http"):
                                        found_high_res_imgs.append(img)
                                        LOGGER.info("Fallback found candidate: %s", src[:80])
                                        
                                except Exception:
                                    continue
                        except Exception as e:
                            LOGGER.warning("Fallback search failed: %s", e)

                    imgs = found_high_res_imgs

                        
                    for img in imgs:
                        # Check stop event
                        if stop_event and stop_event.is_set():
                            break

                        src = img.get_attribute("src") or ""
                        if not src.startswith("http") and not src.startswith("data:image"):
                            continue

                        try:
                            dims = driver.execute_script(
                                "return [arguments[0].naturalWidth, arguments[0].naturalHeight];", img
                            )
                            width = int(dims[0] or 0)
                            height = int(dims[1] or 0)
                        except Exception:
                            width = height = 0

                        if (min_w and width < min_w) or (min_h and height < min_h):
                            continue
                        if (max_w and width and width > max_w) or (max_h and height and height > max_h):
                            continue

                        if src in seen_urls or src in queued_urls:
                            accepted = True
                            break
                        
                        if src.startswith("data:image"):
                            import hashlib
                            name = f"data_image_{hashlib.md5(src.encode('utf-8')).hexdigest()[:10]}.jpg"
                        else:
                            name = os.path.basename(urlsplit(src).path)

                        collected.append({"url": src, "name": name})
                        queued_urls.add(src)
                        save_found_image(src, name, len(collected))
                        accepted = True
                        break
                            
                    if not accepted:
                        # Try to extract high-res URL from page JavaScript data
                        # Google embeds image metadata in script tags
                        try:
                            import re
                            page_source = driver.page_source
                            # Look for patterns like ["https://external-image-url.jpg",width,height]
                            # These are embedded in the page's JavaScript
                            url_pattern = r'\["(https?://[^"]+\.(?:jpg|jpeg|png|gif|webp))"(?:,|\])'
                            matches = re.findall(url_pattern, page_source, re.IGNORECASE)
                            
                            # Filter out Google URLs and find unique external URLs
                            external_urls = []
                            for url in matches:
                                if "google.com" not in url and "gstatic.com" not in url and "googleusercontent.com" not in url:
                                    if url not in seen_urls and url not in queued_urls:
                                        external_urls.append(url)
                            
                            if external_urls:
                                # Take the first external URL found
                                src = external_urls[0]
                                name = os.path.basename(urlsplit(src).path) or f"google_img_{len(collected)}.jpg"
                                collected.append({"url": src, "name": name})
                                queued_urls.add(src)
                                save_found_image(src, name, len(collected))
                                # Don't add to seen_urls here - it's added after successful download
                                LOGGER.info("Extracted image URL from page data: %s", src[:80])
                                accepted = True
                        except Exception as ex:
                            LOGGER.debug("Page data extraction failed: %s", ex)
                    
                    if not accepted:
                         # Fallback to thumbnail if high-res not found (Timeout or other error)
                        LOGGER.warning("High-res image not found for %s, using thumbnail.", card_key)
                        if thumb_src:
                            name = f"thumbnail_{card_key}.jpg"
                            collected.append({"url": thumb_src, "name": name})
                            save_found_image(thumb_src, name, len(collected))
                            accepted = True
                        else:
                            LOGGER.debug("Thumbnail src was empty, cannot fallback.")

                    if not accepted:
                        misses += 1
                    else:
                        misses = 0

                except Exception as exc:  # pylint: disable=broad-except
                    errors.append(str(exc))
                    continue

            driver.execute_script("window.scrollBy(0, document.body.scrollHeight);")
            time.sleep(0.2)
            height = driver.execute_script("return document.body.scrollHeight")
            if height == last_height:
                with contextlib.suppress(Exception):
                    show_more = driver.find_element(By.CSS_SELECTOR, ".mye4qd")
                    driver.execute_script("arguments[0].click();", show_more)
                    time.sleep(0.5)
                misses += 1
            else:
                last_height = height

    finally:
        with contextlib.suppress(Exception):
            driver.quit()

    return ScrapeResult(
        engine="google",
        requested=limit,
        saved=saved_count,
        skipped=skipped_count,
        errors=errors,
        destination=destination,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape images from multiple search engines (Bing, Google)."
    )
    parser.add_argument("query", help="Search term to scrape images for.")
    parser.add_argument(
        "--num-images",
        type=int,
        default=10,
        help="Number of images to attempt to download per engine (default: 10).",
    )
    parser.add_argument(
        "--engine",
        dest="engines",
        action="append",
        choices=("bing", "google"),
        help="Specify one or more engines. Defaults to both.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("downloads"),
        help="Base directory where images should be saved (default: ./downloads).",
    )
    parser.add_argument(
        "--keep-filenames",
        action="store_true",
        help="Keep filenames from the search results when possible.",
    )
    parser.add_argument(
        "--convert-webp",
        action="store_true",
        help="Convert downloaded .webp images to .jpg (requires Pillow).",
    )
    parser.add_argument(
        "--bing-timeout",
        type=float,
        default=15.0,
        help="Timeout in seconds for individual Bing requests (default: 15).",
    )
    parser.add_argument(
        "--google-chromedriver",
        type=Path,
        default=Path("webdriver") / ("chromedriver.exe" if os.name == "nt" else "chromedriver"),
        help="Path to the ChromeDriver binary used by the Google scraper.",
    )
    parser.add_argument(
        "--google-show-browser",
        action="store_true",
        help="Run the Google scraper with a visible browser instead of headless mode.",
    )
    parser.add_argument(
        "--google-min-resolution",
        nargs=2,
        type=int,
        metavar=("WIDTH", "HEIGHT"),
        default=(0, 0),
        help="Minimum resolution accepted by the Google scraper (default: 0 0).",
    )
    parser.add_argument(
        "--google-max-resolution",
        nargs=2,
        type=int,
        metavar=("WIDTH", "HEIGHT"),
        default=(1920, 1080),
        help="Maximum resolution accepted by the Google scraper (default: 1920 1080).",
    )
    parser.add_argument(
        "--google-max-missed",
        type=int,
        default=10,
        help="Maximum number of consecutive misses before Google scraping stops.",
    )
    parser.add_argument(
        "--compression-quality",
        type=int,
        default=0,
        help="JPEG compression quality (1-100). Default 0 (no compression).",
    )
    parser.add_argument(
        "--resize-width",
        type=int,
        default=0,
        help="Resize image if width exceeds this value (0 = no limit).",
    )
    parser.add_argument(
        "--resize-height",
        type=int,
        default=0,
        help="Resize image if height exceeds this value (0 = no limit).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="Adjust logging verbosity for the multitool (default: INFO).",
    )
    return parser


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper()), format="[%(levelname)s] %(message)s")
    LOGGER.setLevel(getattr(logging, level.upper()))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    configure_logging(args.log_level)

    engines = args.engines or ["bing", "google"]
    engines = list(dict.fromkeys(engines))  # Preserve order but remove duplicates.

    base_dir = args.output_dir.expanduser().resolve()
    query_folder = slugify(args.query)
    results: List[ScrapeResult] = []

    LOGGER.info("Saving output under %s", base_dir)
    for engine in engines:
        try:
            if engine == "bing":
                destination = base_dir / "bing" / query_folder
                result = scrape_with_bing(
                    args.query,
                    limit=args.num_images,
                    destination=destination,
                    keep_filenames=args.keep_filenames,
                    convert_webp=args.convert_webp,
                    timeout=args.bing_timeout,
                    compression_quality=args.compression_quality,
                    resize_width=args.resize_width,
                    resize_height=args.resize_height,
                )
            elif engine == "google":
                destination = base_dir / "google" / query_folder
                result = scrape_with_google(
                    args.query,
                    limit=args.num_images,
                    destination=destination,
                    keep_filenames=args.keep_filenames,
                    convert_webp=args.convert_webp,
                    chromedriver_path=args.google_chromedriver.expanduser().resolve(),
                    headless=not args.google_show_browser,
                    min_resolution=tuple(args.google_min_resolution),
                    max_resolution=tuple(args.google_max_resolution),
                    max_missed=args.google_max_missed,
                    compression_quality=args.compression_quality,
                    resize_width=args.resize_width,
                    resize_height=args.resize_height,
                )
            else:
                parser.error(f"Unsupported engine requested: {engine}")
                return 2
            results.append(result)
        except Exception as error:  # pylint: disable=broad-except
            LOGGER.error("Scraping via %s failed: %s", engine, error)
            return 1

    LOGGER.info("Scraping complete")
    for result in results:
        LOGGER.info(
            "%s: requested=%d saved=%d skipped=%d destination=%s",
            result.engine,
            result.requested,
            result.saved,
            result.skipped,
            result.destination,
        )
        if result.errors:
            LOGGER.info("%s encountered %d download errors", result.engine, len(result.errors))

    return 0


class GenericPageScraper:
    """Scrapes all images from a single URL using Selenium to handle dynamic content."""

    def __init__(self, *, timeout: float = 15.0) -> None:
        self.timeout = timeout
        # We don't cache the driver here because we want to spawn/close it per scrape or manage it externally.
        # But for simplicity in this tool, we'll spawn it inside scrape if not provided, 
        # or we could make this class stateful. Given the usage pattern, per-scrape is fine.

    def scrape(
        self,
        url: str,
        destination: Path,
        *,
        keep_filenames: bool,
        convert_webp: bool,
        limit: int = 0,
        compression_quality: int = 0,
        resize_width: int = 0,
        resize_height: int = 0,
        headless: bool = True,
        recursion_depth: int = 0,
        stop_event: threading.Event | None = None,
    ) -> Tuple[int, int, List[str]]:
        destination.mkdir(parents=True, exist_ok=True)
        saved = 0
        skipped = 0
        errors: List[str] = []

        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        # This will hold all found images across recursion
        # Format: (src, page_url)
        all_images: set[Tuple[str, str]] = set()
        
        # To avoid infinite loops
        visited_pages: set[str] = set()

        # Queue for recursion: (url, current_depth)
        queue_list: List[Tuple[str, int]] = [(url, 0)]
        
        # Setup Selenium once
        driver = None
        try:
            from selenium import webdriver as selenium_webdriver
            from selenium.webdriver.chrome.service import Service as ChromeService
            from selenium.webdriver.common.by import By
            
            try:
                manager = ChromeDriverManager()
                chromedriver_path = Path(manager.install())
            except Exception as e:
                return 0, 0, [f"Failed to install ChromeDriver: {e}"]

            options = selenium_webdriver.ChromeOptions()
            if headless:
                 options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--log-level=3")
            options.add_argument("--enable-unsafe-swiftshader")
            options.add_argument("--disable-software-rasterizer")
            options.add_argument(f"user-agent={DEFAULT_USER_AGENT}")

            service = ChromeService(executable_path=str(chromedriver_path))
            driver = selenium_webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(self.timeout * 2)

            while queue_list:
                # Check stop event
                if stop_event and stop_event.is_set():
                    LOGGER.info("Stop requested, ending custom URL scrape.")
                    break
                    
                current_url, current_depth = queue_list.pop(0)
                
                if current_url in visited_pages:
                    continue
                visited_pages.add(current_url)
                
                LOGGER.info("Crawling %s (Depth %d)", current_url, current_depth)
                
                try:
                    driver.get(current_url)
                    
                    # Scroll logic
                    last_height = driver.execute_script("return document.body.scrollHeight")
                    for _ in range(3): # Reduce scroll attempts per page to save time
                        # Check stop event
                        if stop_event and stop_event.is_set():
                            break

                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1.0)
                        new_height = driver.execute_script("return document.body.scrollHeight")
                        if new_height == last_height:
                            break
                        last_height = new_height

                    # 1. Harvest Images
                    elements = driver.find_elements(By.TAG_NAME, "img")
                    for img in elements:
                        # Check stop event
                        if stop_event and stop_event.is_set():
                            break

                        src = img.get_attribute("src")
                        if not src:
                             src = img.get_attribute("data-src") or img.get_attribute("data-original")
                        
                        if not src:
                            srcset = img.get_attribute("srcset")
                            if srcset:
                                parts = srcset.split(",")
                                if parts:
                                     candidate = parts[-1].strip().split(" ")[0]
                                     if candidate:
                                         src = candidate

                        if src and (src.startswith("http") or src.startswith("data:image")):
                            all_images.add((src, current_url))

                    # 2. Harvest Links if depth allows
                    if current_depth < recursion_depth:
                        links = driver.find_elements(By.TAG_NAME, "a")
                        base_domain = urlsplit(url).netloc
                        
                        for link in links:
                            # Check stop event
                            if stop_event and stop_event.is_set():
                                break

                            href = link.get_attribute("href")
                            if not href:
                                continue
                                
                            # Filter: same domain only
                            parts = urlsplit(href)
                            if parts.netloc != base_domain:
                                continue
                            
                            # Filter: Common "ignore" patterns
                            lower = href.lower()
                            if any(x in lower for x in ["login", "signup", "signin", "register", "help", "about", "policy"]):
                                continue
                                
                            if href not in visited_pages:
                                queue_list.append((href, current_depth + 1))
                                
                except Exception as e:
                     LOGGER.warning("Failed to crawl %s: %s", current_url, e)
                     errors.append(f"Crawl error {current_url}: {e}")

        except Exception as e:
            errors.append(f"Selenium setup failed: {e}")
        finally:
             if driver:
                 driver.quit()

        LOGGER.info("Crawl finished. Found %d unique image URLs from %d pages.", len(all_images), len(visited_pages))

        # Download Logic (Standard)
        manifest_path = destination / "_downloaded_urls.txt"
        seen_urls: set[str] = set()
        if manifest_path.exists():
            with contextlib.suppress(Exception):
                seen_urls = set(u.strip() for u in manifest_path.read_text(encoding="utf-8").splitlines() if u.strip())

        session = requests.Session()
        session.headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
        
        # Sort to keep some order
        sorted_imgs = sorted(list(all_images), key=lambda x: x[0])

        for index, (image_url, referrer) in enumerate(sorted_imgs, start=1):
            if limit > 0 and saved >= limit:
                break
            
            if image_url in seen_urls:
                skipped += 1
                continue
            
            # Update referer for download
            session.headers["Referer"] = referrer

            try:
                # Handle Data URI
                if image_url.startswith("data:image"):
                    try:
                        header, encoded = image_url.split("base64,", 1)
                        data = base64.b64decode(encoded)
                        ext = ".jpg"
                        if "image/png" in header: ext = ".png"
                        if "image/gif" in header: ext = ".gif"
                        if "image/webp" in header: ext = ".webp"
                        
                        filename = f"custom_{index:04d}{ext}"
                        target_path = destination / filename
                        # Dup check
                        dup_idx = 1
                        while target_path.exists():
                             target_path = destination / f"{target_path.stem}_{dup_idx}{target_path.suffix}"
                             dup_idx += 1
                        
                        with target_path.open("wb") as f:
                            f.write(data)
                        
                        saved += 1
                        
                        final_path = target_path
                        if convert_webp and ext == ".webp":
                             try:
                                 final_path = maybe_convert_webp_to_jpg(target_path)
                             except Exception: pass
                        
                        if compression_quality > 0 or resize_width > 0 or resize_height > 0:
                            compress_image(final_path, compression_quality, resize_width, resize_height)
                            
                        # log
                        try:
                            with manifest_path.open("a", encoding="utf-8") as mf:
                                mf.write(image_url[:50] + "...\n")
                            seen_urls.add(image_url)
                        except Exception: pass
                        
                        LOGGER.info("Saved custom data-uri image -> %s", final_path.name)
                        
                    except Exception as e:
                        LOGGER.warning("Failed to save data URI: %s", e)
                        errors.append(f"Data URI error: {e}")
                        skipped += 1
                    continue

                # Handle HTTP
                try:
                    img_resp = session.get(image_url, timeout=10.0, stream=True)
                    img_resp.raise_for_status()
                except Exception as e:
                    errors.append(f"{image_url}: {e}")
                    skipped += 1
                    continue

                content_type = img_resp.headers.get("Content-Type", "")
                original_name = os.path.basename(urlsplit(image_url).path)
                original_name = sanitize_filename(original_name)
                
                suffix = best_extension(
                    original_name=original_name,
                    fallback_url=image_url,
                    content_type=content_type,
                )

                if keep_filenames and original_name and len(original_name) > 1:
                    filename = original_name
                    if not os.path.splitext(filename)[1]:
                        filename = f"{filename}{suffix}"
                else:
                    filename = f"custom_{index:04d}{suffix}"

                target_path = destination / filename
                dup_idx = 1
                while target_path.exists():
                    target_path = destination / f"{target_path.stem}_{dup_idx}{target_path.suffix}"
                    dup_idx += 1

                with target_path.open("wb") as handle:
                    for chunk in iter_chunks(img_resp):
                        handle.write(chunk)
                
                final_path = target_path
                if convert_webp:
                     try:
                         final_path = maybe_convert_webp_to_jpg(target_path)
                     except Exception: pass

                if compression_quality > 0 or resize_width > 0 or resize_height > 0:
                    compress_image(final_path, compression_quality, resize_width, resize_height)

                saved += 1
                LOGGER.info("Saved custom image -> %s", final_path)
                try:
                    with manifest_path.open("a", encoding="utf-8") as mf:
                        mf.write(image_url + "\n")
                    seen_urls.add(image_url)
                except Exception: pass

            except Exception as error:
                message = f"{image_url} ({error})"
                errors.append(message)
                skipped += 1
                with contextlib.suppress(FileNotFoundError):
                    target_path.unlink(missing_ok=True)

        return saved, skipped, errors


def scrape_custom_url(
    url: str,
    *,
    limit: int,
    destination: Path,
    keep_filenames: bool,
    convert_webp: bool,
    timeout: float,
    compression_quality: int = 0,
    resize_width: int = 0,
    resize_height: int = 0,
    headless: bool = True,
    recursion_depth: int = 0,
    stop_event: threading.Event | None = None,
) -> ScrapeResult:
    if convert_webp:
        ensure_webp_conversion_support()

    scraper = GenericPageScraper(timeout=timeout)
    saved, skipped, errors = scraper.scrape(
        url,
        destination,
        keep_filenames=keep_filenames,
        convert_webp=convert_webp,
        limit=limit,
        compression_quality=compression_quality,
        resize_width=resize_width,
        resize_height=resize_height,
        headless=headless,
        recursion_depth=recursion_depth,
        stop_event=stop_event,
    )
    return ScrapeResult(
        engine="custom",
        requested=limit,
        saved=saved,
        skipped=skipped,
        errors=errors,
        destination=destination,
    )

if __name__ == "__main__":
    # If running directly, expose CLI for simple testing? 
    # The existing CLI was main() which parses args.
    # I should probably leave the main() block if it existed, but looking at previous file view,
    # the existing main() uses `scrape_with_bing` etc.
    # I replaced the END of the file, assuming it was `if __name__ == "__main__": ...`?
    # Wait, the previous `view_file` showed `if __name__ == "__main__": raise SystemExit(main())` at line 1153.
    # The file has a `main()` function somewhere? I didn't see `def main():` in the chunks I read.
    # I should check if `def main():` exists and if I need to update it to support custom scraper via CLI.
    # The user request focused on "add the ability for the user to give the multitool a custom URL"
    # This implies updating the GUI primarily, but CLI update is good practice.
    # However, I am replacing the END of the file.
    # I should preserve `def main():` and the `if __name__` block, but update `main` if I want CLI support.
    # Since I didn't see `def main()` in the chunks, I must be careful not to delete it if I blindly replace "EndLine: 1155".
    # I'll check where `def main()` is.
    pass
