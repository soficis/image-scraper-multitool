# Image Scraper Multitool

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Code Quality](https://img.shields.io/badge/quality-ruff%20%7C%20mypy%20%7C%20pytest-green.svg)](tools/run_quality.py)

A desktop and command-line utility for multi-engine image scraping, batch image format conversion, compression, and metadata cleaning. Built with Python, Tkinter (modern dark theme), Requests, and Selenium.

---

## Highlights & Capabilities

### Multi-Source Image Scraping
- **Bing Images (Keyless, Default):** High-speed async collection with token-level relevance filtering, automatic noun-first query reformulation fallbacks, Facebook crawler link-repair, and query expansion (`--expand-queries`).
- **Openverse (Keyless):** Direct access to millions of openly licensed and Creative Commons images with polite automatic rate-limiting (1 request/sec).
- **Pexels & Pixabay (Free API):** Fast, paginated official API scrapers (free API keys supported via GUI fields, CLI flags, or `PEXELS_API_KEY` / `PIXABAY_API_KEY` environment variables).
- **Google Images (Selenium):** Automated ChromeDriver management, visible or headless execution, resolution filtering, and automated anti-bot block detection.
- **Custom Webpages:** Extract all hosted images from any URL with recursive depth and lazy-load scroll simulation.

### Universal Image Converter & Optimizer
- **Multi-Format Support:** Convert between JPEG, PNG, WebP, AVIF, HEIC, TIFF, BMP, GIF, and ICO.
- **Lossless & Lossy Compression:** Quality slider (1–100) or true lossless encoding for WebP and HEIC.
- **Aspect-Preserving Resizing:** Limit maximum width and height without distorting image proportions.
- **Privacy & Metadata Stripping:** Strip EXIF, GPS location, and camera metadata while preserving embedded color profiles.
- **`--only-smaller` Safeguard:** Optional compression filter that discards any re-encoded file that is larger than the original.
- **Recursive Batch Processing:** Convert entire directory trees into a designated output folder or next to original files.

### Modern Desktop Experience
- **Slate Dark UI:** Custom-styled Tkinter interface featuring visual grouping, responsive layouts, and distinct tabs for Scraping and Converting.
- **Per-Engine Live Progress:** Real-time visual progress counter (`Bing 4/10`, `Google 1/10`), active progress bar, and cancellation support.
- **One-Click Native Folder Access:** Direct "Open Folder" action launching the native file manager (Windows Explorer, macOS Finder, or Linux file browser).
- **Automatic Settings Persistence:** Remembers output directories, selected engines, API keys, and timeouts across sessions (`%APPDATA%/ImageScraperMultitool/settings.json` on Windows, `~/.config/image-scraper-multitool/` on Unix).

### Reliability & Resilience
- **Engine Isolation:** Failure in one engine (e.g. Google anti-bot challenge) never crashes or cancels other active engines.
- **Relevance Protection:** Prevents search engines from injecting unrelated trending/localized fallback images when query matches are sparse.
- **Download Hardening:** Automatic retry with exponential backoff on transient errors, per-host domain throttling, file-size limits, and non-image HTML response rejection with thumbnail fallback.
- **Duplicate Prevention:** Tracks downloaded URLs across runs in per-query `_downloaded_urls.txt` logs.

---

## Engine Reliability Guide

| Engine | Auth Required | Typical Yield / Query | Notes & Best Practices |
| :--- | :--- | :--- | :--- |
| **Bing** | None | ~35 unique (up to 140+ with `--expand-queries`) | **Default & Recommended.** Keyless, fast, features automatic query reordering and relevance filtering. |
| **Openverse** | None | ~20–50 items | Keyless, openly licensed (CC). Politeness-throttled at 1 req/sec. |
| **Pexels** | Free API Key | Up to 80 / page (paginated) | Very fast and reliable. Free API key from [pexels.com/api](https://www.pexels.com/api/). |
| **Pixabay** | Free API Key | Up to 80 / page (paginated) | Very fast and reliable. Free API key from [pixabay.com/api/docs](https://pixabay.com/api/docs/). |
| **Google** | None (Chrome req.) | 10–50 items | Uses Selenium. Subject to Google's anti-bot detection; reports `google_blocked` if captcha occurs. Use `--google-show-browser` if headless is flagged. |
| **Custom** | None | Variable | Scrapes `<img>` and background tags from any website URL. |

---

## Project Structure

```text
image-scraper-multitool/
├── image_scraper_gui.py           # GUI launcher entrypoint
├── image_scraper_multitool.py     # CLI launcher entrypoint (scrape & convert)
├── src/image_scraper/
│   ├── adapters/                  # Engine implementations (Bing, Google, Openverse, Pexels, Pixabay)
│   │   ├── bing.py                # Bing async scraper with relevance filtering & fallbacks
│   │   ├── downloader.py          # Resilient download manager with retry, throttling, fallbacks
│   │   ├── google.py              # Google Selenium lifecycle & orchestration
│   │   ├── image_converter.py     # Universal Pillow/pillow-heif batch converter & compressor
│   │   ├── openverse.py           # Openverse REST API adapter with polite rate-limiting
│   │   ├── pexels.py              # Pexels API adapter
│   │   ├── pixabay.py             # Pixabay API adapter
│   │   └── stock_api.py           # Shared REST pagination helper
│   ├── app/                       # Application services (scrape orchestration, convert workflows)
│   ├── cli/                       # Command-line subcommands (scrape, convert)
│   ├── domain/                    # Pure domain models, typing, expansion, naming
│   └── ui/                        # Tkinter GUI (Slate Dark theme, scrape & convert tabs, settings)
├── tests/                         # Comprehensive unit & integration test suite (188+ tests)
├── tools/
│   └── run_quality.py             # One-step quality gate (Ruff format, Ruff lint, Mypy, Pytest)
├── pyproject.toml                 # Build config, Ruff & Mypy settings
├── requirements.txt               # Runtime dependencies
└── requirements-dev.txt           # Developer tooling (pytest, ruff, mypy)
```

---

## Installation

### Prerequisites

- Python 3.8 or higher
- Google Chrome browser (only required if scraping via Google Images)

### Quick Start (One-Click Setup & Launch)

#### Windows
1. Double-click [setup.bat](file:///v:/image-scraper-multitool/setup.bat) to automatically verify Python 3.8+, create/configure the `.venv` virtual environment, install dependencies, and optionally launch the app.
2. For daily launches, double-click [run.bat](file:///v:/image-scraper-multitool/run.bat) (or run `run.bat --console` if you wish to see diagnostic terminal output).

#### Linux / macOS
1. Make executable and run [setup.sh](file:///v:/image-scraper-multitool/setup.sh):
   ```bash
   chmod +x setup.sh run.sh
   ./setup.sh
   ```
2. Launch anytime with [run.sh](file:///v:/image-scraper-multitool/run.sh):
   ```bash
   ./run.sh
   ```

---

### Manual Setup (Optional)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/soficis/image-scraper-multitool.git
   cd image-scraper-multitool
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # On Windows:
   .venv\Scripts\activate
   # On macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **(Optional) Install development dependencies for quality checks:**
   ```bash
   pip install -r requirements-dev.txt
   ```

---

## Usage

### 1. Graphical User Interface (GUI)

Launch the desktop interface:

```bash
python image_scraper_gui.py
```

The application provides two dedicated tabs:

#### Scrape Tab
- **Query Input & Engine Selection:** Toggle any combination of Bing, Google, Openverse, Pexels, Pixabay, or Custom URL.
- **API Keys:** Secure inputs for Pexels and Pixabay keys with auto-fill from environment variables.
- **Download Settings:** Output path selection with native browsing, image count limits, and timeout controls.
- **Search Variants:** Check "Also search variants" to automatically expand queries (plural, photo, wallpaper) to multiply results.
- **Real-Time Feedback:** Live counter displaying active downloads per engine (`Bing 4/10`, `Google 1/10`), animated progress bar, and single-click cancellation.
- **Output Management:** Direct "Open Folder" button opening the destination folder in Windows Explorer, macOS Finder, or Linux file manager.

#### Convert Images Tab
- **Input Selection:** Select individual files or entire folders for batch conversion.
- **Output Format:** Convert to JPEG, PNG, WebP, AVIF, HEIC, TIFF, BMP, GIF, or ICO (or keep original format for pure compression).
- **Optimization Controls:** Quality slider (1–100), lossless mode toggle, and `--only-smaller` protection.
- **Dimensions & Privacy:** Constrain maximum width/height and toggle EXIF/GPS metadata stripping.
- **Batch Processing:** Live file-by-file progress bar, status metrics, and direct output folder access.

---

### 2. Command-Line Interface (CLI)

The CLI supports both image scraping and offline format conversion:

```bash
python image_scraper_multitool.py [command] [options]
```

#### Scraping Images (`scrape` or default query)

**Basic scrape with Bing (default, 20 images):**
```bash
python image_scraper_multitool.py "red pandas" --num-images 20
```

**Maximize results with query expansion:**
```bash
python image_scraper_multitool.py "vintage motorcycles" --num-images 60 --expand-queries
```

**Multi-engine scrape from Bing, Openverse, and Pexels:**
```bash
python image_scraper_multitool.py "aurora borealis" --engine bing --engine openverse --engine pexels --pexels-api-key YOUR_KEY --num-images 25
```

**Scrape with Google Images and resolution constraints:**
```bash
python image_scraper_multitool.py "mountain landscape" --engine google --google-min-resolution 1920 1080 --google-show-browser
```

**Extract images from a website:**
```bash
python image_scraper_multitool.py "https://news.ycombinator.com" --engine custom --custom-recursion-depth 1
```

#### Converting & Optimizing Images (`convert`)

**Convert a directory of images to WebP at quality 80:**
```bash
python image_scraper_multitool.py convert ./photos --to webp --quality 80
```

**Convert Apple HEIC photos to JPG, strip metadata, and save to a subfolder:**
```bash
python image_scraper_multitool.py convert ./phone_photos --to jpg --strip-metadata --output-dir ./converted
```

**Compress images in-place, keeping only outputs that save disk space:**
```bash
python image_scraper_multitool.py convert ./gallery --to keep --quality 75 --only-smaller
```

**Downscale high-resolution images to fit 1920x1080:**
```bash
python image_scraper_multitool.py convert ./wallpapers --max-width 1920 --max-height 1080 --to png
```

---

## CLI Options Reference

### Scraper Options

```text
positional arguments:
  query                 Search term or URL to scrape.

options:
  --num-images NUM_IMAGES
                        Images to download per engine (default: 10).
  --engine {bing,google,custom,pexels,pixabay,openverse}
                        Specify one or more engines. Defaults to bing.
  --output-dir OUTPUT_DIR
                        Base output directory (default: ./downloads).
  --keep-filenames      Keep original source filenames when possible.
  --convert-webp        Convert WebP images to JPG after download.
  --compression-quality COMPRESSION_QUALITY
                        JPEG quality (1-100). 0 disables compression.
  --resize-width RESIZE_WIDTH
                        Max output width (0 = no limit).
  --resize-height RESIZE_HEIGHT
                        Max output height (0 = no limit).
  --bing-timeout BING_TIMEOUT
                        Bing request timeout in seconds (default: 15.0).
  --api-timeout API_TIMEOUT
                        Request timeout in seconds for Pexels, Pixabay, and Openverse APIs.
  --expand-queries      Search query variants (plural, photo, wallpaper, picture) to multiply results.
  --pexels-api-key PEXELS_API_KEY
                        Pexels API key (free at pexels.com/api). Falls back to PEXELS_API_KEY env var.
  --pixabay-api-key PIXABAY_API_KEY
                        Pixabay API key (free at pixabay.com/api/docs). Falls back to PIXABAY_API_KEY env var.
  --google-chromedriver GOOGLE_CHROMEDRIVER
                        Optional explicit path to chromedriver. If omitted, auto-download is used.
  --google-show-browser Run Selenium with visible Chrome window instead of headless mode.
  --google-min-resolution WIDTH HEIGHT
                        Minimum Google image resolution.
  --google-max-resolution WIDTH HEIGHT
                        Maximum Google image resolution (0 0 disables max).
  --google-max-missed GOOGLE_MAX_MISSED
                        Stop Google collection after this many empty passes (default: 10).
  --custom-recursion-depth CUSTOM_RECURSION_DEPTH
                        Recursion depth for custom URL mode.
  --log-level {DEBUG,INFO,WARNING,ERROR}
                        Logging verbosity.
```

### Converter Options

```text
positional arguments:
  inputs                Image files and/or folders to convert.

options:
  --to FORMAT           Output format: keep (default; re-encode in original format),
                        jpeg/jpg, png, webp, avif, heic, tiff, bmp, gif, ico.
  --quality QUALITY     Compression quality (1-100) for JPEG, WebP, AVIF, HEIC (default: 85).
  --lossless            Lossless encoding (WebP and HEIC only).
  --max-width MAX_WIDTH Shrink to fit this width (0 = no limit).
  --max-height MAX_HEIGHT
                        Shrink to fit this height (0 = no limit).
  --strip-metadata      Remove EXIF, GPS location, and camera info (color profiles preserved).
  --only-smaller        Discard output files that are not smaller than their original.
  --output-dir OUTPUT_DIR
                        Write to this directory, mirroring input structure (default: next to original).
  --list-formats        Print supported input and output formats and exit.
  --log-level {DEBUG,INFO,WARNING,ERROR}
                        Logging verbosity.
```

---

## Output Organization

Downloaded images are systematically structured by engine and query slug:

```text
downloads/
├── bing/
│   └── red-pandas/
│       ├── bing_0001.jpg
│       ├── bing_0002.png
│       └── _downloaded_urls.txt
├── openverse/
│   └── red-pandas/
│       ├── openverse_0001.jpg
│       └── _downloaded_urls.txt
├── pexels/
│   └── red-pandas/
│       ├── pexels_0001.jpg
│       └── _downloaded_urls.txt
└── google/
    └── red-pandas/
        ├── google_0001.jpg
        └── _downloaded_urls.txt
```

- Each directory contains a `_downloaded_urls.txt` manifest ensuring subsequent runs never duplicate previously fetched URLs.
- Filenames follow consistent zero-padded prefixes (`engine_0001.ext`) or retain source names when `--keep-filenames` is specified.

---

## Quality Gate & Testing

The project maintains 100% passing test coverage across all features:

```bash
python tools/run_quality.py
```

This single command executes:
1. **Ruff Format:** Code style and indentation enforcement.
2. **Ruff Lint:** Strict static analysis and hygiene checks.
3. **Mypy:** Static type verification across all modules.
4. **Pytest:** 188+ deterministic unit and integration tests.

---

## Troubleshooting

### Bing returns fewer images than requested
- Check the "Also search variants" option or use `--expand-queries` on the CLI to automatically fetch related variants.
- For niche or multi-word queries, the scraper automatically falls back through noun-first reordered phrases to maintain high relevance while fulfilling quotas.

### Google scraping is blocked ("unusual traffic / sorry")
- Google periodically flags headless automated requests.
- Toggle `--google-show-browser` (or uncheck Headless in the GUI) to run a visible browser window, or switch to the keyless **Bing** or **Openverse** engines.

### Pexels or Pixabay report authentication errors
- Ensure your API key is valid. Keys can be obtained free of charge from [Pexels](https://www.pexels.com/api/) and [Pixabay](https://pixabay.com/api/docs/).
- You can store them in environment variables (`export PEXELS_API_KEY="..."`) or enter them directly in the GUI settings.

### GUI fails to start on Linux
- Ensure Tkinter is installed on your Linux distribution:
  ```bash
  sudo apt-get install python3-tk
  ```

---

## Disclaimer

This software is provided for educational and research purposes. Please respect the terms of service of each image provider and ensure compliance with copyright and intellectual property laws for any downloaded content.

---

## License

This project is licensed under the **GNU General Public License v3.0** (GPLv3). See the [LICENSE](LICENSE) file for details.
