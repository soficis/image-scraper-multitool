# Image Scraper Multitool

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

A comprehensive tool for scraping images from Bing and Google Images with both a modern graphical user interface (GUI) and command-line interface (CLI). This project provides an easy-to-use solution for collecting images from multiple search engines while handling duplicates, file naming, and various configuration options.

> [!NOTE]
> **Scraping Reliability**: While the Bing scraper relies on a stable legacy API and is highly reliable, the Google Images scraper uses browser automation (Selenium) which can be affected by Google's anti-bot measures and DOM changes. It is functional but may not be 100% reliable compared to the Bing scraper.

## Features

- **Multi-Engine Support**: Scrape images from Bing, Google Images, or custom URLs
- **Graphical Interface**: Modern, dark-themed Tkinter GUI for easy operation
- **Command-Line Tool**: Full CLI support for automation and scripting
- **Duplicate Prevention**: Automatic tracking of downloaded URLs to avoid duplicates
- **Flexible Naming**: Option to keep original filenames or use numbered sequences
- **Resolution Filtering**: Set minimum and maximum image resolutions
- **WebP Conversion**: Automatically convert WebP images to JPG
- **Image Compression**: Optional quality reduction and resizing for smaller files
- **Custom URL Scraping**: Extract all images from any webpage with lazy-load support
- **Auto-Driver Download**: Automatically downloads compatible ChromeDriver
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Organized Output**: Images are saved in structured directories by engine and query

## Project Structure

- `image_scraper_gui.py` — Modern Tkinter GUI application
- `image_scraper_multitool.py` — Command-line interface and core scraping logic
- `webdriver/` — Local storage for ChromeDriver binaries
- `downloads/` — Default output directory with organized subfolders
- `requirements.txt` — Python dependencies

## Installation

### Prerequisites

- Python 3.8 or higher
- Google Chrome browser (for Google Images scraping)

### Setup

1. Clone the repository:

   ```bash
   git clone https://github.com/soficis/image-scraper-multitool.git
   cd image-scraper-multitool
   ```

2. Create a virtual environment (recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Usage

### Graphical Interface (Recommended)

Launch the GUI application:

```bash
python image_scraper_gui.py
```

The interface provides:

- Search query input
- Engine selection (Bing, Google, Custom URL, or all)
- Output directory selection
- Resolution constraints
- WebP to JPG conversion toggle
- Image compression and resizing options
- Real-time logging
- Progress tracking

### Command-Line Interface

For automation or scripting, use the CLI tool:

```bash
python image_scraper_multitool.py "search query" [options]
```

#### Examples

Scrape 20 images from both engines:

```bash
python image_scraper_multitool.py "red pandas" --num-images 20
```

Scrape only from Bing with custom timeout:

```bash
python image_scraper_multitool.py "cats" --engine bing --num-images 10 --bing-timeout 30
```

Scrape from Google with resolution constraints:

```bash
python image_scraper_multitool.py "mountains" --engine google --google-min-resolution 1024 768 --google-max-resolution 4096 2160
```

#### CLI Options

```text
positional arguments:
  query                 Search term to scrape images for

optional arguments:
  --num-images NUM_IMAGES
                        Number of images to attempt to download per engine (default: 10)
  --engine {bing,google}
                        Specify one or more engines. Defaults to both
  --output-dir OUTPUT_DIR
                        Base directory where images should be saved (default: ./downloads)
  --keep-filenames      Keep filenames from the search results when possible
  --bing-timeout BING_TIMEOUT
                        Timeout in seconds for individual Bing requests (default: 15)
  --google-chromedriver GOOGLE_CHROMEDRIVER
                        Path to the ChromeDriver binary (default: ./webdriver/chromedriver)
  --google-show-browser
                        Run the Google scraper with a visible browser instead of headless mode
  --google-min-resolution WIDTH HEIGHT
                        Minimum resolution accepted by the Google scraper (default: 0 0)
  --google-max-resolution WIDTH HEIGHT
                        Maximum resolution accepted by the Google scraper (default: 1920 1080)
  --google-max-missed GOOGLE_MAX_MISSED
                        Maximum number of consecutive misses before Google scraping stops (default: 10)
  --log-level {DEBUG,INFO,WARNING,ERROR}
                        Adjust logging verbosity (default: INFO)
```

## ChromeDriver Setup

For Google Images scraping, the tool requires ChromeDriver:

- **Automatic**: If not found, the tool automatically downloads a compatible version
- **Manual Override**: Specify a custom path using `--google-chromedriver` or in the GUI
- **Platform Detection**: Automatically detects your OS and Chrome version for compatibility

## Output Structure

Images are organized as follows:

```text
downloads/
├── bing/
│   └── search-query-slug/
│       ├── bing_0001.jpg
│       ├── bing_0002.png
│       └── _downloaded_urls.txt
└── google/
    └── search-query-slug/
        ├── google_0001.jpg
        ├── google_0002.webp
        └── _downloaded_urls.txt
```

- Images are saved in subdirectories by engine and search query
- Filenames can be original names (when `--keep-filenames` is used) or numbered sequences
- `_downloaded_urls.txt` tracks downloaded URLs to prevent duplicates across runs

## Troubleshooting

### Common Issues

#### ChromeDriver download fails

- Ensure internet connection is stable
- Check firewall/antivirus settings
- Manually download from [ChromeDriver Downloads](https://googlechromelabs.github.io/chromedriver/)

#### Google scraping returns few results

- Try adjusting resolution constraints
- Increase `--google-max-missed` value
- Ensure Chrome browser is up to date

#### Bing scraping fails

- Check network connectivity
- Increase `--bing-timeout` value
- Bing may block requests from certain IP ranges

#### GUI doesn't start

- Ensure Python 3.8+ is installed
- Install all requirements: `pip install -r requirements.txt`
- On Linux, install tkinter: `sudo apt-get install python3-tk`

### Getting Help

- Check the [Issues](https://github.com/soficis/Google-Image-Scraper/issues) page for known problems
- Open a new issue for bugs or feature requests
- Include your OS, Python version, and error messages when reporting issues

## Disclaimer

This tool is for educational and research purposes. Please respect the terms of service of the search engines and websites you scrape. Be mindful of copyright laws and usage rights for downloaded images.

## License

This project is licensed under the **GNU General Public License v3.0** (GPLv3).

This means you are free to:

- Use, copy, and distribute this software
- Modify the source code
- Distribute your modifications

Under the condition that:

- Any derivative work must also be licensed under GPLv3
- You must include the original copyright notice and license
- Source code must be made available when distributing

See the [LICENSE](LICENSE) file for the full license text, or visit <https://www.gnu.org/licenses/gpl-3.0.html>.
