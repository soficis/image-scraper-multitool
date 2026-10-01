"""Tkinter GUI shell: app window, shared state, log panel, file dialogs.

Tab content lives in scrape_tab.py (widgets), scrape_runner.py (execution),
and convert_panel.py (Convert & Compress); all are mixed into ScraperApp below.
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .convert_panel import KEEP_LABEL, ConvertPanelMixin
from .scrape_runner import ScrapeRunnerMixin
from .scrape_tab import ScrapeTabMixin
from .settings import load_settings, save_settings
from .theme import ThemeManager

LOGGER = logging.getLogger("image_scraper_gui")


class TkQueueHandler(logging.Handler):
    """Forward log messages to the Tk UI thread."""

    def __init__(self, destination: queue.Queue[str]) -> None:
        super().__init__()
        self.destination = destination

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        self.destination.put(message)


class ScraperApp(ScrapeRunnerMixin, ScrapeTabMixin, ConvertPanelMixin, tk.Tk):
    """Main GUI app."""

    POLL_INTERVAL_MS = 125

    def __init__(self) -> None:
        super().__init__()
        self.title("Image Scraper Multitool")
        self.geometry("980x780")
        self.minsize(920, 540)

        self.log_queue: queue.Queue[str] = queue.Queue()
        # Worker threads must never call Tk (including after()) directly: it
        # only works while mainloop runs and can deadlock. They post here and
        # the main thread runs the calls from _poll_logs.
        self.ui_calls: queue.Queue[tuple[Callable[..., None], tuple[Any, ...]]] = queue.Queue()
        self.log_handler = TkQueueHandler(self.log_queue)
        self.log_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)

        self.scrape_thread: threading.Thread | None = None
        self.scrape_stop_event = threading.Event()

        self.convert_thread: threading.Thread | None = None
        self.convert_stop_event = threading.Event()

        self.vars = self._init_vars()
        self._load_persisted_settings()
        self.theme = ThemeManager(self)
        self._build_ui()
        self.theme.apply(dark=bool(self.vars["dark_mode"].get()))
        self._fit_height_to_content()
        self.vars["dark_mode"].trace_add("write", self._on_theme_toggle)

        self.after(self.POLL_INTERVAL_MS, self._poll_logs)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _init_vars(self) -> dict[str, tk.Variable]:
        return {
            "mode": tk.StringVar(value="search"),
            "query": tk.StringVar(value=""),
            "num_images": tk.IntVar(value=10),
            "output_dir": tk.StringVar(value=str(Path.cwd() / "downloads")),
            "bing": tk.BooleanVar(value=True),
            "google": tk.BooleanVar(value=False),
            "pexels": tk.BooleanVar(value=False),
            "pixabay": tk.BooleanVar(value=False),
            "openverse": tk.BooleanVar(value=False),
            "expand_queries": tk.BooleanVar(value=False),
            "pexels_api_key": tk.StringVar(value=""),
            "pixabay_api_key": tk.StringVar(value=""),
            "remember_api_keys": tk.BooleanVar(value=False),
            "keep_filenames": tk.BooleanVar(value=False),
            "convert_webp": tk.BooleanVar(value=False),
            "bing_timeout": tk.DoubleVar(value=15.0),
            "api_timeout": tk.DoubleVar(value=15.0),
            "advanced_open": tk.BooleanVar(value=False),
            "chromedriver": tk.StringVar(value=""),
            "show_browser": tk.BooleanVar(value=False),
            "min_width": tk.IntVar(value=0),
            "min_height": tk.IntVar(value=0),
            "max_width": tk.IntVar(value=0),
            "max_height": tk.IntVar(value=0),
            "max_missed": tk.IntVar(value=10),
            "recursion_depth": tk.IntVar(value=0),
            "compression_quality": tk.IntVar(value=0),
            "resize_width": tk.IntVar(value=0),
            "resize_height": tk.IntVar(value=0),
            "scrape_format": tk.StringVar(value=KEEP_LABEL),
            "scrape_quality": tk.IntVar(value=85),
            "scrape_max_width": tk.IntVar(value=0),
            "scrape_max_height": tk.IntVar(value=0),
            "convert_paths": tk.StringVar(value=""),
            "convert_format": tk.StringVar(value=KEEP_LABEL),
            "convert_quality": tk.IntVar(value=85),
            "convert_lossless": tk.BooleanVar(value=False),
            "convert_max_width": tk.IntVar(value=0),
            "convert_max_height": tk.IntVar(value=0),
            "convert_strip_metadata": tk.BooleanVar(value=False),
            "convert_only_smaller": tk.BooleanVar(value=False),
            "convert_use_source_dir": tk.BooleanVar(value=True),
            "convert_output_dir": tk.StringVar(value=""),
            "dark_mode": tk.BooleanVar(value=True),
        }

    def _load_persisted_settings(self) -> None:
        saved = load_settings()
        for key, value in saved.items():
            if key in ("query", "convert_paths"):
                continue
            if key not in self.vars:
                continue
            var = self.vars[key]
            if isinstance(var, tk.BooleanVar):
                if isinstance(value, bool):
                    var.set(value)
            elif isinstance(var, tk.IntVar):
                if isinstance(value, int) and not isinstance(value, bool):
                    var.set(value)
            elif isinstance(var, tk.DoubleVar):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    var.set(float(value))
            elif isinstance(var, tk.StringVar):
                if isinstance(value, str):
                    var.set(value)

    def _save_persisted_settings(self) -> None:
        remember_keys = bool(self.vars.get("remember_api_keys", tk.BooleanVar(value=False)).get())
        data: dict[str, Any] = {}
        for key, var in self.vars.items():
            if key in ("query", "convert_paths"):
                continue
            if key in ("pexels_api_key", "pixabay_api_key") and not remember_keys:
                continue
            try:
                data[key] = var.get()
            except (tk.TclError, TypeError, ValueError):
                continue
        save_settings(data)

    def _on_theme_toggle(self, *_args: object) -> None:
        self.theme.apply(dark=bool(self.vars["dark_mode"].get()))
        self._fit_height_to_content()
        self._save_persisted_settings()

    def _fit_height_to_content(self) -> None:
        # Themes differ in widget padding; grow the window so the Activity Log
        # is not squeezed, but never past the usable screen height.
        self.update_idletasks()
        needed = self.winfo_reqheight()
        usable = max(400, self.winfo_screenheight() - 80)
        height = max(self.winfo_height(), min(needed, usable))
        self.minsize(920, min(540, usable))
        if height != self.winfo_height():
            self.geometry(f"{self.winfo_width()}x{height}")

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container)
        header.pack(fill=tk.X)
        title = ttk.Label(header, text="Image Scraper Multitool", font=("Segoe UI", 18, "bold"))
        title.pack(side=tk.LEFT)
        ttk.Checkbutton(header, text="Dark mode", variable=self.vars["dark_mode"]).pack(
            side=tk.RIGHT
        )

        paned = ttk.PanedWindow(container, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        self.notebook = ttk.Notebook(paned)
        paned.add(self.notebook, weight=3)

        scrape_tab = ttk.Frame(self.notebook, padding=12)
        convert_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(scrape_tab, text="Scrape Images")
        self.notebook.add(convert_tab, text="Convert & Compress")

        self._build_scrape_tab(scrape_tab)
        self._build_convert_tab(convert_tab)

        log_frame = self._build_log_panel(paned)
        paned.add(log_frame, weight=1)

        self.bind("<Control-Return>", self._on_ctrl_enter)
        self.bind("<Escape>", self._on_escape)

    def _on_ctrl_enter(self, _event: tk.Event[tk.Misc]) -> None:
        tab_idx = self.notebook.index(self.notebook.select())
        if tab_idx == 0:
            self._start_scrape()
        elif tab_idx == 1:
            self._start_convert()

    def _on_escape(self, _event: tk.Event[tk.Misc]) -> None:
        tab_idx = self.notebook.index(self.notebook.select())
        if tab_idx == 0:
            self._stop_scrape()
        elif tab_idx == 1:
            self._stop_convert()

    def _build_log_panel(self, parent: ttk.PanedWindow | ttk.Frame) -> ttk.LabelFrame:
        log_frame = ttk.LabelFrame(parent, text="Activity Log", padding=8)

        log_top = ttk.Frame(log_frame)
        log_top.pack(fill=tk.X, pady=(0, 4))
        self.clear_log_button = ttk.Button(log_top, text="Clear log", command=self._clear_log)
        self.clear_log_button.pack(side=tk.RIGHT)

        text_frame = ttk.Frame(log_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)

        # tk.Text + ttk.Scrollbar rather than ScrolledText: its tk.Scrollbar is
        # a native control on Windows and cannot be recoloured for dark mode.
        self.log_widget = tk.Text(text_frame, height=6, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.log_widget.yview)
        self.log_widget.configure(yscrollcommand=scrollbar.set, state=tk.DISABLED)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.theme.register_text(self.log_widget)
        return log_frame

    def _clear_log(self) -> None:
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.delete("1.0", tk.END)
        self.log_widget.configure(state=tk.DISABLED)

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="Select output directory")
        if selected:
            self.vars["output_dir"].set(selected)

    def _choose_chromedriver(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select chromedriver executable",
            filetypes=[
                ("Chromedriver", "chromedriver*"),
                ("Executable", "*.exe"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            self.vars["chromedriver"].set(selected)

    def post_to_ui(self, callback: Callable[..., None], *args: Any) -> None:
        """Thread-safe: run `callback(*args)` on the Tk main thread."""
        self.ui_calls.put((callback, args))

    def _poll_logs(self) -> None:
        try:
            while True:
                message = self.log_queue.get_nowait()
                self._append_log(message)
        except queue.Empty:
            pass
        try:
            while True:
                callback, args = self.ui_calls.get_nowait()
                try:
                    callback(*args)
                except Exception:
                    LOGGER.exception(
                        "UI callback %s failed", getattr(callback, "__name__", callback)
                    )
        except queue.Empty:
            pass
        finally:
            self.after(self.POLL_INTERVAL_MS, self._poll_logs)

    def _append_log(self, message: str) -> None:
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, message + "\n")
        self.log_widget.configure(state=tk.DISABLED)
        self.log_widget.see(tk.END)

    def _on_close(self) -> None:
        if self.scrape_thread and self.scrape_thread.is_alive():
            if not messagebox.askokcancel("Quit", "Scrape is still running. Quit anyway?"):
                return
            self.scrape_stop_event.set()

        if self.convert_thread and self.convert_thread.is_alive():
            if not messagebox.askokcancel("Quit", "Conversion is still running. Quit anyway?"):
                return
            self.convert_stop_event.set()

        self._save_persisted_settings()
        logging.getLogger().removeHandler(self.log_handler)
        self.destroy()


def main() -> None:
    app = ScraperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
