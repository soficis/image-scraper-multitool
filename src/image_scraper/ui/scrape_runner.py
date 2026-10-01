"""Scrape execution for the Tk GUI: options assembly plus background thread lifecycle.

Compiles widget state into ScrapeOptions, runs scrape_images off the UI
thread, and reports completion back via `after`. Mixed into ScraperApp.
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from collections.abc import Callable, Sequence
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, overload

from image_scraper.adapters.image_converter import available_output_formats
from image_scraper.app.scrape import scrape_images
from image_scraper.domain.models import (
    CustomPageOptions,
    EngineName,
    GoogleOptions,
    ScrapeOptions,
    ScrapeResult,
    TransformOptions,
)
from image_scraper.errors import ImageScraperError
from image_scraper.ui.platform_open import open_in_file_manager


class ScrapeRunnerMixin(tk.Tk):
    """Runs scrapes in the background. Mixed into ScraperApp (never alone)."""

    # Provided by ScraperApp / sibling mixins; declared here for type-checking.
    vars: dict[str, tk.Variable]
    scrape_thread: threading.Thread | None
    scrape_stop_event: threading.Event
    scrape_status: ttk.Label
    scrape_start_button: ttk.Button
    scrape_stop_button: ttk.Button
    scrape_open_folder_button: ttk.Button
    _last_scrape_folder: Path | None
    _scrape_engine_progress: dict[str, str]

    def _append_log(self, message: str) -> None: ...

    def post_to_ui(self, callback: Callable[..., None], *args: Any) -> None: ...

    @overload
    def _read_number(self, var_name: str, label: str, kind: type[int] = int) -> int | None: ...

    @overload
    def _read_number(self, var_name: str, label: str, kind: type[float]) -> float | None: ...

    def _read_number(
        self, var_name: str, label: str, kind: type[int] | type[float] = int
    ) -> int | float | None:
        try:
            val = self.vars[var_name].get()
            return kind(val)
        except (tk.TclError, TypeError, ValueError):
            if kind is int:
                messagebox.showerror("Invalid value", f"{label} must be a whole number.")
            else:
                messagebox.showerror("Invalid value", f"{label} must be a number.")
            return None

    def _compile_scrape_options(self) -> ScrapeOptions | None:
        query = self.vars["query"].get().strip()
        if not query:
            messagebox.showwarning("Missing query", "Enter a search query or URL.")
            return None

        num_images = self._read_number("num_images", "Images", int)
        if num_images is None:
            return None

        mode = self.vars["mode"].get()
        if mode == "url":
            engines: Sequence[EngineName] = ["custom"]
        else:
            engines_list: list[EngineName] = []
            if self.vars["bing"].get():
                engines_list.append("bing")
            if self.vars["google"].get():
                engines_list.append("google")
            if self.vars["pexels"].get():
                engines_list.append("pexels")
            if self.vars["pixabay"].get():
                engines_list.append("pixabay")
            if self.vars["openverse"].get():
                engines_list.append("openverse")
            if not engines_list:
                messagebox.showwarning("No engines selected", "Choose at least one engine.")
                return None
            engines = engines_list

        if "pexels" in engines:
            pexels_key = (
                self.vars["pexels_api_key"].get().strip()
                or os.environ.get("PEXELS_API_KEY", "").strip()
            )
            if not pexels_key:
                messagebox.showwarning(
                    "API key needed",
                    "Pexels needs a free API key: paste it under Sources, or set PEXELS_API_KEY. Get one at https://www.pexels.com/api/",
                )
                return None

        if "pixabay" in engines:
            pixabay_key = (
                self.vars["pixabay_api_key"].get().strip()
                or os.environ.get("PIXABAY_API_KEY", "").strip()
            )
            if not pixabay_key:
                messagebox.showwarning(
                    "API key needed",
                    "Pixabay needs a free API key: paste it under Sources, or set PIXABAY_API_KEY. Get one at https://pixabay.com/api/docs/",
                )
                return None

        chromedriver_value = self.vars["chromedriver"].get().strip()
        chromedriver = Path(chromedriver_value).expanduser() if chromedriver_value else None

        bing_timeout = self._read_number("bing_timeout", "Bing timeout", float)
        if bing_timeout is None:
            return None

        api_timeout = self._read_number("api_timeout", "API timeout", float)
        if api_timeout is None:
            return None

        compression_quality = self._read_number("compression_quality", "JPEG quality", int)
        if compression_quality is None:
            return None

        resize_width = self._read_number("resize_width", "Resize width", int)
        if resize_width is None:
            return None

        resize_height = self._read_number("resize_height", "Resize height", int)
        if resize_height is None:
            return None

        min_width = self._read_number("min_width", "Min width", int)
        if min_width is None:
            return None

        min_height = self._read_number("min_height", "Min height", int)
        if min_height is None:
            return None

        max_width = self._read_number("max_width", "Max width", int)
        if max_width is None:
            return None

        max_height = self._read_number("max_height", "Max height", int)
        if max_height is None:
            return None

        max_missed = self._read_number("max_missed", "Max missed passes", int)
        if max_missed is None:
            return None

        recursion_depth = self._read_number("recursion_depth", "Depth", int)
        if recursion_depth is None:
            return None

        fmt_label = str(
            self.vars.get("scrape_format", tk.StringVar(value="Keep original format")).get()
        )
        fmt_obj = next(
            (f for f in available_output_formats() if f.label == fmt_label),
            None,
        )
        scrape_format_key = fmt_obj.key if fmt_obj else "keep"

        scrape_quality = (
            self._read_number("scrape_quality", "Quality", int)
            if "scrape_quality" in self.vars
            else 85
        )
        if scrape_quality is None:
            return None
        scrape_max_w = (
            self._read_number("scrape_max_width", "Max width", int)
            if "scrape_max_width" in self.vars
            else 0
        )
        if scrape_max_w is None:
            return None
        scrape_max_h = (
            self._read_number("scrape_max_height", "Max height", int)
            if "scrape_max_height" in self.vars
            else 0
        )
        if scrape_max_h is None:
            return None

        options = ScrapeOptions(
            query=query,
            engines=engines,
            limit=num_images,
            output_dir=Path(self.vars["output_dir"].get()).expanduser(),
            keep_filenames=self.vars["keep_filenames"].get(),
            bing_timeout=bing_timeout,
            api_timeout=api_timeout,
            expand_queries=self.vars["expand_queries"].get(),
            pexels_api_key=self.vars["pexels_api_key"].get().strip(),
            pixabay_api_key=self.vars["pixabay_api_key"].get().strip(),
            transform=TransformOptions(
                convert_webp=bool(self.vars["convert_webp"].get()),
                compression_quality=compression_quality,
                resize_width=resize_width,
                resize_height=resize_height,
                format=scrape_format_key,
                quality=scrape_quality,
                max_width=scrape_max_w,
                max_height=scrape_max_h,
            ),
            google=GoogleOptions(
                chromedriver_path=chromedriver,
                headless=not self.vars["show_browser"].get(),
                min_resolution=(min_width, min_height),
                max_resolution=(max_width, max_height),
                max_missed=max_missed,
            ),
            custom_page=CustomPageOptions(recursion_depth=recursion_depth),
        )

        try:
            options.validate()
        except ImageScraperError as error:
            messagebox.showerror("Invalid configuration", str(error))
            return None

        return options

    def _start_scrape(self) -> None:
        if self.scrape_thread and self.scrape_thread.is_alive():
            messagebox.showinfo("Scraper busy", "Scraping is already running.")
            return

        options = self._compile_scrape_options()
        if options is None:
            return

        self._scrape_engine_progress = {}
        if hasattr(self, "scrape_open_folder_button"):
            self.scrape_open_folder_button.state(["disabled"])

        self.scrape_status.configure(text="● Running")
        self.scrape_start_button.state(["disabled"])
        self.scrape_stop_button.state(["!disabled"])

        self.scrape_stop_event.clear()
        self.scrape_thread = threading.Thread(
            target=self._run_scrape_thread, args=(options,), daemon=True
        )
        self.scrape_thread.start()

    def _stop_scrape(self) -> None:
        if self.scrape_thread and self.scrape_thread.is_alive():
            self.scrape_stop_event.set()
            self.scrape_status.configure(text="● Stopping")
            self.scrape_stop_button.state(["disabled"])

    def _show_scrape_progress(self, engine: str, saved: int, requested: int) -> None:
        if not hasattr(self, "_scrape_engine_progress"):
            self._scrape_engine_progress = {}
        if saved == -1:
            self._scrape_engine_progress[engine] = f"{engine.capitalize()} collecting…"
        else:
            self._scrape_engine_progress[engine] = f"{engine.capitalize()} {saved}/{requested}"
        parts = list(self._scrape_engine_progress.values())
        self.scrape_status.configure(text="● " + " · ".join(parts))

    def _run_scrape_thread(self, options: ScrapeOptions) -> None:
        def on_progress(engine: str, saved: int, requested: int) -> None:
            self.post_to_ui(self._show_scrape_progress, engine, saved, requested)

        try:
            results = scrape_images(
                options, stop_event=self.scrape_stop_event, progress=on_progress
            )
            self.post_to_ui(self._on_scrape_complete, results, None)
        except Exception as error:
            self.post_to_ui(self._on_scrape_complete, [], str(error))

    def _on_scrape_complete(self, results: Sequence[ScrapeResult], error: str | None) -> None:
        self.scrape_start_button.state(["!disabled"])
        self.scrape_stop_button.state(["disabled"])

        if results:
            destinations = [str(r.destination) for r in results]
            try:
                common = os.path.commonpath(destinations)
                self._last_scrape_folder = Path(common)
            except ValueError:
                self._last_scrape_folder = results[0].destination
            if hasattr(self, "scrape_open_folder_button"):
                self.scrape_open_folder_button.state(["!disabled"])
        else:
            raw_dir = str(self.vars["output_dir"].get()).strip()
            if raw_dir:
                folder = Path(raw_dir).expanduser()
                if folder.exists():
                    self._last_scrape_folder = folder
                    if hasattr(self, "scrape_open_folder_button"):
                        self.scrape_open_folder_button.state(["!disabled"])

        if error:
            self.scrape_status.configure(text="● Error")
            messagebox.showerror("Scrape error", error)
            return

        total_saved = sum(result.saved for result in results)
        if self.scrape_stop_event.is_set():
            status_text = f"■ Stopped — {total_saved} saved"
            self.scrape_status.configure(text=status_text)
            self._append_log(f"[Scrape] {status_text}")
        else:
            status_text = f"✓ Done — {total_saved} saved"
            self.scrape_status.configure(text=status_text)
            self._append_log(f"[Scrape] {status_text}")

        for result in results:
            self._append_log(
                f"[Scrape] {result.engine}: requested={result.requested} saved={result.saved} "
                f"skipped={result.skipped} -> {result.destination}"
            )
            if result.errors:
                self._append_log(f"[Scrape] {result.engine}: {len(result.errors)} errors")
                for err in result.errors[:25]:
                    self._append_log(f"[Scrape]   - {err}")
                if len(result.errors) > 25:
                    self._append_log(f"[Scrape]   - … and {len(result.errors) - 25} more")

    def _open_scrape_folder(self) -> None:
        folder = getattr(self, "_last_scrape_folder", None)
        if not folder:
            raw_dir = str(self.vars["output_dir"].get()).strip()
            if raw_dir:
                folder = Path(raw_dir).expanduser()
        if not folder or not Path(folder).exists():
            messagebox.showinfo("Folder not found", "Output folder does not exist yet.")
            return
        if not open_in_file_manager(folder):
            messagebox.showerror("Error", f"Could not open folder:\n{folder}")
