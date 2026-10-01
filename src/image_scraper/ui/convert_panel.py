"""Convert & Compress tab for the Tk GUI: widgets plus background conversion flow.

Mixed into ScraperApp; shares only the log helper with the shell.
"""

from __future__ import annotations

import threading
import tkinter as tk
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from image_scraper.adapters.image_converter import (
    KEEP_FORMAT,
    ConversionOptions,
    available_output_formats,
    collect_images,
    supported_input_extensions,
)
from image_scraper.app.convert import convert_image_batch, summarize_conversion
from image_scraper.domain.models import BatchConversionResult
from image_scraper.ui.platform_open import open_in_file_manager

KEEP_LABEL = "Keep original format"
MAX_LOGGED_ERRORS = 25


@dataclass(frozen=True)
class ConvertRequest:
    input_paths: list[Path]
    options: ConversionOptions


class ConvertPanelMixin(tk.Tk):
    """Builds and runs the Convert & Compress tab. Mixed into ScraperApp (never alone)."""

    # Provided by ScraperApp; declared here for type-checking.
    vars: dict[str, tk.Variable]
    theme: Any
    convert_count_label: ttk.Label
    convert_listbox: tk.Listbox
    convert_remove_button: ttk.Button
    convert_output_entry: ttk.Entry
    convert_output_browse: ttk.Button
    convert_quality_spin: ttk.Spinbox
    convert_lossless_check: ttk.Checkbutton
    convert_status: ttk.Label
    convert_start_button: ttk.Button
    convert_stop_button: ttk.Button
    convert_open_folder_button: ttk.Button
    convert_thread: threading.Thread | None
    convert_stop_event: threading.Event
    _last_convert_folder: Path | None

    def _append_log(self, message: str) -> None: ...

    def post_to_ui(self, callback: Callable[..., None], *args: Any) -> None: ...

    def _build_convert_tab(self, parent: ttk.Frame) -> None:
        self._convert_extensions = supported_input_extensions()
        self._convert_formats = {fmt.label: fmt for fmt in available_output_formats()}
        self._count_generation = 0

        files_box = ttk.LabelFrame(parent, text="Input images", padding=8)
        files_box.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            files_box,
            text=(
                "Folders are scanned recursively. Reads JPEG, PNG, WebP, AVIF, HEIC, "
                "TIFF, GIF, BMP, ICO and more. Originals are never modified."
            ),
        ).pack(anchor=tk.W)

        controls = ttk.Frame(files_box)
        controls.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(controls, text="Browse Files…", command=self._browse_convert_files).pack(
            side=tk.LEFT
        )
        ttk.Button(controls, text="Browse Folder…", command=self._browse_convert_folder).pack(
            side=tk.LEFT, padx=(8, 0)
        )
        ttk.Button(controls, text="Clear", command=self._clear_convert_paths).pack(side=tk.RIGHT)
        self.convert_remove_button = ttk.Button(
            controls, text="Remove selected", command=self._remove_selected_convert_path
        )
        self.convert_remove_button.pack(side=tk.RIGHT, padx=(0, 6))

        list_frame = ttk.Frame(files_box)
        list_frame.pack(fill=tk.X, pady=(8, 0))
        self.convert_listbox = tk.Listbox(
            list_frame,
            height=5,
            selectmode=tk.EXTENDED,
            exportselection=False,
        )
        self.convert_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True)
        scrollbar = ttk.Scrollbar(
            list_frame, orient=tk.VERTICAL, command=self.convert_listbox.yview
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.convert_listbox.configure(yscrollcommand=scrollbar.set)
        if hasattr(self, "theme"):
            self.theme.register_listbox(self.convert_listbox)
        self.convert_listbox.bind("<Delete>", lambda _e: self._remove_selected_convert_path())

        self.convert_count_label = ttk.Label(files_box, text="No files selected")
        self.convert_count_label.pack(anchor=tk.W, pady=(6, 0))

        options_row = ttk.Frame(parent)
        options_row.pack(fill=tk.X, pady=(0, 8))

        left = ttk.LabelFrame(options_row, text="Output Settings", padding=8)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        ttk.Label(left, text="Format").grid(row=0, column=0, sticky=tk.W)
        format_box = ttk.Combobox(
            left,
            textvariable=self.vars["convert_format"],
            values=[KEEP_LABEL, *self._convert_formats],
            width=22,
            state="readonly",
        )
        format_box.grid(row=0, column=1, columnspan=3, sticky=tk.W, padx=(8, 0))
        format_box.bind("<<ComboboxSelected>>", lambda _event: self._on_convert_format_change())

        ttk.Label(left, text="Quality (1-100)").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        self.convert_quality_spin = ttk.Spinbox(
            left, from_=1, to=100, width=6, textvariable=self.vars["convert_quality"]
        )
        self.convert_quality_spin.grid(row=1, column=1, sticky=tk.W, padx=(8, 0), pady=(8, 0))
        self.convert_lossless_check = ttk.Checkbutton(
            left, text="Lossless", variable=self.vars["convert_lossless"]
        )
        self.convert_lossless_check.grid(
            row=1, column=2, columnspan=2, sticky=tk.W, padx=(12, 0), pady=(8, 0)
        )

        ttk.Label(left, text="Max size (W x H, 0 = any)").grid(
            row=2, column=0, sticky=tk.W, pady=(8, 0)
        )
        ttk.Spinbox(
            left, from_=0, to=20000, width=6, textvariable=self.vars["convert_max_width"]
        ).grid(row=2, column=1, sticky=tk.W, padx=(8, 0), pady=(8, 0))
        ttk.Label(left, text="x").grid(row=2, column=2, pady=(8, 0), padx=4)
        ttk.Spinbox(
            left, from_=0, to=20000, width=6, textvariable=self.vars["convert_max_height"]
        ).grid(row=2, column=3, sticky=tk.W, pady=(8, 0))

        ttk.Checkbutton(
            left,
            text="Strip metadata (EXIF, GPS location, camera info)",
            variable=self.vars["convert_strip_metadata"],
        ).grid(row=3, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
        ttk.Checkbutton(
            left,
            text="Skip files that don't get smaller",
            variable=self.vars["convert_only_smaller"],
        ).grid(row=4, column=0, columnspan=4, sticky=tk.W, pady=(4, 0))

        right = ttk.LabelFrame(options_row, text="Output Location", padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
        ttk.Checkbutton(
            right,
            text="Save next to each original",
            variable=self.vars["convert_use_source_dir"],
            command=self._on_convert_output_toggle,
        ).pack(anchor=tk.W)
        output_row = ttk.Frame(right)
        output_row.pack(fill=tk.X, pady=(8, 0))
        self.convert_output_entry = ttk.Entry(
            output_row, textvariable=self.vars["convert_output_dir"], state="disabled"
        )
        self.convert_output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.convert_output_browse = ttk.Button(
            output_row, text="Browse…", command=self._choose_convert_output_dir, state="disabled"
        )
        self.convert_output_browse.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            right,
            text="Folder structure is kept under a chosen output folder.",
            wraplength=320,
        ).pack(anchor=tk.W, pady=(8, 0))

        actions = ttk.Frame(parent)
        actions.pack(fill=tk.X)
        self.convert_status = ttk.Label(actions, text="● Ready")
        self.convert_status.pack(side=tk.LEFT)

        self.convert_stop_button = ttk.Button(
            actions, text="Stop", command=self._stop_convert, state="disabled"
        )
        self.convert_stop_button.pack(side=tk.RIGHT)
        self.convert_start_button = ttk.Button(
            actions, text="Convert", command=self._start_convert, style="Accent.TButton"
        )
        self.convert_start_button.pack(side=tk.RIGHT, padx=(0, 8))
        self.convert_open_folder_button = ttk.Button(
            actions, text="Open folder", command=self._open_convert_folder, state="disabled"
        )
        self.convert_open_folder_button.pack(side=tk.RIGHT, padx=(0, 8))
        self._on_convert_format_change()
        self._update_convert_count()

    def _on_convert_format_change(self) -> None:
        fmt = self._convert_formats.get(str(self.vars["convert_format"].get()))
        # "Keep original" may re-encode JPEG/WebP/etc., so quality stays live.
        uses_quality = fmt is None or fmt.uses_quality
        has_lossless = fmt is not None and fmt.has_lossless
        self.convert_quality_spin.state(["!disabled"] if uses_quality else ["disabled"])
        if not has_lossless:
            self.vars["convert_lossless"].set(False)
        self.convert_lossless_check.state(["!disabled"] if has_lossless else ["disabled"])

    def _on_convert_output_toggle(self) -> None:
        state = "disabled" if self.vars["convert_use_source_dir"].get() else "normal"
        self.convert_output_entry.configure(state=state)
        self.convert_output_browse.configure(state=state)

    def _convert_paths(self) -> list[Path]:
        return [Path(value) for value in self.vars["convert_paths"].get().split("|") if value]

    def _add_convert_paths(self, values: Sequence[str]) -> None:
        existing = {value for value in self.vars["convert_paths"].get().split("|") if value}
        existing.update(value for value in values if value)
        self.vars["convert_paths"].set("|".join(sorted(existing)))
        self._update_convert_count()

    def _remove_selected_convert_path(self) -> None:
        if not hasattr(self, "convert_listbox"):
            return
        selected_indices = list(self.convert_listbox.curselection())
        if not selected_indices:
            return
        paths = self._convert_paths()
        to_remove = {str(paths[i]) for i in selected_indices if 0 <= i < len(paths)}
        remaining = [p for p in paths if str(p) not in to_remove]
        self.vars["convert_paths"].set("|".join(str(p) for p in remaining))
        self._update_convert_count()

    def _browse_convert_files(self) -> None:
        patterns = " ".join(f"*{extension}" for extension in sorted(self._convert_extensions))
        files = filedialog.askopenfilenames(
            title="Select images",
            filetypes=[("Images", patterns), ("All files", "*.*")],
        )
        if files:
            self._add_convert_paths(files)

    def _browse_convert_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select folder with images")
        if folder:
            self._add_convert_paths([folder])

    def _clear_convert_paths(self) -> None:
        self.vars["convert_paths"].set("")
        self._update_convert_count()

    def _update_convert_count(self) -> None:
        paths = self._convert_paths()
        self._count_generation += 1
        generation = self._count_generation

        if hasattr(self, "convert_listbox"):
            self.convert_listbox.delete(0, tk.END)
            for path in paths:
                self.convert_listbox.insert(tk.END, str(path))

        if not paths:
            self.convert_count_label.configure(text="No files selected")
            return
        self.convert_count_label.configure(text="Counting images…")

        # Recursive scans of large folders would freeze the window; count in
        # the background and drop results superseded by a newer selection.
        def count() -> None:
            counts: dict[str, int] = {}
            total = 0
            for p in paths:
                if p.is_dir():
                    c = len(collect_images([p], self._convert_extensions))
                    counts[str(p)] = c
                    total += c
                else:
                    total += 1
            self.post_to_ui(self._show_convert_count, generation, paths, total, counts)

        threading.Thread(target=count, daemon=True).start()

    def _show_convert_count(
        self,
        generation: int,
        paths: list[Path],
        total: int,
        counts: dict[str, int] | None = None,
    ) -> None:
        if generation != self._count_generation:
            return
        folders = sum(1 for path in paths if path.is_dir())
        files = len(paths) - folders
        self.convert_count_label.configure(
            text=f"{folders} folder(s), {files} file(s) — {total} image(s) found"
        )
        if counts is not None and hasattr(self, "convert_listbox"):
            selected_indices = set(self.convert_listbox.curselection())
            self.convert_listbox.delete(0, tk.END)
            for path in paths:
                p_str = str(path)
                if path.is_dir():
                    c = counts.get(p_str, 0)
                    display = f"{p_str}  ({c} image{'s' if c != 1 else ''})"
                else:
                    display = p_str
                self.convert_listbox.insert(tk.END, display)
            for idx in selected_indices:
                if idx < len(paths):
                    self.convert_listbox.selection_set(idx)

    def _choose_convert_output_dir(self) -> None:
        selected = filedialog.askdirectory(title="Select output directory")
        if selected:
            self.vars["convert_output_dir"].set(selected)

    def _compile_convert_request(self) -> ConvertRequest | None:
        paths = self._convert_paths()
        if not paths:
            messagebox.showwarning("No files", "Select one or more images or folders.")
            return None

        output_dir: Path | None = None
        if not self.vars["convert_use_source_dir"].get():
            output_dir_text = str(self.vars["convert_output_dir"].get()).strip()
            if not output_dir_text:
                messagebox.showwarning("No output", "Choose an output directory.")
                return None
            output_dir = Path(output_dir_text)

        try:
            quality = int(self.vars["convert_quality"].get())
            max_width = int(self.vars["convert_max_width"].get())
            max_height = int(self.vars["convert_max_height"].get())
        except (tk.TclError, ValueError):
            messagebox.showwarning("Invalid number", "Quality and max size must be whole numbers.")
            return None

        fmt = self._convert_formats.get(str(self.vars["convert_format"].get()))
        options = ConversionOptions(
            output_format=fmt.key if fmt else KEEP_FORMAT,
            quality=quality,
            lossless=bool(self.vars["convert_lossless"].get()),
            max_width=max_width,
            max_height=max_height,
            strip_metadata=bool(self.vars["convert_strip_metadata"].get()),
            only_if_smaller=bool(self.vars["convert_only_smaller"].get()),
            output_dir=output_dir,
        )
        try:
            options.validate()
        except Exception as error:
            messagebox.showwarning("Invalid settings", str(error))
            return None
        return ConvertRequest(input_paths=paths, options=options)

    def _start_convert(self) -> None:
        if self.convert_thread and self.convert_thread.is_alive():
            messagebox.showinfo("Converter busy", "A conversion is already running.")
            return

        request = self._compile_convert_request()
        if request is None:
            return

        if self.vars["convert_use_source_dir"].get():
            images = collect_images(request.input_paths, self._convert_extensions)
            folders = {p.path.parent for p in images}
            file_count = len(images)
            folder_count = len(folders)
            if file_count > 20 or folder_count > 1:
                fmt_name = (
                    "images in their original formats"
                    if request.options.output_format == KEEP_FORMAT
                    else f"{request.options.output_format.upper()} files"
                )
                msg = (
                    f"Write {file_count:,} {fmt_name} next to their originals "
                    f"in {folder_count:,} folder{'s' if folder_count != 1 else ''}?"
                )
                if not messagebox.askokcancel("Confirm Output Location", msg):
                    return

        self.convert_status.configure(text="● Running")
        self.convert_start_button.state(["disabled"])
        self.convert_stop_button.state(["!disabled"])
        if hasattr(self, "convert_open_folder_button"):
            self.convert_open_folder_button.state(["disabled"])

        self.convert_stop_event.clear()
        self.convert_thread = threading.Thread(
            target=self._run_convert_thread, args=(request,), daemon=True
        )
        self.convert_thread.start()

    def _stop_convert(self) -> None:
        if self.convert_thread and self.convert_thread.is_alive():
            self.convert_stop_event.set()
            self.convert_status.configure(text="● Stopping")
            self.convert_stop_button.state(["disabled"])

    def _run_convert_thread(self, request: ConvertRequest) -> None:
        def progress(index: int, total: int, name: str) -> None:
            self.post_to_ui(self._show_convert_progress, index, total, name)

        try:
            result = convert_image_batch(
                input_paths=request.input_paths,
                options=request.options,
                stop_event=self.convert_stop_event,
                progress_callback=progress,
            )
            self.post_to_ui(self._on_convert_complete, result, None)
        except Exception as error:
            self.post_to_ui(self._on_convert_complete, None, str(error))

    def _show_convert_progress(self, index: int, total: int, name: str) -> None:
        if self.convert_thread and self.convert_thread.is_alive():
            self.convert_status.configure(text=f"● {index}/{total}  {name}")

    def _on_convert_complete(self, result: BatchConversionResult | None, error: str | None) -> None:
        self.convert_start_button.state(["!disabled"])
        self.convert_stop_button.state(["disabled"])

        if result is not None:
            self._last_convert_folder = result.output_dir
            if hasattr(self, "convert_open_folder_button"):
                self.convert_open_folder_button.state(["!disabled"])

        if error:
            self.convert_status.configure(text="● Error")
            messagebox.showerror("Conversion error", error)
            return

        if result is None:
            self.convert_status.configure(text="● Ready")
            return

        if self.convert_stop_event.is_set():
            status_text = f"■ Stopped — {result.converted}/{result.total_files} converted"
            self.convert_status.configure(text=status_text)
            self._append_log(f"[Convert] {status_text}")
        else:
            status_text = f"✓ Done — {result.converted}/{result.total_files} converted"
            if result.failed:
                status_text += f" ({result.failed} failed)"
            self.convert_status.configure(text=status_text)
            self._append_log(f"[Convert] {status_text}")
        self._append_log(f"[Convert] {summarize_conversion(result)}")
        for message in result.errors[:MAX_LOGGED_ERRORS]:
            self._append_log(f"[Convert]   skipped: {message}")
        if len(result.errors) > MAX_LOGGED_ERRORS:
            self._append_log(f"[Convert]   … and {len(result.errors) - MAX_LOGGED_ERRORS} more")

    def _open_convert_folder(self) -> None:
        folder = getattr(self, "_last_convert_folder", None)
        if not folder:
            raw_dir = str(self.vars["convert_output_dir"].get()).strip()
            if raw_dir:
                folder = Path(raw_dir)
            else:
                paths = self._convert_paths()
                if paths:
                    folder = paths[0] if paths[0].is_dir() else paths[0].parent
        if not folder or not Path(folder).exists():
            messagebox.showinfo("Folder not found", "Output folder does not exist.")
            return
        if not open_in_file_manager(folder):
            messagebox.showerror("Error", f"Could not open folder:\n{folder}")
