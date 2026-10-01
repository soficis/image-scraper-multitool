"""Theme switching on a real Tk root (skipped where no display is available)."""

from __future__ import annotations

import logging
import tkinter as tk
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from tkinter import font, ttk
from unittest.mock import MagicMock

import pytest

from image_scraper.domain.models import BatchConversionResult, ScrapeResult
from image_scraper.ui.settings import load_settings, save_settings
from image_scraper.ui.theme import DARK, DARK_BASE_THEME, ThemeManager
from image_scraper.ui.tk_app import ScraperApp


@dataclass(frozen=True)
class AppAtStartup:
    app: ScraperApp
    dark_mode_var: bool
    manager_dark: bool
    log_background: str


def _start_app() -> ScraperApp:
    """Create the app, skipping only when Tk itself cannot start.

    Tcl on Windows intermittently fails to read its own init scripts
    (init.tcl, tk.tcl, auto.tcl) while starting an interpreter, so start-up
    is retried. A TclError that does not name a .tcl file (for example an
    invalid style option in the theme code) is a real failure.
    """
    last: tk.TclError | None = None
    for _ in range(3):
        try:
            return ScraperApp()
        except tk.TclError as error:
            message = str(error)
            if ".tcl" not in message and "display" not in message.lower():
                raise
            last = error
    pytest.skip(f"Tk unavailable: {last}")


@pytest.fixture(scope="module")
def started() -> Iterator[AppAtStartup]:
    # One interpreter for the whole module: each extra Tk() is another chance
    # for the start-up flake above, and ScraperApp is itself a Tk root.
    app = _start_app()
    app.withdraw()
    snapshot = AppAtStartup(
        app=app,
        dark_mode_var=bool(app.vars["dark_mode"].get()),
        manager_dark=app.theme.dark,
        log_background=str(app.log_widget.cget("background")),
    )
    yield snapshot
    logging.getLogger().removeHandler(app.log_handler)
    app.destroy()


@pytest.fixture
def app(started: AppAtStartup) -> Iterator[ScraperApp]:
    yield started.app
    started.app.vars["dark_mode"].set(True)


def test_app_starts_dark(started: AppAtStartup) -> None:
    assert started.dark_mode_var is True
    assert started.manager_dark is True
    assert started.log_background == DARK.surface


def test_toggle_switches_app_theme(app: ScraperApp) -> None:
    app.vars["dark_mode"].set(False)
    assert app.theme.dark is False
    assert app.log_widget.cget("background") != DARK.surface
    app.vars["dark_mode"].set(True)
    assert app.log_widget.cget("background") == DARK.surface


def test_dark_then_light_restores_native_theme(app: ScraperApp) -> None:
    app.vars["dark_mode"].set(False)  # put the root back on its native theme
    style = ttk.Style(app)
    native = style.theme_use()
    manager = ThemeManager(app)
    text = tk.Text(app)
    manager.register_text(text)
    native_text_bg = text.cget("background")

    manager.apply(dark=True)
    assert style.theme_use() == DARK_BASE_THEME
    assert style.lookup("TEntry", "fieldbackground") == DARK.surface
    assert text.cget("background") == DARK.surface

    manager.apply(dark=False)
    assert style.theme_use() == native
    assert text.cget("background") == native_text_bg
    text.destroy()


def test_text_registered_while_dark_is_dark(app: ScraperApp) -> None:
    manager = ThemeManager(app)
    manager.apply(dark=True)
    text = tk.Text(app)
    manager.register_text(text)
    assert text.cget("foreground") == DARK.foreground
    text.destroy()


def test_convert_tab_greys_out_quality_for_lossless_formats(app: ScraperApp) -> None:
    app.vars["convert_format"].set("PNG")
    app._on_convert_format_change()
    assert "disabled" in app.convert_quality_spin.state()
    assert "disabled" in app.convert_lossless_check.state()

    app.vars["convert_format"].set("WebP")
    app._on_convert_format_change()
    assert "disabled" not in app.convert_quality_spin.state()
    assert "disabled" not in app.convert_lossless_check.state()


@pytest.mark.parametrize(
    ("var_name", "label", "default_val"),
    [
        ("num_images", "Images", 10),
        ("bing_timeout", "Bing timeout", 15.0),
        ("compression_quality", "JPEG quality", 0),
        ("resize_width", "Resize width", 0),
        ("resize_height", "Resize height", 0),
        ("min_width", "Min width", 0),
        ("min_height", "Min height", 0),
        ("max_width", "Max width", 0),
        ("max_height", "Max height", 0),
        ("max_missed", "Max missed passes", 10),
        ("recursion_depth", "Depth", 0),
    ],
)
def test_compile_scrape_options_invalid_number_shows_error(
    app: ScraperApp, monkeypatch: pytest.MonkeyPatch, var_name: str, label: str, default_val: object
) -> None:
    monkeypatch.setattr("image_scraper.ui.scrape_runner.scrape_images", MagicMock())
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "tkinter.messagebox.showerror",
        lambda title, msg, **kwargs: errors.append((title, msg)),
    )
    app.vars["query"].set("cats")
    app.vars["bing"].set(True)
    try:
        app.setvar(str(app.vars[var_name]), "ten")
        res = app._compile_scrape_options()
        assert res is None
        assert len(errors) == 1
        assert label in errors[0][1]
    finally:
        app.vars[var_name].set(default_val)


def test_stop_convert_status_shows_stopped(app: ScraperApp) -> None:
    app.convert_stop_event.set()
    try:
        res = BatchConversionResult(
            total_files=5,
            converted=2,
            skipped=3,
            errors=[],
            output_dir=Path("."),
        )
        app._on_convert_complete(res, None)
        assert app.convert_status.cget("text").startswith("■ Stopped")
        assert "2/5" in app.convert_status.cget("text")
    finally:
        app.convert_stop_event.clear()
        app.convert_status.configure(text="● Ready")


def test_stop_scrape_status_shows_stopped(app: ScraperApp) -> None:
    app.scrape_stop_event.set()
    try:
        res = ScrapeResult(
            engine="bing",
            requested=10,
            saved=4,
            skipped=2,
            errors=[],
            destination=Path("."),
        )
        app._on_scrape_complete([res], None)
        assert app.scrape_status.cget("text").startswith("■ Stopped")
        assert "4 saved" in app.scrape_status.cget("text")
    finally:
        app.scrape_stop_event.clear()
        app.scrape_status.configure(text="● Ready")


def test_pexels_pixabay_key_check_and_env(app: ScraperApp, monkeypatch: pytest.MonkeyPatch) -> None:
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "tkinter.messagebox.showwarning",
        lambda title, msg, **kwargs: warnings.append((title, msg)),
    )
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    monkeypatch.delenv("PIXABAY_API_KEY", raising=False)

    app.vars["query"].set("cats")
    app.vars["bing"].set(False)
    app.vars["pexels"].set(True)
    app.vars["pixabay"].set(False)
    app.vars["pexels_api_key"].set("")

    # Without key and without env var: returns None and warns
    res = app._compile_scrape_options()
    assert res is None
    assert len(warnings) == 1
    assert "Pexels" in warnings[0][1]

    # With env var: succeeds
    monkeypatch.setenv("PEXELS_API_KEY", "env_secret_key")
    res = app._compile_scrape_options()
    assert res is not None

    # Reset
    app.vars["bing"].set(True)
    app.vars["pexels"].set(False)


def test_api_key_hints_update(app: ScraperApp, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PEXELS_API_KEY", raising=False)
    app.vars["pexels_api_key"].set("")
    app._update_api_key_hints()
    assert app.pexels_key_hint.cget("text") == "(needs key)"

    app.vars["pexels_api_key"].set("some_key")
    assert app.pexels_key_hint.cget("text") == ""

    app.vars["pexels_api_key"].set("")
    monkeypatch.setenv("PEXELS_API_KEY", "env_key")
    app._update_api_key_hints()
    assert app.pexels_key_hint.cget("text") == ""


def test_activity_log_and_start_visible_at_688_px(app: ScraperApp) -> None:
    orig_geom = app.geometry()
    app.minsize(920, 400)
    app.geometry("980x688")
    app.update()
    try:
        # Start button is visible inside window
        start_bottom = (
            app.scrape_start_button.winfo_rooty() + app.scrape_start_button.winfo_height()
        )
        window_bottom = app.winfo_rooty() + app.winfo_height()
        assert start_bottom <= window_bottom

        # Log widget has at least 3 lines visible
        log_font = font.Font(app, font=app.log_widget.cget("font"))
        line_height = log_font.metrics("linespace")
        log_top_rel = app.log_widget.winfo_rooty() - app.winfo_rooty()
        assert log_top_rel + 3 * line_height <= app.winfo_height()
    finally:
        app.geometry(orig_geom)
        app.update()


def test_grouping_and_advanced_toggle(app: ScraperApp) -> None:
    def is_descendant(child: tk.Widget, parent: tk.Widget) -> bool:
        parent_path = str(parent)
        current: tk.Widget | None = child
        while current:
            parent_name = current.winfo_parent()
            if not parent_name:
                return False
            if parent_name == parent_path:
                return True
            try:
                current = child.nametowidget(parent_name)
            except KeyError:
                return False
        return False

    # Check Sources descendants
    assert is_descendant(app.bing_check, app.sources_frame)
    assert is_descendant(app.google_check, app.sources_frame)
    assert is_descendant(app.openverse_check, app.sources_frame)
    assert is_descendant(app.pexels_check, app.sources_frame)
    assert is_descendant(app.pixabay_check, app.sources_frame)

    # Check Advanced descendants
    assert is_descendant(app.depth_spin, app.advanced_frame)

    app.deiconify()
    try:
        # Advanced is collapsed by default
        app.vars["advanced_open"].set(False)
        app._update_advanced_visibility()
        app.update()
        assert not app.advanced_frame.winfo_ismapped()

        # Toggle open
        app._toggle_advanced()
        app.update()
        assert app.vars["advanced_open"].get() is True
        assert app.advanced_frame.winfo_ismapped()
    finally:
        # Reset and withdraw
        app.vars["advanced_open"].set(False)
        app._update_advanced_visibility()
        app.update()
        app.withdraw()


def test_app_save_excludes_keys_by_default(
    app: ScraperApp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("image_scraper.ui.settings.get_settings_path", lambda: settings_file)

    app.vars["query"].set("secret search")
    app.vars["convert_paths"].set("c:/test.jpg")
    app.vars["pexels_api_key"].set("secret_pexels")
    app.vars["pixabay_api_key"].set("secret_pixabay")
    app.vars["remember_api_keys"].set(False)

    app._save_persisted_settings()
    saved = load_settings(path=settings_file)

    # Excluded always
    assert "query" not in saved
    assert "convert_paths" not in saved

    # Excluded when remember_api_keys is False
    assert "pexels_api_key" not in saved
    assert "pixabay_api_key" not in saved


def test_app_save_includes_keys_when_opted_in(
    app: ScraperApp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr("image_scraper.ui.settings.get_settings_path", lambda: settings_file)

    app.vars["pexels_api_key"].set("my_pexels_key")
    app.vars["pixabay_api_key"].set("my_pixabay_key")
    app.vars["remember_api_keys"].set(True)

    app._save_persisted_settings()
    saved = load_settings(path=settings_file)

    assert saved.get("pexels_api_key") == "my_pexels_key"
    assert saved.get("pixabay_api_key") == "my_pixabay_key"
    assert saved.get("remember_api_keys") is True


def test_app_load_ignores_unknown_and_wrong_types(
    app: ScraperApp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_file = tmp_path / "settings.json"
    save_settings(
        {
            "unknown_random_key": "some_value",
            "bing": "should_be_bool_not_str",
            "num_images": "should_be_int",
            "bing_timeout": "should_be_float",
            "output_dir": 12345,  # should be str
        },
        path=settings_file,
    )
    monkeypatch.setattr("image_scraper.ui.settings.get_settings_path", lambda: settings_file)

    app.vars["bing"].set(True)
    app.vars["num_images"].set(10)
    app.vars["output_dir"].set("default_dir")

    app._load_persisted_settings()

    # Values must remain unaffected because types were invalid
    assert app.vars["bing"].get() is True
    assert app.vars["num_images"].get() == 10
    assert app.vars["output_dir"].get() == "default_dir"


def test_scrape_progress_label_updates(app: ScraperApp) -> None:
    app._scrape_engine_progress = {}
    app._show_scrape_progress("bing", 4, 10)
    assert "Bing 4/10" in app.scrape_status.cget("text")

    app._show_scrape_progress("google", -1, 10)
    text = app.scrape_status.cget("text")
    assert "Bing 4/10" in text
    assert "Google collecting…" in text

    # Reset
    app.scrape_status.configure(text="● Ready")


def test_accent_button_styles(app: ScraperApp) -> None:
    assert app.scrape_start_button.cget("style") == "Accent.TButton"
    assert app.convert_start_button.cget("style") == "Accent.TButton"


def test_convert_listbox_remove_and_sync(app: ScraperApp) -> None:
    app.vars["convert_paths"].set("img1.jpg|img2.png")
    app._update_convert_count()
    assert app.convert_listbox.size() == 2

    # Select the first item and remove it
    app.convert_listbox.selection_clear(0, tk.END)
    app.convert_listbox.selection_set(0)
    app._remove_selected_convert_path()

    assert app.vars["convert_paths"].get() == "img2.png"
    assert app.convert_listbox.size() == 1

    # Cleanup
    app.vars["convert_paths"].set("")
    app._update_convert_count()


def test_open_folder_buttons_enabled_and_invoked(
    app: ScraperApp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scrape_calls: list[Path] = []
    convert_calls: list[Path] = []

    def mock_open_scrape(p: Path | str) -> bool:
        scrape_calls.append(Path(p))
        return True

    def mock_open_convert(p: Path | str) -> bool:
        convert_calls.append(Path(p))
        return True

    monkeypatch.setattr(
        "image_scraper.ui.scrape_runner.open_in_file_manager",
        mock_open_scrape,
    )
    monkeypatch.setattr(
        "image_scraper.ui.convert_panel.open_in_file_manager",
        mock_open_convert,
    )

    out_folder = tmp_path / "scrape_out"
    out_folder.mkdir(parents=True, exist_ok=True)
    res = ScrapeResult(
        engine="bing",
        requested=5,
        saved=3,
        skipped=2,
        errors=[],
        destination=out_folder,
    )
    app._on_scrape_complete([res], None)
    assert app.scrape_open_folder_button.instate(["!disabled"])

    app._open_scrape_folder()
    assert len(scrape_calls) == 1
    assert scrape_calls[0] == out_folder

    conv_out = tmp_path / "conv_out"
    conv_out.mkdir(parents=True, exist_ok=True)
    conv_res = BatchConversionResult(
        total_files=3,
        converted=3,
        skipped=0,
        failed=0,
        errors=[],
        bytes_in=1000,
        bytes_out=500,
        output_dir=conv_out,
    )
    app._on_convert_complete(conv_res, None)
    assert app.convert_open_folder_button.instate(["!disabled"])

    app._open_convert_folder()
    assert len(convert_calls) == 1
    assert convert_calls[0] == conv_out


def test_wcag_aa_contrast_ratios() -> None:
    from image_scraper.ui.theme import DARK

    def rel_lum(hex_str: str) -> float:
        clean = hex_str.lstrip("#")
        rgb = [int(clean[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
        rgb = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

    def contrast(hex1: str, hex2: str) -> float:
        l1 = rel_lum(hex1)
        l2 = rel_lum(hex2)
        return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

    # WCAG AA requires at least 4.5:1 for normal text
    assert contrast(DARK.foreground, DARK.background) >= 4.5
    assert contrast(DARK.muted, DARK.raised) >= 4.5
    assert contrast(DARK.muted, DARK.background) >= 4.5
    assert contrast(DARK.accent_foreground, DARK.accent) >= 4.5


def test_clear_log_button(app: ScraperApp) -> None:
    app._append_log("hello log")
    assert "hello log" in app.log_widget.get("1.0", tk.END)
    app.clear_log_button.invoke()
    assert app.log_widget.get("1.0", tk.END).strip() == ""


def test_risky_convert_confirmation(
    app: ScraperApp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Create 22 dummy image files
    files: list[Path] = []
    for i in range(22):
        f = tmp_path / f"img_{i}.jpg"
        f.touch()
        files.append(f)

    app.vars["convert_paths"].set("|".join(str(p) for p in files))
    app.vars["convert_use_source_dir"].set(True)

    asked = []

    def mock_ask(title: str, msg: str, **kwargs: object) -> bool:
        asked.append((title, msg))
        return False

    monkeypatch.setattr("tkinter.messagebox.askokcancel", mock_ask)

    app.convert_thread = None
    app._start_convert()

    # Confirmed cancelled -> no thread started
    assert len(asked) == 1
    assert "22" in asked[0][1]
    assert app.convert_thread is None

    # Reset
    app.vars["convert_paths"].set("")


def test_keyboard_shortcuts_and_log_prefix(
    app: ScraperApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(app, "_start_scrape", lambda: calls.append("scrape"))
    monkeypatch.setattr(app, "_start_convert", lambda: calls.append("convert"))
    monkeypatch.setattr(app, "_stop_scrape", lambda: calls.append("stop_scrape"))
    monkeypatch.setattr(app, "_stop_convert", lambda: calls.append("stop_convert"))

    # Active tab 0: Scrape
    app.notebook.select(0)
    app._on_ctrl_enter(tk.Event())
    app._on_escape(tk.Event())

    # Active tab 1: Convert
    app.notebook.select(1)
    app._on_ctrl_enter(tk.Event())
    app._on_escape(tk.Event())

    assert calls == ["scrape", "stop_scrape", "convert", "stop_convert"]

    # Reset active tab to 0
    app.notebook.select(0)
