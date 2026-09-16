"""Tkinter GUI shell: app window, shared state, log panel, file dialogs.

Tab content lives in scrape_tab.py (widgets), scrape_runner.py (execution),
and heic_panel.py (HEIC converter); all are mixed into ScraperApp below.
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .heic_panel import HeicPanelMixin
from .scrape_runner import ScrapeRunnerMixin
from .scrape_tab import ScrapeTabMixin

LOGGER = logging.getLogger("image_scraper_gui")


class TkQueueHandler(logging.Handler):
    """Forward log messages to the Tk UI thread."""

    def __init__(self, destination: queue.Queue[str]) -> None:
        super().__init__()
        self.destination = destination

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        self.destination.put(message)


class ScraperApp(ScrapeTabMixin, ScrapeRunnerMixin, HeicPanelMixin, tk.Tk):
    """Main GUI app."""

    POLL_INTERVAL_MS = 125

    def __init__(self) -> None:
        super().__init__()
        self.title("Image Scraper Multitool")
        self.geometry("980x780")
        self.minsize(920, 720)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.log_handler = TkQueueHandler(self.log_queue)
        self.log_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(self.log_handler)
        logging.getLogger().setLevel(logging.INFO)

        self.scrape_thread: threading.Thread | None = None
        self.scrape_stop_event = threading.Event()

        self.heic_thread: threading.Thread | None = None
        self.heic_stop_event = threading.Event()

        self.vars = self._init_vars()
        self._build_ui()

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
            "expand_queries": tk.BooleanVar(value=False),
            "pexels_api_key": tk.StringVar(value=""),
            "pixabay_api_key": tk.StringVar(value=""),
            "keep_filenames": tk.BooleanVar(value=False),
            "convert_webp": tk.BooleanVar(value=False),
            "bing_timeout": tk.DoubleVar(value=15.0),
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
            "heic_paths": tk.StringVar(value=""),
            "heic_output_format": tk.StringVar(value="jpg"),
            "heic_quality": tk.IntVar(value=85),
            "heic_use_source_dir": tk.BooleanVar(value=True),
            "heic_output_dir": tk.StringVar(value=""),
        }

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        title = ttk.Label(container, text="Image Scraper Multitool", font=("Segoe UI", 18, "bold"))
        title.pack(anchor=tk.W)

        notebook = ttk.Notebook(container)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(12, 12))

        scrape_tab = ttk.Frame(notebook, padding=12)
        heic_tab = ttk.Frame(notebook, padding=12)
        notebook.add(scrape_tab, text="Scrape Images")
        notebook.add(heic_tab, text="HEIC Converter")

        self._build_scrape_tab(scrape_tab)
        self._build_heic_tab(heic_tab)

        self._build_log_panel(container)

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        log_frame = ttk.LabelFrame(parent, text="Activity Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=False)

        self.log_widget = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD)
        self.log_widget.pack(fill=tk.BOTH, expand=True)
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

    def _poll_logs(self) -> None:
        try:
            while True:
                message = self.log_queue.get_nowait()
                self._append_log(message)
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

        if self.heic_thread and self.heic_thread.is_alive():
            if not messagebox.askokcancel("Quit", "HEIC conversion is still running. Quit anyway?"):
                return
            self.heic_stop_event.set()

        logging.getLogger().removeHandler(self.log_handler)
        self.destroy()


def main() -> None:
    app = ScraperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
