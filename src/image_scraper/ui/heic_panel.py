"""HEIC converter tab for the Tk GUI: widgets plus background conversion flow.

Mixed into ScraperApp; shares only the log helper with the shell.
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from image_scraper.app.heic import convert_heic_batch
from image_scraper.domain.models import BatchConversionResult


@dataclass(frozen=True)
class HeicRequest:
    input_paths: list[Path]
    output_dir: Path
    output_format: str
    quality: int


class HeicPanelMixin(tk.Tk):
    """Builds and runs the HEIC tab. Mixed into ScraperApp (never alone)."""

    # Provided by ScraperApp; declared here for type-checking.
    vars: dict[str, tk.Variable]
    heic_count_label: ttk.Label
    heic_output_entry: ttk.Entry
    heic_output_browse: ttk.Button
    heic_status: ttk.Label
    heic_start_button: ttk.Button
    heic_stop_button: ttk.Button
    heic_thread: threading.Thread | None
    heic_stop_event: threading.Event

    def _append_log(self, message: str) -> None: ...

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

    def _on_heic_output_toggle(self) -> None:
        use_source = self.vars["heic_use_source_dir"].get()
        if use_source:
            self.heic_output_entry.configure(state="disabled")
            self.heic_output_browse.configure(state="disabled")
        else:
            self.heic_output_entry.configure(state="normal")
            self.heic_output_browse.configure(state="normal")

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
