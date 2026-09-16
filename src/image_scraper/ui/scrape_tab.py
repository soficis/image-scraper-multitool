"""Scrape-tab widget construction and mode gating for the Tk GUI.

Owns the Scrape Images tab: mode/query/output/engines/settings widgets plus
the search-vs-URL mode toggle. Execution lives in scrape_runner.py; both are
mixed into ScraperApp, so all cross-references resolve via `self`.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ScrapeTabMixin(tk.Tk):
    """Builds the scrape tab. Mixed into ScraperApp (never instantiated alone)."""

    # Provided by ScraperApp / sibling mixins; declared here for type-checking.
    vars: dict[str, tk.Variable]
    query_label: ttk.Label
    depth_spin: ttk.Spinbox
    bing_check: ttk.Checkbutton
    google_check: ttk.Checkbutton
    pexels_check: ttk.Checkbutton
    pixabay_check: ttk.Checkbutton
    scrape_status: ttk.Label
    scrape_start_button: ttk.Button
    scrape_stop_button: ttk.Button

    def _choose_output_dir(self) -> None: ...
    def _choose_chromedriver(self) -> None: ...
    def _start_scrape(self) -> None: ...
    def _stop_scrape(self) -> None: ...

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
        self.pexels_check = ttk.Checkbutton(
            engines_row, text="Pexels", variable=self.vars["pexels"]
        )
        self.pixabay_check = ttk.Checkbutton(
            engines_row, text="Pixabay", variable=self.vars["pixabay"]
        )
        self.bing_check.pack(side=tk.LEFT, padx=(0, 16))
        self.google_check.pack(side=tk.LEFT, padx=(0, 16))
        self.pexels_check.pack(side=tk.LEFT, padx=(0, 16))
        self.pixabay_check.pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(
            engines_row, text="Expand queries", variable=self.vars["expand_queries"]
        ).pack(side=tk.LEFT, padx=(0, 16))
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

        ttk.Label(left, text="Pexels API key").grid(row=4, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Entry(left, textvariable=self.vars["pexels_api_key"], width=18, show="*").grid(
            row=4, column=1, sticky=tk.W, padx=(8, 0), pady=(6, 0)
        )

        ttk.Label(left, text="Pixabay API key").grid(row=5, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Entry(left, textvariable=self.vars["pixabay_api_key"], width=18, show="*").grid(
            row=5, column=1, sticky=tk.W, padx=(8, 0), pady=(6, 0)
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

    def _on_mode_changed(self) -> None:
        is_url_mode = self.vars["mode"].get() == "url"
        self.query_label.configure(text="Target URL" if is_url_mode else "Search Query")

        if is_url_mode:
            self.bing_check.state(["disabled"])
            self.google_check.state(["disabled"])
            self.pexels_check.state(["disabled"])
            self.pixabay_check.state(["disabled"])
            self.depth_spin.state(["!disabled"])
        else:
            self.bing_check.state(["!disabled"])
            self.google_check.state(["!disabled"])
            self.pexels_check.state(["!disabled"])
            self.pixabay_check.state(["!disabled"])
            self.depth_spin.state(["disabled"])
