#!/usr/bin/env python3
# Image Scraper Multitool - Graphical User Interface
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
Graphical front-end for the image scraper multitool.

This GUI wraps the command-line helper to provide an approachable, modern-feeling
workflow for collecting images from Bing and Google. It relies on the existing
`image_scraper_multitool` module for the heavy lifting.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import List, Sequence

import image_scraper_multitool as multitool


@dataclass
class GuiOptions:
    query: str
    num_images: int
    engines: Sequence[str]
    keep_filenames: bool
    convert_webp: bool
    output_dir: Path
    bing_timeout: float
    chromedriver: Path
    headless: bool
    min_resolution: Sequence[int]
    max_resolution: Sequence[int]
    max_missed: int
    compression_quality: int
    resize_width: int
    resize_height: int
    recursion_depth: int


class TkQueueHandler(logging.Handler):
    """Route log records into a thread-safe queue for the Tk loop."""

    def __init__(self, destination: queue.Queue[str]) -> None:
        super().__init__()
        self.destination = destination

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            self.destination.put(message)
        except Exception:  # pylint: disable=broad-except
            self.handleError(record)


class ScraperApp(tk.Tk):
    """Main application window."""

    POLL_INTERVAL_MS = 125

    def __init__(self) -> None:
        super().__init__()
        self.title("Image Scraper Multitool")
        self.geometry("940x760")
        self.minsize(880, 700)
        self.configure(background="#0f1419")

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.queue_handler = TkQueueHandler(self.log_queue)
        self.queue_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(self.queue_handler)
        logging.getLogger().setLevel(logging.INFO)

        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()

        self._build_style()
        self.vars = self._init_variables()
        self._build_layout()

        self.after(self.POLL_INTERVAL_MS, self._process_log_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            if "clam" in style.theme_names():
                style.theme_use("clam")
            elif "alt" in style.theme_names():
                style.theme_use("alt")
        except tk.TclError:
            pass

        # Dark mode color palette
        bg_dark = "#1a1f2e"
        bg_darker = "#0f1419"
        bg_card = "#232938"
        bg_input = "#2d3548"
        fg_primary = "#e6e9ef"
        fg_secondary = "#9ca3af"
        accent_blue = "#3b82f6"
        accent_blue_hover = "#2563eb"
        accent_blue_active = "#1d4ed8"
        border_color = "#3d4556"

        # Header styles
        style.configure("Header.TLabel", 
                       font=("Segoe UI", 22, "bold"), 
                       foreground="#ffffff",
                       background=bg_card)
        style.configure("SubHeader.TLabel", 
                       font=("Segoe UI", 10), 
                       foreground=fg_secondary,
                       background=bg_card)
        
        # Frame styles
        style.configure("Card.TFrame", background=bg_card, relief="flat")
        style.configure("TFrame", background=bg_card)
        
        # Label styles
        style.configure("TLabel", 
                       background=bg_card, 
                       foreground=fg_primary,
                       font=("Segoe UI", 9))
        
        # Entry styles
        style.configure("TEntry",
                       fieldbackground=bg_input,
                       background=bg_input,
                       foreground=fg_primary,
                       bordercolor=border_color,
                       lightcolor=border_color,
                       darkcolor=border_color,
                       insertcolor=fg_primary)
        style.map("TEntry",
                 fieldbackground=[("readonly", bg_input), ("disabled", bg_darker)],
                 foreground=[("disabled", fg_secondary)])
        
        # Spinbox styles
        style.configure("TSpinbox",
                       fieldbackground=bg_input,
                       background=bg_input,
                       foreground=fg_primary,
                       bordercolor=border_color,
                       arrowcolor=fg_primary,
                       insertcolor=fg_primary)
        
        # Button styles
        style.configure("TButton",
                       background=bg_input,
                       foreground=fg_primary,
                       bordercolor=border_color,
                       focuscolor="none",
                       font=("Segoe UI", 9))
        style.map("TButton",
                 background=[("active", "#3d4556"), ("pressed", bg_darker)],
                 foreground=[("disabled", fg_secondary)])
        
        # Primary button (Start Scraping)
        style.configure("Primary.TButton",
                       background=accent_blue,
                       foreground="#ffffff",
                       bordercolor=accent_blue,
                       focuscolor="none",
                       font=("Segoe UI", 10, "bold"),
                       padding=(20, 10))
        style.map("Primary.TButton",
                 background=[("active", accent_blue_hover), 
                           ("pressed", accent_blue_active),
                           ("disabled", "#374151")],
                 foreground=[("disabled", "#6b7280")],
                 bordercolor=[("active", accent_blue_hover)])
        
        # Checkbutton styles
        style.configure("TCheckbutton",
                       background=bg_card,
                       foreground=fg_primary,
                       font=("Segoe UI", 9))
        style.map("TCheckbutton",
                 background=[("active", bg_card)],
                 foreground=[("disabled", fg_secondary)])
        
        # LabelFrame styles
        style.configure("TLabelframe",
                       background=bg_card,
                       foreground=fg_primary,
                       bordercolor=border_color,
                       relief="solid",
                       borderwidth=1)
        style.configure("TLabelframe.Label",
                       background=bg_card,
                       foreground=fg_primary,
                       font=("Segoe UI", 9, "bold"))
        
        # Status label
        style.configure("Status.TLabel",
                       font=("Segoe UI", 10),
                       foreground=accent_blue,
                       background=bg_card)

    def _init_variables(self) -> dict[str, tk.Variable]:
        # Choose a sensible default chromedriver name per-platform
        driver_name = "chromedriver.exe" if os.name == "nt" else "chromedriver"
        return {
            "query": tk.StringVar(value=""),
            "num_images": tk.IntVar(value=10),
            "bing": tk.BooleanVar(value=True),
            "google": tk.BooleanVar(value=False),
            "keep_filenames": tk.BooleanVar(value=False),
            "convert_webp": tk.BooleanVar(value=False),
            "output_dir": tk.StringVar(value=str(Path.cwd() / "downloads")),
            "bing_timeout": tk.DoubleVar(value=15.0),
            "chromedriver": tk.StringVar(
                value=str((Path.cwd() / "webdriver" / driver_name).resolve())
            ),
            "show_browser": tk.BooleanVar(value=False),
            "min_width": tk.IntVar(value=0),
            "min_height": tk.IntVar(value=0),
            "max_width": tk.IntVar(value=1920),
            "max_height": tk.IntVar(value=1080),
            "max_missed": tk.IntVar(value=10),
            "compression_quality": tk.IntVar(value=0),
            "resize_width": tk.IntVar(value=0),
            "resize_width": tk.IntVar(value=0),
            "resize_height": tk.IntVar(value=0),
            "search_mode": tk.StringVar(value="search"),
            "recursion_depth": tk.IntVar(value=0),
        }

    def _build_layout(self) -> None:
        # Main container with dark background
        main_container = ttk.Frame(self, style="Card.TFrame")
        main_container.pack(fill=tk.BOTH, expand=True)

        # 1. Fixed Header
        header_frame = ttk.Frame(main_container, padding=(20, 20, 20, 10))
        header_frame.pack(fill=tk.X, side=tk.TOP)
        
        header = ttk.Label(header_frame, text="🖼️ Image Scraper", style="Header.TLabel")
        subheader = ttk.Label(
            header_frame,
            text="Search Bing and Google Images from a single, streamlined interface.",
            style="SubHeader.TLabel",
        )
        header.pack(anchor=tk.W)
        subheader.pack(anchor=tk.W, pady=(4, 0))

        # 2. Fixed Footer (Action Bar + Logs)
        # We pack this BEFORE the middle section so it stays at the bottom
        footer_frame = ttk.Frame(main_container, padding=(20, 10, 20, 20))
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # Action buttons (Start/Status) in footer
        action_frame = ttk.Frame(footer_frame)
        action_frame.pack(fill=tk.X, pady=(0, 10))

        self.status_label = ttk.Label(action_frame, text="● Ready", style="Status.TLabel")
        self.status_label.pack(side=tk.LEFT, pady=8)

        self.start_button = ttk.Button(
            action_frame, 
            text="Start Scraping", 
            style="Primary.TButton", 
            command=self._on_start
        )
        self.start_button.pack(side=tk.RIGHT, pady=4)

        self.stop_button = ttk.Button(
            action_frame, 
            text="Stop", 
            style="TButton", 
            command=self._on_stop,
            state="disabled"
        )
        self.stop_button.pack(side=tk.RIGHT, padx=(0, 8), pady=4)

        # Log output in footer
        log_expander = ttk.LabelFrame(footer_frame, text="Activity Log", padding=(10, 5))
        log_expander.pack(fill=tk.X)
        
        self.log_widget = scrolledtext.ScrolledText(
            log_expander, 
            height=6, # Keep it relatively short so it doesn't eat screen space
            font=("Consolas", 10),
            bg="#1a1f2e",
            fg="#e6e9ef",
            insertbackground="#3b82f6",
            selectbackground="#3b82f6",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            wrap=tk.WORD
        )
        self.log_widget.pack(fill=tk.BOTH, expand=True, pady=5)
        self.log_widget.configure(state=tk.DISABLED)

        # 3. Scrollable Middle Section (Settings)
        # We use a Canvas + Scrollbar approach
        canvas_container = ttk.Frame(main_container)
        canvas_container.pack(fill=tk.BOTH, expand=True, padx=20)

        canvas = tk.Canvas(canvas_container, bg="#232938", highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_container, orient="vertical", command=canvas.yview)
        
        # The frame that will hold the actual form
        self.scrollable_frame = ttk.Frame(canvas, style="Card.TFrame")
        
        # Configure scrolling
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=canvas.winfo_reqwidth())
        
        # Link canvas width to frame width to avoid horizontal scrolling if possible,
        # but we need to update the window width when canvas resizes.
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas.find_withtag("all")[0], width=event.width)
        
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Now build the form inside scrollable_frame
        form = ttk.Frame(self.scrollable_frame, padding=(0, 0, 10, 20)) # Padding inside the scroll area
        form.pack(fill=tk.BOTH, expand=True)

        # --- Content moved from original layout ---

        # Mode Selection
        mode_frame = ttk.Frame(form)
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(mode_frame, text="Mode", font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT, padx=(0, 16))
        
        ttk.Radiobutton(
            mode_frame, 
            text="Keyword Search", 
            variable=self.vars["search_mode"], 
            value="search",
            command=self._on_mode_change
        ).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Radiobutton(
            mode_frame, 
            text="Page URL", 
            variable=self.vars["search_mode"], 
            value="url",
            command=self._on_mode_change
        ).pack(side=tk.LEFT, padx=(0, 20))

        # Depth control (Custom URL only)
        self.depth_frame = ttk.Frame(mode_frame)
        self.depth_frame.pack(side=tk.LEFT)
        ttk.Label(self.depth_frame, text="Depth:", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Spinbox(
            self.depth_frame, 
            from_=0, 
            to=3, 
            width=3, 
            textvariable=self.vars["recursion_depth"]
        ).pack(side=tk.LEFT)

        # Search Query Row
        query_frame = ttk.Frame(form)
        query_frame.pack(fill=tk.X, pady=(0, 16))
        
        query_label_frame = ttk.Frame(query_frame)
        query_label_frame.pack(fill=tk.X, pady=(0, 6))
        self.query_label = ttk.Label(query_label_frame, text="Search Query", font=("Segoe UI", 9, "bold"))
        self.query_label.pack(side=tk.LEFT)
        
        query_input_frame = ttk.Frame(query_frame)
        query_input_frame.pack(fill=tk.X)
        query_entry = ttk.Entry(query_input_frame, textvariable=self.vars["query"], font=("Segoe UI", 10))
        query_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        
        # Number of images spinbox on same row
        ttk.Label(query_input_frame, text="Images", font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=(16, 6))
        num_spin = ttk.Spinbox(query_input_frame, from_=1, to=500, textvariable=self.vars["num_images"], width=8)
        num_spin.pack(side=tk.LEFT, ipady=3)

        # Output Directory Row
        output_frame = ttk.Frame(form)
        output_frame.pack(fill=tk.X, pady=(0, 16))
        
        ttk.Label(output_frame, text="Output Directory", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(0, 6))
        
        output_input_frame = ttk.Frame(output_frame)
        output_input_frame.pack(fill=tk.X)
        output_entry = ttk.Entry(output_input_frame, textvariable=self.vars["output_dir"], font=("Segoe UI", 9))
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        browse_btn = ttk.Button(output_input_frame, text="Browse…", command=self._choose_output_dir)
        browse_btn.pack(side=tk.LEFT, padx=(8, 0), ipady=2)

        # Two-column layout for engine options
        options_container = ttk.Frame(form)
        options_container.pack(fill=tk.BOTH, expand=True)
        
        # Left column - Engine Selection & Bing Options
        left_column = ttk.Frame(options_container)
        left_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        
        # Engine selection
        self.engines_frame = ttk.LabelFrame(left_column, text="Engines", padding=12)
        self.engines_frame.pack(fill=tk.X, pady=(0, 12))
        
        engine_checks = ttk.Frame(self.engines_frame)
        engine_checks.pack(fill=tk.X)
        ttk.Checkbutton(engine_checks, text="Bing", variable=self.vars["bing"]).pack(side=tk.LEFT, padx=(0, 20))
        ttk.Checkbutton(engine_checks, text="Google", variable=self.vars["google"]).pack(side=tk.LEFT)
        
        ttk.Checkbutton(
            self.engines_frame, 
            text="Keep original filenames", 
            variable=self.vars["keep_filenames"]
        ).pack(anchor=tk.W, pady=(8, 0))
        ttk.Checkbutton(
            self.engines_frame,
            text="Convert .webp to .jpg",
            variable=self.vars["convert_webp"],
        ).pack(anchor=tk.W, pady=(4, 0))

        # Bing Options
        bing_frame = ttk.LabelFrame(left_column, text="Bing Options", padding=12)
        bing_frame.pack(fill=tk.X)
        
        bing_timeout_frame = ttk.Frame(bing_frame)
        bing_timeout_frame.pack(fill=tk.X)
        ttk.Label(bing_timeout_frame, text="Timeout (seconds)").pack(side=tk.LEFT)
        ttk.Spinbox(
            bing_timeout_frame, 
            from_=5.0, 
            to=60.0, 
            increment=0.5, 
            textvariable=self.vars["bing_timeout"], 
            width=10
        ).pack(side=tk.LEFT, padx=(8, 0), ipady=2)

        # Right column - Google Options
        right_column = ttk.Frame(options_container)
        right_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        
        # Google settings
        google_frame = ttk.LabelFrame(right_column, text="Google Options", padding=12)
        google_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(google_frame, text="Chromedriver Path", font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(0, 6))
        
        chromedriver_frame = ttk.Frame(google_frame)
        chromedriver_frame.pack(fill=tk.X, pady=(0, 10))
        chromedriver_entry = ttk.Entry(chromedriver_frame, textvariable=self.vars["chromedriver"], font=("Segoe UI", 9))
        chromedriver_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        ttk.Button(chromedriver_frame, text="Locate…", command=self._choose_chromedriver).pack(
            side=tk.LEFT, padx=(8, 0), ipady=2
        )

        ttk.Checkbutton(
            google_frame,
            text="Show browser while scraping",
            variable=self.vars["show_browser"],
        ).pack(anchor=tk.W, pady=(0, 10))

        # Resolution settings
        resolution_label = ttk.Label(google_frame, text="Resolution Limits", font=("Segoe UI", 9))
        resolution_label.pack(anchor=tk.W, pady=(0, 6))
        
        resolution_frame = ttk.Frame(google_frame)
        resolution_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Min resolution
        min_res_frame = ttk.Frame(resolution_frame)
        min_res_frame.pack(side=tk.LEFT, padx=(0, 16))
        ttk.Label(min_res_frame, text="Min", foreground="#9ca3af").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Spinbox(min_res_frame, from_=0, to=7680, textvariable=self.vars["min_width"], width=6).pack(side=tk.LEFT)
        ttk.Label(min_res_frame, text="×", foreground="#9ca3af").pack(side=tk.LEFT, padx=3)
        ttk.Spinbox(min_res_frame, from_=0, to=4320, textvariable=self.vars["min_height"], width=6).pack(side=tk.LEFT)
        
        # Max resolution
        max_res_frame = ttk.Frame(resolution_frame)
        max_res_frame.pack(side=tk.LEFT)
        ttk.Label(max_res_frame, text="Max", foreground="#9ca3af").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Spinbox(max_res_frame, from_=0, to=7680, textvariable=self.vars["max_width"], width=6).pack(side=tk.LEFT)
        ttk.Label(max_res_frame, text="×", foreground="#9ca3af").pack(side=tk.LEFT, padx=3)
        ttk.Spinbox(max_res_frame, from_=0, to=4320, textvariable=self.vars["max_height"], width=6).pack(side=tk.LEFT)

        # Max consecutive misses
        misses_frame = ttk.Frame(google_frame)
        misses_frame.pack(fill=tk.X)
        ttk.Label(misses_frame, text="Max consecutive misses").pack(side=tk.LEFT)
        ttk.Spinbox(
            misses_frame, 
            from_=1, 
            to=50, 
            textvariable=self.vars["max_missed"], 
            width=8
        ).pack(side=tk.LEFT, padx=(8, 0), ipady=2)

        # Post-Processing (Compression)
        post_frame = ttk.LabelFrame(right_column, text="Post-Processing", padding=12)
        post_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        # Compression Quality
        quality_frame = ttk.Frame(post_frame)
        quality_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(quality_frame, text="JPEG Quality (1-100, 0=None)").pack(side=tk.LEFT)
        ttk.Spinbox(
            quality_frame, 
            from_=0, 
            to=100, 
            textvariable=self.vars["compression_quality"], 
            width=8
        ).pack(side=tk.LEFT, padx=(8, 0))

        # Resize Options
        resize_label = ttk.Label(post_frame, text="Force Resize (Optional)", font=("Segoe UI", 9))
        resize_label.pack(anchor=tk.W, pady=(0, 6))

        resize_frame = ttk.Frame(post_frame)
        resize_frame.pack(fill=tk.X)
        
        ttk.Label(resize_frame, text="W:", foreground="#9ca3af").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Spinbox(resize_frame, from_=0, to=7680, textvariable=self.vars["resize_width"], width=6).pack(side=tk.LEFT)
        
        ttk.Label(resize_frame, text="H:", foreground="#9ca3af").pack(side=tk.LEFT, padx=(8, 4))
        ttk.Spinbox(resize_frame, from_=0, to=4320, textvariable=self.vars["resize_height"], width=6).pack(side=tk.LEFT)

        # Initialize UI state logic
        self._on_mode_change()

        # Mousewheel scrolling (Functional for windows/linux roughly)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.scrollable_frame.bind("<Enter>", lambda _: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.scrollable_frame.bind("<Leave>", lambda _: canvas.unbind_all("<MouseWheel>"))

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _choose_output_dir(self) -> None:
        initial = Path(self.vars["output_dir"].get()).expanduser()
        selected = filedialog.askdirectory(initialdir=initial if initial.exists() else None)
        if selected:
            self.vars["output_dir"].set(selected)

            self.vars["output_dir"].set(selected)

    def _on_mode_change(self) -> None:
        mode = self.vars["search_mode"].get()
        if mode == "url":
            self.query_label.configure(text="Target URL")
            # Disable engine selection for generic URL
            for child in self.engines_frame.winfo_children():
                child.state(["disabled"])
            # Enable depth
            for child in self.depth_frame.winfo_children():
                child.state(["!disabled"])
        else:
            self.query_label.configure(text="Search Query")
            for child in self.engines_frame.winfo_children():
                child.state(["!disabled"])
            # Disable depth
            for child in self.depth_frame.winfo_children():
                child.state(["disabled"])

    def _choose_chromedriver(self) -> None:
        initial = Path(self.vars["chromedriver"].get()).expanduser()
        selected = filedialog.askopenfilename(
            title="Select chromedriver executable",
            initialdir=initial.parent if initial.exists() else None,
            filetypes=[("Chromedriver", "chromedriver*"), ("Executables", "*.exe"), ("All files", "*.*")],
        )
        if selected:
            self.vars["chromedriver"].set(selected)

    def _on_start(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Scraper busy", "A scraping run is already in progress.")
            return

        options = self._compile_options()
        if options is None:
            return

        self._append_log("Starting scraping run…")
        self.status_label.configure(text="● Running…")
        self.start_button.state(["disabled"])
        self.stop_button.state(["!disabled"])
        self.stop_event.clear()
        self.worker = threading.Thread(target=self._run_scraper, args=(options,), daemon=True)
        self.worker.start()

    def _on_stop(self) -> None:
        """Signal the scraper thread to stop gracefully."""
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
            self._append_log("Stop requested. Finishing current download...")
            self.status_label.configure(text="● Stopping…")
            self.stop_button.state(["disabled"])

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askokcancel("Quit", "A scraping run is still in progress. Quit anyway?"):
                return
            self.stop_event.set()
        logging.getLogger().removeHandler(self.queue_handler)
        self.destroy()

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------
    def _compile_options(self) -> GuiOptions | None:
        query = self.vars["query"].get().strip()
        if not query:
            messagebox.showwarning("Missing query", "Enter a search query to continue.")
            return None

        engines: List[str] = []
        if self.vars["bing"].get():
            engines.append("bing")
        if self.vars["google"].get():
            engines.append("google")

        if self.vars["search_mode"].get() == "url":
            engines = ["custom"]
        elif not engines:
            messagebox.showwarning("No engines selected", "Choose at least one search engine.")
            return None

        try:
            num_images = int(self.vars["num_images"].get())
            if num_images <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid number", "Images per engine must be a positive integer.")
            return None

        try:
            timeout = float(self.vars["bing_timeout"].get())
            if timeout <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid timeout", "Bing timeout must be a positive number.")
            return None

        output_dir = Path(self.vars["output_dir"].get()).expanduser()
        chromedriver = Path(self.vars["chromedriver"].get()).expanduser()

        # No upfront warning: Google path will be auto-downloaded if missing.

        min_resolution = (max(self.vars["min_width"].get(), 0), max(self.vars["min_height"].get(), 0))
        max_resolution = (max(self.vars["max_width"].get(), 0), max(self.vars["max_height"].get(), 0))

        return GuiOptions(
            query=query,
            num_images=num_images,
            engines=engines,
            keep_filenames=self.vars["keep_filenames"].get(),
            convert_webp=self.vars["convert_webp"].get(),
            output_dir=output_dir,
            bing_timeout=timeout,
            chromedriver=chromedriver,
            headless=not self.vars["show_browser"].get(),
            min_resolution=min_resolution,
            max_resolution=max_resolution,
            max_missed=max(self.vars["max_missed"].get(), 1),
            compression_quality=max(0, min(self.vars["compression_quality"].get(), 100)),
            resize_width=max(0, self.vars["resize_width"].get()),
            resize_height=max(0, self.vars["resize_height"].get()),
            recursion_depth=max(0, self.vars["recursion_depth"].get()),
        )

    def _run_scraper(self, options: GuiOptions) -> None:
        results: List[multitool.ScrapeResult] = []
        errors: List[str] = []
        for engine in options.engines:
            if self.stop_event.is_set():
                self._append_log("Scraping run cancelled.")
                break

            try:
                if engine == "bing":
                    destination = options.output_dir / "bing" / multitool.slugify(options.query)
                    result = multitool.scrape_with_bing(
                        options.query,
                        limit=options.num_images,
                        destination=destination,
                        keep_filenames=options.keep_filenames,
                        convert_webp=options.convert_webp,
                        timeout=options.bing_timeout,
                        compression_quality=options.compression_quality,
                        resize_width=options.resize_width,
                        resize_height=options.resize_height,
                        stop_event=self.stop_event,
                    )
                elif engine == "google":
                    destination = options.output_dir / "google" / multitool.slugify(options.query)
                    result = multitool.scrape_with_google(
                        options.query,
                        limit=options.num_images,
                        destination=destination,
                        keep_filenames=options.keep_filenames,
                        convert_webp=options.convert_webp,
                        chromedriver_path=options.chromedriver,
                        headless=options.headless,
                        min_resolution=options.min_resolution,
                        max_resolution=options.max_resolution,
                        max_missed=options.max_missed,
                        compression_quality=options.compression_quality,
                        resize_width=options.resize_width,
                        resize_height=options.resize_height,
                        stop_event=self.stop_event,
                    )
                elif engine == "custom":
                    destination = options.output_dir / "custom_url" / multitool.slugify(options.query)
                    result = multitool.scrape_custom_url(
                        options.query,
                        limit=options.num_images,
                        destination=destination,
                        keep_filenames=options.keep_filenames,
                        convert_webp=options.convert_webp,
                        timeout=options.bing_timeout,
                        compression_quality=options.compression_quality,
                        resize_width=options.resize_width,
                        resize_height=options.resize_height,
                        headless=options.headless,
                        recursion_depth=options.recursion_depth,
                        stop_event=self.stop_event,
                    )
                else:
                    raise ValueError(f"Unsupported engine: {engine}")

                results.append(result)
            except Exception as error:  # pylint: disable=broad-except
                logging.getLogger().exception("Scraping via %s failed: %s", engine, error)
                errors.append(f"{engine.title()} run failed: {error}")
                break

        self.after(0, self._on_run_complete, results, errors)

    def _on_run_complete(
        self, results: Sequence[multitool.ScrapeResult], errors: Sequence[str]
    ) -> None:
        self.start_button.state(["!disabled"])
        self.stop_button.state(["disabled"])
        if results:
            self.status_label.configure(text="✓ Completed")
            for result in results:
                self._append_log(
                    f"{result.engine.title()}: requested={result.requested} saved={result.saved} skipped={result.skipped} -> {result.destination}"
                )
                if result.errors:
                    self._append_log(f"{result.engine.title()} encountered {len(result.errors)} download errors")
        else:
            self.status_label.configure(text="● Ready")

        for error in errors:
            messagebox.showerror("Scraper error", error)

    def _process_log_queue(self) -> None:
        try:
            while True:
                message = self.log_queue.get_nowait()
                self._append_log(message)
        except queue.Empty:
            pass
        finally:
            self.after(self.POLL_INTERVAL_MS, self._process_log_queue)

    def _append_log(self, message: str) -> None:
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, message + "\n")
        self.log_widget.configure(state=tk.DISABLED)
        self.log_widget.see(tk.END)


def main() -> None:
    app = ScraperApp()
    app.mainloop()


if __name__ == "__main__":
    main()
