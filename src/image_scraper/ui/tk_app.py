"""Tkinter GUI for image scraper workflows."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from image_scraper.app.heic import convert_heic_batch
from image_scraper.app.scrape import scrape_images
from image_scraper.domain.models import (
    BatchConversionResult,
    CustomPageOptions,
    EngineName,
    GoogleOptions,
    ScrapeOptions,
    ScrapeResult,
    TransformOptions,
)
from image_scraper.errors import ImageScraperError

LOGGER = logging.getLogger("image_scraper_gui")


@dataclass(frozen=True)
class HeicRequest:
    input_paths: list[Path]
    output_dir: Path
    output_format: str
    quality: int


class TkQueueHandler(logging.Handler):
    """Forward log messages to the Tk UI thread."""

    def __init__(self, destination: queue.Queue[str]) -> None:
        super().__init__()
        self.destination = destination

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        self.destination.put(message)


class ScraperApp(tk.Tk):
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

    def _build_scrape_tab(self, parent: ttk.Frame) -> None:
        mode_row = ttk.Frame(parent)
        mode_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(mode_row, text="Mode:").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Radiobutton(
            mode_row,
            text="Keyword Search",
            variable=self.vars["mode"],
            value="search",
            command=self._on_mode_changed,
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Radiobutton(
            mode_row,
            text="Page URL",
            variable=self.vars["mode"],
            value="url",
            command=self._on_mode_changed,
        ).pack(side=tk.LEFT, padx=(0, 12))

        self.depth_spin = ttk.Spinbox(
            mode_row, from_=0, to=3, width=4, textvariable=self.vars["recursion_depth"]
        )
        ttk.Label(mode_row, text="Depth:").pack(side=tk.LEFT, padx=(8, 6))
        self.depth_spin.pack(side=tk.LEFT)

        query_row = ttk.Frame(parent)
        query_row.pack(fill=tk.X, pady=(0, 8))
        self.query_label = ttk.Label(query_row, text="Search Query")
        self.query_label.pack(anchor=tk.W)
        query_input = ttk.Frame(parent)
        query_input.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(query_input, textvariable=self.vars["query"]).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Label(query_input, text="Images").pack(side=tk.LEFT, padx=(12, 6))
        ttk.Spinbox(
            query_input, from_=1, to=500, textvariable=self.vars["num_images"], width=8
        ).pack(side=tk.LEFT)

        output_row = ttk.LabelFrame(parent, text="Output", padding=8)
        output_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(output_row, textvariable=self.vars["output_dir"]).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(output_row, text="Browse…", command=self._choose_output_dir).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        engines_row = ttk.LabelFrame(parent, text="Engines", padding=8)
        engines_row.pack(fill=tk.X, pady=(0, 8))
        self.bing_check = ttk.Checkbutton(engines_row, text="Bing", variable=self.vars["bing"])
        self.google_check = ttk.Checkbutton(
            engines_row, text="Google", variable=self.vars["google"]
        )
        self.bing_check.pack(side=tk.LEFT, padx=(0, 16))
        self.google_check.pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(
            engines_row, text="Keep original filenames", variable=self.vars["keep_filenames"]
        ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(
            engines_row, text="Convert WebP to JPG", variable=self.vars["convert_webp"]
        ).pack(side=tk.LEFT)

        settings = ttk.Frame(parent)
        settings.pack(fill=tk.BOTH, expand=True)

        left = ttk.LabelFrame(settings, text="General", padding=8)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))

        ttk.Label(left, text="Bing timeout (seconds)").grid(row=0, column=0, sticky=tk.W)
        ttk.Spinbox(
            left,
            from_=1.0,
            to=60.0,
            increment=0.5,
            width=10,
            textvariable=self.vars["bing_timeout"],
        ).grid(row=0, column=1, sticky=tk.W, padx=(8, 0))

        ttk.Label(left, text="JPEG quality (0-100)").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Spinbox(
            left, from_=0, to=100, width=10, textvariable=self.vars["compression_quality"]
        ).grid(row=1, column=1, sticky=tk.W, padx=(8, 0), pady=(6, 0))

        ttk.Label(left, text="Resize width").grid(row=2, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Spinbox(left, from_=0, to=7680, width=10, textvariable=self.vars["resize_width"]).grid(
            row=2, column=1, sticky=tk.W, padx=(8, 0), pady=(6, 0)
        )

        ttk.Label(left, text="Resize height").grid(row=3, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Spinbox(left, from_=0, to=4320, width=10, textvariable=self.vars["resize_height"]).grid(
            row=3, column=1, sticky=tk.W, padx=(8, 0), pady=(6, 0)
        )

        right = ttk.LabelFrame(settings, text="Google + Custom URL", padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))

        ttk.Label(right, text="Chromedriver path (optional, leave blank for auto)").grid(
            row=0, column=0, sticky=tk.W
        )
        driver_row = ttk.Frame(right)
        driver_row.grid(row=1, column=0, columnspan=2, sticky=tk.EW)
        ttk.Entry(driver_row, textvariable=self.vars["chromedriver"]).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(driver_row, text="Locate…", command=self._choose_chromedriver).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        ttk.Checkbutton(right, text="Show browser", variable=self.vars["show_browser"]).grid(
            row=2, column=0, sticky=tk.W, pady=(8, 0)
        )

        ttk.Label(right, text="Min resolution (W x H)").grid(
            row=3, column=0, sticky=tk.W, pady=(8, 0)
        )
        min_row = ttk.Frame(right)
        min_row.grid(row=4, column=0, sticky=tk.W)
        ttk.Spinbox(min_row, from_=0, to=7680, width=7, textvariable=self.vars["min_width"]).pack(
            side=tk.LEFT
        )
        ttk.Label(min_row, text="x").pack(side=tk.LEFT, padx=4)
        ttk.Spinbox(min_row, from_=0, to=4320, width=7, textvariable=self.vars["min_height"]).pack(
            side=tk.LEFT
        )

        ttk.Label(right, text="Max resolution (W x H)").grid(
            row=5, column=0, sticky=tk.W, pady=(8, 0)
        )
        max_row = ttk.Frame(right)
        max_row.grid(row=6, column=0, sticky=tk.W)
        ttk.Spinbox(max_row, from_=0, to=7680, width=7, textvariable=self.vars["max_width"]).pack(
            side=tk.LEFT
        )
        ttk.Label(max_row, text="x").pack(side=tk.LEFT, padx=4)
        ttk.Spinbox(max_row, from_=0, to=4320, width=7, textvariable=self.vars["max_height"]).pack(
            side=tk.LEFT
        )

        ttk.Label(right, text="Max missed passes").grid(row=7, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Spinbox(right, from_=1, to=100, width=7, textvariable=self.vars["max_missed"]).grid(
            row=7, column=1, sticky=tk.W, padx=(8, 0), pady=(8, 0)
        )

        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X, pady=(10, 0))
        self.scrape_status = ttk.Label(actions, text="● Ready")
        self.scrape_status.pack(side=tk.LEFT)

        self.scrape_stop_button = ttk.Button(
            actions, text="Stop", command=self._stop_scrape, state="disabled"
        )
        self.scrape_stop_button.pack(side=tk.RIGHT)
        self.scrape_start_button = ttk.Button(
            actions, text="Start Scraping", command=self._start_scrape
        )
        self.scrape_start_button.pack(side=tk.RIGHT, padx=(0, 8))

        self._on_mode_changed()

    def _build_heic_tab(self, parent: ttk.Frame) -> None:
        files_box = ttk.LabelFrame(parent, text="Input HEIC files/folders", padding=8)
        files_box.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(
            files_box, text="Selected paths are scanned recursively for .heic/.heif files."
        ).pack(anchor=tk.W)

        controls = ttk.Frame(files_box)
        controls.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(controls, text="Browse Files…", command=self._browse_heic_files).pack(
            side=tk.LEFT
        )
        ttk.Button(controls, text="Browse Folder…", command=self._browse_heic_folder).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(controls, text="Clear", command=self._clear_heic_paths).pack(side=tk.RIGHT)

        self.heic_count_label = ttk.Label(files_box, text="No files selected")
        self.heic_count_label.pack(anchor=tk.W, pady=(8, 0))

        options_row = ttk.Frame(parent)
        options_row.pack(fill=tk.X, pady=(0, 8))

        left = ttk.LabelFrame(options_row, text="Output Settings", padding=8)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        ttk.Label(left, text="Format").grid(row=0, column=0, sticky=tk.W)
        ttk.Combobox(
            left,
            textvariable=self.vars["heic_output_format"],
            values=["jpg", "png"],
            width=8,
            state="readonly",
        ).grid(row=0, column=1, sticky=tk.W, padx=(8, 0))
        ttk.Label(left, text="Quality (1-100)").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Spinbox(left, from_=1, to=100, width=8, textvariable=self.vars["heic_quality"]).grid(
            row=1, column=1, sticky=tk.W, padx=(8, 0), pady=(8, 0)
        )

        right = ttk.LabelFrame(options_row, text="Output Location", padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
        ttk.Checkbutton(
            right,
            text="Use source directory",
            variable=self.vars["heic_use_source_dir"],
            command=self._on_heic_output_toggle,
        ).pack(anchor=tk.W)
        output_row = ttk.Frame(right)
        output_row.pack(fill=tk.X, pady=(8, 0))
        self.heic_output_entry = ttk.Entry(
            output_row, textvariable=self.vars["heic_output_dir"], state="disabled"
        )
        self.heic_output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.heic_output_browse = ttk.Button(
            output_row, text="Browse…", command=self._choose_heic_output_dir, state="disabled"
        )
        self.heic_output_browse.pack(side=tk.LEFT, padx=(8, 0))

        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X)
        self.heic_status = ttk.Label(actions, text="● Ready")
        self.heic_status.pack(side=tk.LEFT)

        self.heic_stop_button = ttk.Button(
            actions, text="Stop", command=self._stop_heic, state="disabled"
        )
        self.heic_stop_button.pack(side=tk.RIGHT)
        self.heic_start_button = ttk.Button(actions, text="Convert HEIC", command=self._start_heic)
        self.heic_start_button.pack(side=tk.RIGHT, padx=(0, 8))

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        log_frame = ttk.LabelFrame(parent, text="Activity Log", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=False)

        self.log_widget = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD)
        self.log_widget.pack(fill=tk.BOTH, expand=True)
        self.log_widget.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # UI state controls
    # ------------------------------------------------------------------
    def _on_mode_changed(self) -> None:
        is_url_mode = self.vars["mode"].get() == "url"
        self.query_label.configure(text="Target URL" if is_url_mode else "Search Query")

        if is_url_mode:
            self.bing_check.state(["disabled"])
            self.google_check.state(["disabled"])
            self.depth_spin.state(["!disabled"])
        else:
            self.bing_check.state(["!disabled"])
            self.google_check.state(["!disabled"])
            self.depth_spin.state(["disabled"])

    def _on_heic_output_toggle(self) -> None:
        use_source = self.vars["heic_use_source_dir"].get()
        if use_source:
            self.heic_output_entry.configure(state="disabled")
            self.heic_output_browse.configure(state="disabled")
        else:
            self.heic_output_entry.configure(state="normal")
            self.heic_output_browse.configure(state="normal")

    # ------------------------------------------------------------------
    # Scrape flow
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # HEIC flow
    # ------------------------------------------------------------------
    def _add_heic_paths(self, values: Sequence[str]) -> None:
        existing = {value for value in self.vars["heic_paths"].get().split("|") if value}
        existing.update(value for value in values if value)
        self.vars["heic_paths"].set("|".join(sorted(existing)))
        self._update_heic_count()

    def _browse_heic_files(self) -> None:
        files = filedialog.askopenfilenames(
            title="Select HEIC files",
            filetypes=[("HEIC files", "*.heic *.HEIC *.heif *.HEIF"), ("All files", "*.*")],
        )
        if files:
            self._add_heic_paths(files)

    def _browse_heic_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder with HEIC files")
        if folder:
            self._add_heic_paths([folder])

    def _clear_heic_paths(self) -> None:
        self.vars["heic_paths"].set("")
        self._update_heic_count()

    def _update_heic_count(self) -> None:
        raw = self.vars["heic_paths"].get()
        if not raw:
            self.heic_count_label.configure(text="No files selected")
            return

        paths = [Path(value) for value in raw.split("|") if value]
        heic_count = 0
        folder_count = 0
        file_count = 0

        for path in paths:
            if path.is_dir():
                folder_count += 1
                heic_count += sum(
                    1
                    for item in path.rglob("*")
                    if item.is_file() and item.suffix.lower() in {".heic", ".heif"}
                )
            elif path.is_file() and path.suffix.lower() in {".heic", ".heif"}:
                file_count += 1
                heic_count += 1

        self.heic_count_label.configure(
            text=f"{folder_count} folder(s), {file_count} file(s) — {heic_count} HEIC file(s) found"
        )

    def _choose_heic_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="Select HEIC output directory")
        if selected:
            self.vars["heic_output_dir"].set(selected)

    def _compile_heic_request(self) -> HeicRequest | None:
        paths = [Path(value) for value in self.vars["heic_paths"].get().split("|") if value]
        if not paths:
            messagebox.showwarning("No files", "Select one or more HEIC files/folders.")
            return None

        output_format = self.vars["heic_output_format"].get()
        quality = int(self.vars["heic_quality"].get())

        if self.vars["heic_use_source_dir"].get():
            first = paths[0]
            output_dir = first if first.is_dir() else first.parent
        else:
            output_dir_text = self.vars["heic_output_dir"].get().strip()
            if not output_dir_text:
                messagebox.showwarning("No output", "Choose an output directory.")
                return None
            output_dir = Path(output_dir_text)

        return HeicRequest(
            input_paths=paths,
            output_dir=output_dir,
            output_format=output_format,
            quality=quality,
        )

    def _start_heic(self) -> None:
        if self.heic_thread and self.heic_thread.is_alive():
            messagebox.showinfo("Converter busy", "HEIC conversion is already running.")
            return

        request = self._compile_heic_request()
        if request is None:
            return

        self.heic_status.configure(text="● Running")
        self.heic_start_button.state(["disabled"])
        self.heic_stop_button.state(["!disabled"])

        self.heic_stop_event.clear()
        self.heic_thread = threading.Thread(
            target=self._run_heic_thread, args=(request,), daemon=True
        )
        self.heic_thread.start()

    def _stop_heic(self) -> None:
        if self.heic_thread and self.heic_thread.is_alive():
            self.heic_stop_event.set()
            self.heic_status.configure(text="● Stopping")
            self.heic_stop_button.state(["disabled"])

    def _run_heic_thread(self, request: HeicRequest) -> None:
        try:
            result = convert_heic_batch(
                input_paths=request.input_paths,
                output_dir=request.output_dir,
                output_format=request.output_format,
                quality=request.quality,
                stop_event=self.heic_stop_event,
            )
            self.after(0, self._on_heic_complete, result, None)
        except Exception as error:
            self.after(0, self._on_heic_complete, None, str(error))

    def _on_heic_complete(self, result: BatchConversionResult | None, error: str | None) -> None:
        self.heic_start_button.state(["!disabled"])
        self.heic_stop_button.state(["disabled"])

        if error:
            self.heic_status.configure(text="● Error")
            messagebox.showerror("HEIC conversion error", error)
            return

        if result is None:
            self.heic_status.configure(text="● Ready")
            return

        self.heic_status.configure(text="✓ Done")
        self._append_log(
            f"HEIC conversion: {result.converted}/{result.total_files} converted, "
            f"{result.skipped} skipped -> {result.output_dir}"
        )
        if result.errors:
            self._append_log(f"HEIC conversion errors: {len(result.errors)}")

    # ------------------------------------------------------------------
    # Shared UI helpers
    # ------------------------------------------------------------------
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
