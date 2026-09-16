"""Scrape execution for the Tk GUI: options assembly plus background thread lifecycle.

Compiles widget state into ScrapeOptions, runs scrape_images off the UI
thread, and reports completion back via `after`. Mixed into ScraperApp.
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Sequence
from pathlib import Path
from tkinter import messagebox, ttk

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


class ScrapeRunnerMixin(tk.Tk):
    """Runs scrapes in the background. Mixed into ScraperApp (never alone)."""

    # Provided by ScraperApp / sibling mixins; declared here for type-checking.
    vars: dict[str, tk.Variable]
    scrape_thread: threading.Thread | None
    scrape_stop_event: threading.Event
    scrape_status: ttk.Label
    scrape_start_button: ttk.Button
    scrape_stop_button: ttk.Button

    def _append_log(self, message: str) -> None: ...

    def _compile_scrape_options(self) -> ScrapeOptions | None:
        query = self.vars["query"].get().strip()
        if not query:
            messagebox.showwarning("Missing query", "Enter a search query or URL.")
            return None

        try:
            num_images = int(self.vars["num_images"].get())
        except (TypeError, ValueError):
            messagebox.showerror("Invalid value", "Images must be a positive integer.")
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
            if not engines_list:
                messagebox.showwarning("No engines selected", "Choose at least one engine.")
                return None
            engines = engines_list

        chromedriver_value = self.vars["chromedriver"].get().strip()
        chromedriver = Path(chromedriver_value).expanduser() if chromedriver_value else None

        options = ScrapeOptions(
            query=query,
            engines=engines,
            limit=num_images,
            output_dir=Path(self.vars["output_dir"].get()).expanduser(),
            keep_filenames=self.vars["keep_filenames"].get(),
            bing_timeout=float(self.vars["bing_timeout"].get()),
            expand_queries=self.vars["expand_queries"].get(),
            pexels_api_key=self.vars["pexels_api_key"].get().strip(),
            pixabay_api_key=self.vars["pixabay_api_key"].get().strip(),
            transform=TransformOptions(
                convert_webp=self.vars["convert_webp"].get(),
                compression_quality=int(self.vars["compression_quality"].get()),
                resize_width=int(self.vars["resize_width"].get()),
                resize_height=int(self.vars["resize_height"].get()),
            ),
            google=GoogleOptions(
                chromedriver_path=chromedriver,
                headless=not self.vars["show_browser"].get(),
                min_resolution=(
                    int(self.vars["min_width"].get()),
                    int(self.vars["min_height"].get()),
                ),
                max_resolution=(
                    int(self.vars["max_width"].get()),
                    int(self.vars["max_height"].get()),
                ),
                max_missed=int(self.vars["max_missed"].get()),
            ),
            custom_page=CustomPageOptions(recursion_depth=int(self.vars["recursion_depth"].get())),
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

    def _run_scrape_thread(self, options: ScrapeOptions) -> None:
        try:
            results = scrape_images(options, stop_event=self.scrape_stop_event)
            self.after(0, self._on_scrape_complete, results, None)
        except Exception as error:
            self.after(0, self._on_scrape_complete, [], str(error))

    def _on_scrape_complete(self, results: Sequence[ScrapeResult], error: str | None) -> None:
        self.scrape_start_button.state(["!disabled"])
        self.scrape_stop_button.state(["disabled"])

        if error:
            self.scrape_status.configure(text="● Error")
            messagebox.showerror("Scrape error", error)
            return

        if self.scrape_stop_event.is_set() and not results:
            self.scrape_status.configure(text="● Ready")
            self._append_log("Scrape cancelled.")
            return

        self.scrape_status.configure(text="✓ Done")
        for result in results:
            self._append_log(
                f"{result.engine}: requested={result.requested} saved={result.saved} "
                f"skipped={result.skipped} -> {result.destination}"
            )
            if result.errors:
                self._append_log(f"{result.engine}: {len(result.errors)} errors")
                for error in result.errors[:3]:
                    self._append_log(f"  - {error}")
                if len(result.errors) > 3:
                    self._append_log(f"  - ... and {len(result.errors) - 3} more")
