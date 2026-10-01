"""Light/dark theming for the Tk GUI.

Dark mode is built on ttk's "clam" theme because the native Windows themes
("vista", "xpnative") ignore most colour options. Light mode switches back
to whatever native theme Tk started with, so it looks exactly as before.
Plain Tk widgets (the log Text, Combobox dropdown lists) are not styled by
ttk and are recoloured explicitly.
"""

from __future__ import annotations

import contextlib
import sys
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

DARK_BASE_THEME = "clam"


@dataclass(frozen=True)
class Palette:
    background: str
    surface: str
    raised: str
    hover: str
    foreground: str
    muted: str
    border: str
    accent: str
    accent_foreground: str


DARK = Palette(
    background="#1e1f22",
    surface="#2b2d31",
    raised="#35373c",
    hover="#404249",
    foreground="#e3e5e8",
    muted="#a5a9ae",
    border="#3f4147",
    accent="#2f6bd8",
    accent_foreground="#ffffff",
)


class ThemeManager:
    """Owns theme switching for one Tk root."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._style = ttk.Style(root)
        self._native_theme = self._style.theme_use()
        self._text_widgets: list[tk.Text] = []
        self._listbox_widgets: list[tk.Listbox] = []
        # Defaults read from a throwaway widget, so light mode can restore
        # the platform's own colours instead of guessing them.
        probe = tk.Text(root)
        self._text_defaults = {
            key: probe.cget(key)
            for key in (
                "background",
                "foreground",
                "insertbackground",
                "selectbackground",
                "selectforeground",
            )
        }
        probe.destroy()
        probe_lb = tk.Listbox(root)
        self._listbox_defaults = {
            key: probe_lb.cget(key)
            for key in (
                "background",
                "foreground",
                "selectbackground",
                "selectforeground",
            )
        }
        probe_lb.destroy()
        self.dark = False

    def register_text(self, widget: tk.Text) -> None:
        self._text_widgets.append(widget)
        self._apply_text(widget)

    def register_listbox(self, widget: tk.Listbox) -> None:
        self._listbox_widgets.append(widget)
        self._apply_listbox(widget)

    def apply(self, *, dark: bool) -> None:
        self.dark = dark
        if dark:
            self._apply_dark_styles(DARK)
        else:
            self._style.theme_use(self._native_theme)
            self._root.configure(background=self._style.lookup(".", "background"))
            self._set_listbox_options(
                background=self._text_defaults["background"],
                foreground=self._text_defaults["foreground"],
                select_background=self._text_defaults["selectbackground"],
                select_foreground=self._text_defaults["selectforeground"],
            )
            self._style.configure("Muted.TLabel", foreground="#6c757d")
            self._style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))
        for widget in self._text_widgets:
            self._apply_text(widget)
        for lb in self._listbox_widgets:
            self._apply_listbox(lb)
        set_windows_title_bar_dark(self._root, dark)

    def _apply_text(self, widget: tk.Text) -> None:
        if self.dark:
            widget.configure(
                background=DARK.surface,
                foreground=DARK.foreground,
                insertbackground=DARK.foreground,
                selectbackground=DARK.accent,
                selectforeground=DARK.accent_foreground,
                highlightthickness=0,
                borderwidth=0,
            )
        else:
            widget.configure(**self._text_defaults)

    def _apply_listbox(self, widget: tk.Listbox) -> None:
        if self.dark:
            widget.configure(
                background=DARK.surface,
                foreground=DARK.foreground,
                selectbackground=DARK.accent,
                selectforeground=DARK.accent_foreground,
                highlightthickness=0,
                borderwidth=0,
            )
        else:
            widget.configure(
                background=self._listbox_defaults["background"],
                foreground=self._listbox_defaults["foreground"],
                selectbackground=self._listbox_defaults["selectbackground"],
                selectforeground=self._listbox_defaults["selectforeground"],
                highlightthickness=1,
                borderwidth=1,
            )

    def _set_listbox_options(
        self,
        *,
        background: str,
        foreground: str,
        select_background: str,
        select_foreground: str,
    ) -> None:
        # Combobox dropdowns are plain Tk listboxes created lazily; option
        # database entries apply to dropdowns opened after the switch.
        self._root.option_add("*TCombobox*Listbox.background", background)
        self._root.option_add("*TCombobox*Listbox.foreground", foreground)
        self._root.option_add("*TCombobox*Listbox.selectBackground", select_background)
        self._root.option_add("*TCombobox*Listbox.selectForeground", select_foreground)

    def _apply_dark_styles(self, p: Palette) -> None:
        style = self._style
        style.theme_use(DARK_BASE_THEME)
        self._root.configure(background=p.background)

        style.configure(
            ".",
            background=p.background,
            foreground=p.foreground,
            fieldbackground=p.surface,
            bordercolor=p.border,
            lightcolor=p.background,
            darkcolor=p.background,
            troughcolor=p.surface,
            selectbackground=p.accent,
            selectforeground=p.accent_foreground,
            insertcolor=p.foreground,
            focuscolor=p.accent,
            arrowcolor=p.foreground,
        )
        style.map(
            ".",
            foreground=[("disabled", p.muted)],
            background=[("disabled", p.background)],
        )

        style.configure(
            "TButton",
            background=p.raised,
            bordercolor=p.border,
            lightcolor=p.raised,
            darkcolor=p.raised,
        )
        style.map(
            "TButton",
            background=[("disabled", p.background), ("pressed", p.accent), ("active", p.hover)],
            foreground=[("disabled", p.muted), ("pressed", p.accent_foreground)],
            lightcolor=[("pressed", p.accent), ("active", p.hover)],
            darkcolor=[("pressed", p.accent), ("active", p.hover)],
        )

        style.configure(
            "Accent.TButton",
            background=p.accent,
            foreground=p.accent_foreground,
            bordercolor=p.accent,
            lightcolor=p.accent,
            darkcolor=p.accent,
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("disabled", p.background), ("pressed", p.hover), ("active", p.hover)],
            foreground=[
                ("disabled", p.muted),
                ("pressed", p.accent_foreground),
                ("active", p.accent_foreground),
            ],
            lightcolor=[("pressed", p.hover), ("active", p.hover)],
            darkcolor=[("pressed", p.hover), ("active", p.hover)],
        )

        for name in ("TCheckbutton", "TRadiobutton"):
            style.configure(
                name,
                background=p.background,
                indicatorbackground=p.surface,
                indicatorforeground=p.foreground,
                upperbordercolor=p.border,
                lowerbordercolor=p.border,
            )
            style.map(
                name,
                background=[("active", p.background)],
                indicatorbackground=[
                    ("disabled", p.background),
                    ("selected", p.accent),
                    ("pressed", p.hover),
                ],
                indicatorforeground=[("selected", p.accent_foreground)],
            )

        for name in ("TEntry", "TSpinbox", "TCombobox"):
            style.configure(
                name,
                fieldbackground=p.surface,
                foreground=p.foreground,
                insertcolor=p.foreground,
                bordercolor=p.border,
                lightcolor=p.surface,
                darkcolor=p.surface,
                background=p.raised,
                arrowcolor=p.foreground,
            )
            style.map(
                name,
                fieldbackground=[("disabled", p.background), ("readonly", p.surface)],
                foreground=[("disabled", p.muted)],
                bordercolor=[("focus", p.accent)],
                lightcolor=[("focus", p.accent)],
                background=[("active", p.hover), ("pressed", p.hover)],
            )

        style.configure("TNotebook", background=p.background, bordercolor=p.border)
        style.configure(
            "TNotebook.Tab",
            background=p.raised,
            foreground=p.muted,
            bordercolor=p.border,
            lightcolor=p.raised,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", p.background), ("active", p.hover)],
            foreground=[("selected", p.foreground), ("active", p.foreground)],
            lightcolor=[("selected", p.background)],
        )

        style.configure("TLabelframe", background=p.background, bordercolor=p.border)
        style.configure("TLabelframe.Label", background=p.background, foreground=p.foreground)
        style.configure("Muted.TLabel", foreground=p.muted)

        style.configure(
            "Vertical.TScrollbar",
            background=p.raised,
            troughcolor=p.background,
            bordercolor=p.background,
            arrowcolor=p.foreground,
            lightcolor=p.raised,
            darkcolor=p.raised,
        )
        style.map("Vertical.TScrollbar", background=[("active", p.hover)])

        self._set_listbox_options(
            background=p.surface,
            foreground=p.foreground,
            select_background=p.accent,
            select_foreground=p.accent_foreground,
        )


def set_windows_title_bar_dark(root: tk.Tk, dark: bool) -> None:
    """Match the Windows 10/11 title bar to the theme; no-op elsewhere."""
    if sys.platform != "win32":
        return
    with contextlib.suppress(Exception):
        import ctypes

        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 20H1+); 19 on older builds.
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                break
