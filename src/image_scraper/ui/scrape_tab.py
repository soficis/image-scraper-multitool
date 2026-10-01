"""Scrape-tab widget construction and mode gating for the Tk GUI.

Owns the Scrape Images tab: mode/query/sources/output/advanced widgets plus
the search-vs-URL mode toggle. Execution lives in scrape_runner.py; both are
mixed into ScraperApp, so all cross-references resolve via `self`.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk

from image_scraper.adapters.image_converter import available_output_formats
from image_scraper.ui.convert_panel import KEEP_LABEL


class ScrapeTabMixin(tk.Tk):
    """Builds the scrape tab. Mixed into ScraperApp (never instantiated alone)."""

    # Provided by ScraperApp / sibling mixins; declared here for type-checking.
    vars: dict[str, tk.Variable]
    query_label: ttk.Label
    query_entry: ttk.Entry
    scrape_format_combo: ttk.Combobox
    scrape_quality_spin: ttk.Spinbox
    depth_spin: ttk.Spinbox
    bing_check: ttk.Checkbutton
    google_check: ttk.Checkbutton
    pexels_check: ttk.Checkbutton
    pexels_key_hint: ttk.Label
    pixabay_check: ttk.Checkbutton
    pixabay_key_hint: ttk.Label
    openverse_check: ttk.Checkbutton
    scrape_status: ttk.Label
    scrape_start_button: ttk.Button
    scrape_stop_button: ttk.Button
    scrape_open_folder_button: ttk.Button
    sources_frame: ttk.LabelFrame
    output_frame: ttk.LabelFrame
    advanced_frame: ttk.LabelFrame
    advanced_button: ttk.Button
    actions_row: ttk.Frame

    def _choose_output_dir(self) -> None: ...
    def _choose_chromedriver(self) -> None: ...
    def _start_scrape(self) -> None: ...
    def _stop_scrape(self) -> None: ...
    def _open_scrape_folder(self) -> None: ...
    def _fit_height_to_content(self) -> None: ...

    def _build_scrape_tab(self, parent: ttk.Frame) -> None:
        top_frame = ttk.Frame(parent)
        top_frame.pack(fill=tk.X, pady=(0, 8))

        mode_row = ttk.Frame(top_frame)
        mode_row.pack(fill=tk.X, pady=(0, 6))

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
        ).pack(side=tk.LEFT)

        query_input = ttk.Frame(top_frame)
        query_input.pack(fill=tk.X)
        self.query_label = ttk.Label(query_input, text="Search Query")
        self.query_label.pack(side=tk.LEFT, padx=(0, 8))
        self.query_entry = ttk.Entry(query_input, textvariable=self.vars["query"])
        self.query_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.query_entry.bind("<Return>", lambda _e: self._start_scrape())
        ttk.Label(query_input, text="Images:").pack(side=tk.LEFT, padx=(12, 6))
        ttk.Spinbox(
            query_input, from_=1, to=500, textvariable=self.vars["num_images"], width=6
        ).pack(side=tk.LEFT)

        # 1. Sources: engine selection, API credentials, query expansion
        self.sources_frame = ttk.LabelFrame(parent, text="Sources", padding=8)
        self.sources_frame.pack(fill=tk.X, pady=(0, 8))

        engines_row = ttk.Frame(self.sources_frame)
        engines_row.pack(fill=tk.X)
        self.bing_check = ttk.Checkbutton(engines_row, text="Bing", variable=self.vars["bing"])
        self.bing_check.pack(side=tk.LEFT, padx=(0, 16))
        self.google_check = ttk.Checkbutton(
            engines_row, text="Google", variable=self.vars["google"]
        )
        self.google_check.pack(side=tk.LEFT, padx=(0, 16))
        self.openverse_check = ttk.Checkbutton(
            engines_row, text="Openverse", variable=self.vars["openverse"]
        )
        self.openverse_check.pack(side=tk.LEFT, padx=(0, 16))

        pexels_row = ttk.Frame(self.sources_frame)
        pexels_row.pack(fill=tk.X, pady=(6, 0))
        self.pexels_check = ttk.Checkbutton(
            pexels_row, text="Pexels", variable=self.vars["pexels"], width=10
        )
        self.pexels_check.pack(side=tk.LEFT)
        self.pexels_key_hint = ttk.Label(pexels_row, text="", style="Muted.TLabel")
        self.pexels_key_hint.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(pexels_row, text="API key:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(pexels_row, textvariable=self.vars["pexels_api_key"], width=28, show="*").pack(
            side=tk.LEFT
        )

        pixabay_row = ttk.Frame(self.sources_frame)
        pixabay_row.pack(fill=tk.X, pady=(4, 0))
        self.pixabay_check = ttk.Checkbutton(
            pixabay_row, text="Pixabay", variable=self.vars["pixabay"], width=10
        )
        self.pixabay_check.pack(side=tk.LEFT)
        self.pixabay_key_hint = ttk.Label(pixabay_row, text="", style="Muted.TLabel")
        self.pixabay_key_hint.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Label(pixabay_row, text="API key:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(pixabay_row, textvariable=self.vars["pixabay_api_key"], width=28, show="*").pack(
            side=tk.LEFT
        )

        options_row = ttk.Frame(self.sources_frame)
        options_row.pack(fill=tk.X, pady=(6, 0))
        ttk.Checkbutton(
            options_row,
            text="Also search variants (plurals, 'photo', 'wallpaper')",
            variable=self.vars["expand_queries"],
        ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Checkbutton(
            options_row,
            text="Remember API keys (stored as plain text)",
            variable=self.vars["remember_api_keys"],
        ).pack(side=tk.LEFT)

        self.vars["pexels_api_key"].trace_add("write", self._update_api_key_hints)
        self.vars["pixabay_api_key"].trace_add("write", self._update_api_key_hints)
        self._update_api_key_hints()

        # 2. Output: folder, filename preservation, and post-download processing
        self.output_frame = ttk.LabelFrame(parent, text="Output", padding=8)
        self.output_frame.pack(fill=tk.X, pady=(0, 8))

        dest_row = ttk.Frame(self.output_frame)
        dest_row.pack(fill=tk.X)
        ttk.Label(dest_row, text="Folder:").pack(side=tk.LEFT, padx=(0, 6))
        ttk.Entry(dest_row, textvariable=self.vars["output_dir"]).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(dest_row, text="Browse…", command=self._choose_output_dir).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        file_opts = ttk.Frame(self.output_frame)
        file_opts.pack(fill=tk.X, pady=(6, 0))
        ttk.Checkbutton(
            file_opts, text="Keep original filenames", variable=self.vars["keep_filenames"]
        ).pack(side=tk.LEFT, padx=(0, 16))

        convert_row = ttk.Frame(self.output_frame)
        convert_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(convert_row, text="Convert downloads to:").pack(side=tk.LEFT, padx=(0, 6))
        self.scrape_format_combo = ttk.Combobox(
            convert_row,
            textvariable=self.vars["scrape_format"],
            values=[KEEP_LABEL, *[fmt.label for fmt in available_output_formats()]],
            width=20,
            state="readonly",
        )
        self.scrape_format_combo.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(convert_row, text="Quality (1-100):").pack(side=tk.LEFT, padx=(0, 4))
        self.scrape_quality_spin = ttk.Spinbox(
            convert_row, from_=1, to=100, width=5, textvariable=self.vars["scrape_quality"]
        )
        self.scrape_quality_spin.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Label(convert_row, text="Max size:").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Spinbox(
            convert_row, from_=0, to=7680, width=6, textvariable=self.vars["scrape_max_width"]
        ).pack(side=tk.LEFT)
        ttk.Label(convert_row, text="x").pack(side=tk.LEFT, padx=3)
        ttk.Spinbox(
            convert_row, from_=0, to=4320, width=6, textvariable=self.vars["scrape_max_height"]
        ).pack(side=tk.LEFT)

        # 3. Advanced: collapsible section for timeouts, recursion depth, and Google browser settings
        self.advanced_button = ttk.Button(parent, text="▸ Advanced", command=self._toggle_advanced)
        self.advanced_button.pack(anchor=tk.W, pady=(0, 4))

        self.advanced_frame = ttk.LabelFrame(parent, text="Advanced", padding=8)

        adv_content = ttk.Frame(self.advanced_frame)
        adv_content.pack(fill=tk.BOTH, expand=True)

        adv_left = ttk.Frame(adv_content)
        adv_left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))

        ttk.Label(adv_left, text="Bing timeout (s)").grid(row=0, column=0, sticky=tk.W)
        ttk.Spinbox(
            adv_left,
            from_=1.0,
            to=60.0,
            increment=0.5,
            width=8,
            textvariable=self.vars["bing_timeout"],
        ).grid(row=0, column=1, sticky=tk.W, padx=(8, 0))

        ttk.Label(adv_left, text="API timeout (s)").grid(row=1, column=0, sticky=tk.W, pady=(6, 0))
        ttk.Spinbox(
            adv_left,
            from_=1.0,
            to=60.0,
            increment=0.5,
            width=8,
            textvariable=self.vars["api_timeout"],
        ).grid(row=1, column=1, sticky=tk.W, padx=(8, 0), pady=(6, 0))

        ttk.Label(adv_left, text="Follow links N levels deep").grid(
            row=2, column=0, sticky=tk.W, pady=(6, 0)
        )
        self.depth_spin = ttk.Spinbox(
            adv_left, from_=0, to=3, width=8, textvariable=self.vars["recursion_depth"]
        )
        self.depth_spin.grid(row=2, column=1, sticky=tk.W, padx=(8, 0), pady=(6, 0))

        adv_right = ttk.Frame(adv_content)
        adv_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        ttk.Checkbutton(adv_right, text="Show browser", variable=self.vars["show_browser"]).grid(
            row=0, column=0, columnspan=2, sticky=tk.W
        )

        ttk.Label(adv_right, text="Chromedriver path").grid(
            row=1, column=0, sticky=tk.W, pady=(4, 0)
        )
        driver_row = ttk.Frame(adv_right)
        driver_row.grid(row=2, column=0, columnspan=2, sticky=tk.EW)
        ttk.Entry(driver_row, textvariable=self.vars["chromedriver"]).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(driver_row, text="Locate…", command=self._choose_chromedriver).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        ttk.Label(adv_right, text="Min resolution (W x H)").grid(
            row=3, column=0, sticky=tk.W, pady=(4, 0)
        )
        min_res_row = ttk.Frame(adv_right)
        min_res_row.grid(row=4, column=0, sticky=tk.W)
        ttk.Spinbox(
            min_res_row, from_=0, to=7680, width=6, textvariable=self.vars["min_width"]
        ).pack(side=tk.LEFT)
        ttk.Label(min_res_row, text="x").pack(side=tk.LEFT, padx=3)
        ttk.Spinbox(
            min_res_row, from_=0, to=4320, width=6, textvariable=self.vars["min_height"]
        ).pack(side=tk.LEFT)

        ttk.Label(adv_right, text="Max resolution (W x H)").grid(
            row=5, column=0, sticky=tk.W, pady=(4, 0)
        )
        max_res_row = ttk.Frame(adv_right)
        max_res_row.grid(row=6, column=0, sticky=tk.W)
        ttk.Spinbox(
            max_res_row, from_=0, to=7680, width=6, textvariable=self.vars["max_width"]
        ).pack(side=tk.LEFT)
        ttk.Label(max_res_row, text="x").pack(side=tk.LEFT, padx=3)
        ttk.Spinbox(
            max_res_row, from_=0, to=4320, width=6, textvariable=self.vars["max_height"]
        ).pack(side=tk.LEFT)

        ttk.Label(adv_right, text="Give up after N scrolls with no new images").grid(
            row=7, column=0, sticky=tk.W, pady=(4, 0)
        )
        ttk.Spinbox(adv_right, from_=1, to=100, width=6, textvariable=self.vars["max_missed"]).grid(
            row=7, column=1, sticky=tk.W, padx=(8, 0), pady=(4, 0)
        )

        # 4. Actions: status, start and stop buttons
        self.actions_row = ttk.Frame(parent)
        self.actions_row.pack(fill=tk.X, pady=(10, 0))
        self.scrape_status = ttk.Label(self.actions_row, text="● Ready")
        self.scrape_status.pack(side=tk.LEFT)

        self.scrape_stop_button = ttk.Button(
            self.actions_row, text="Stop", command=self._stop_scrape, state="disabled"
        )
        self.scrape_stop_button.pack(side=tk.RIGHT)
        self.scrape_start_button = ttk.Button(
            self.actions_row,
            text="Start Scraping",
            command=self._start_scrape,
            style="Accent.TButton",
        )
        self.scrape_start_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.scrape_open_folder_button = ttk.Button(
            self.actions_row,
            text="Open folder",
            command=self._open_scrape_folder,
            state="disabled",
        )
        self.scrape_open_folder_button.pack(side=tk.RIGHT, padx=(0, 8))

        self._update_advanced_visibility()
        self._on_mode_changed()

    def _toggle_advanced(self) -> None:
        self.vars["advanced_open"].set(not bool(self.vars["advanced_open"].get()))
        self._update_advanced_visibility()
        self._fit_height_to_content()

    def _update_advanced_visibility(self) -> None:
        if bool(self.vars["advanced_open"].get()):
            self.advanced_frame.pack(fill=tk.X, pady=(0, 8), before=self.actions_row)
            self.advanced_button.configure(text="▾ Advanced")
        else:
            self.advanced_frame.pack_forget()
            self.advanced_button.configure(text="▸ Advanced")

    def _on_mode_changed(self) -> None:
        is_url_mode = self.vars["mode"].get() == "url"
        self.query_label.configure(text="Target URL" if is_url_mode else "Search Query")

        if is_url_mode:
            self.bing_check.state(["disabled"])
            self.google_check.state(["disabled"])
            self.pexels_check.state(["disabled"])
            self.pixabay_check.state(["disabled"])
            self.openverse_check.state(["disabled"])
            self.depth_spin.state(["!disabled"])
        else:
            self.bing_check.state(["!disabled"])
            self.google_check.state(["!disabled"])
            self.pexels_check.state(["!disabled"])
            self.pixabay_check.state(["!disabled"])
            self.openverse_check.state(["!disabled"])
            self.depth_spin.state(["disabled"])

    def _update_api_key_hints(self, *_args: object) -> None:
        has_pexels = bool(
            self.vars["pexels_api_key"].get().strip()
            or os.environ.get("PEXELS_API_KEY", "").strip()
        )
        self.pexels_key_hint.configure(text="" if has_pexels else "(needs key)")

        has_pixabay = bool(
            self.vars["pixabay_api_key"].get().strip()
            or os.environ.get("PIXABAY_API_KEY", "").strip()
        )
        self.pixabay_key_hint.configure(text="" if has_pixabay else "(needs key)")
