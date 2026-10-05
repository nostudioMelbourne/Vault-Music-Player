"""Manage theme palettes, widget styling, and persisted theme selection."""

import json
import tkinter as tk
from tkinter import font as tkfont, ttk

from .utils import write_json_atomic


THEMES = {
    "light": {
        "shell_bg": "#edf1f5",
        "card_bg": "#ffffff",
        "border_color": "#d7dee7",
        "text_color": "#18212f",
        "muted_color": "#607085",
        "selection_bg": "#d8e6ff",
        "heading_bg": "#f5f7fa",
        "button_bg": "#f8fafc",
        "menu_active_bg": "#eef4ff",
        "accent": "#2f6fed",
        "accent_dark": "#2459bd",
        "waveform_axis": "#eef2f7",
        "waveform_empty": "#d8e0eb",
        "waveform_loading": "#e8edf4",
        "waveform_cursor": "#2459bd",
    },
    "dark": {
        "shell_bg": "#111722",
        "card_bg": "#182231",
        "border_color": "#2c3849",
        "text_color": "#e8eef7",
        "muted_color": "#9aa9bc",
        "selection_bg": "#304b78",
        "heading_bg": "#202b3a",
        "button_bg": "#243044",
        "menu_active_bg": "#2b4268",
        "accent": "#6b9dff",
        "accent_dark": "#4a7fe0",
        "waveform_axis": "#2a3545",
        "waveform_empty": "#3a485c",
        "waveform_loading": "#313d4f",
        "waveform_cursor": "#8eb3ff",
    },
}


class ThemeMixin:
    def configure_theme(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        palette = THEMES.get(self.theme_mode, THEMES["light"])
        self.shell_bg = palette["shell_bg"]
        self.card_bg = palette["card_bg"]
        self.border_color = palette["border_color"]
        self.text_color = palette["text_color"]
        self.muted_color = palette["muted_color"]
        self.selection_bg = palette["selection_bg"]
        self.heading_bg = palette["heading_bg"]
        self.button_bg = palette["button_bg"]
        self.menu_active_bg = palette["menu_active_bg"]
        self.accent = palette["accent"]
        self.accent_dark = palette["accent_dark"]
        self.waveform_axis_color = palette["waveform_axis"]
        self.waveform_empty_color = palette["waveform_empty"]
        self.waveform_loading_color = palette["waveform_loading"]
        self.waveform_cursor_color = palette["waveform_cursor"]

        self.root.configure(background=self.shell_bg)
        self.root.option_add("*Background", self.shell_bg)
        self.root.option_add("*Foreground", self.text_color)
        self.root.option_add("*Entry.Background", self.card_bg)
        self.root.option_add("*Entry.Foreground", self.text_color)
        self.root.option_add("*Listbox.Background", self.card_bg)
        self.root.option_add("*Listbox.Foreground", self.text_color)
        self.root.option_add("*selectBackground", self.selection_bg)
        self.root.option_add("*selectForeground", self.text_color)

        try:
            tkfont.nametofont("TkDefaultFont").configure(family="Helvetica Neue", size=12)
            tkfont.nametofont("TkTextFont").configure(family="Helvetica Neue", size=12)
            tkfont.nametofont("TkHeadingFont").configure(family="Helvetica Neue", size=13, weight="bold")
        except tk.TclError:
            pass

        style.configure(".", background=self.shell_bg, foreground=self.text_color)
        style.configure("TFrame", background=self.shell_bg)
        style.configure("TLabel", background=self.shell_bg, foreground=self.text_color)
        style.configure("TButton", padding=(7, 4), background=self.button_bg, foreground=self.text_color)
        style.configure("TMenubutton", padding=(7, 4), background=self.button_bg, foreground=self.text_color)
        style.configure("TCheckbutton", background=self.shell_bg, foreground=self.text_color)
        style.configure("TLabelframe", background=self.shell_bg, borderwidth=1, relief="solid")
        style.configure("TLabelframe.Label", background=self.shell_bg, foreground=self.text_color)
        style.configure(
            "TScrollbar",
            background=self.button_bg,
            troughcolor=self.shell_bg,
            bordercolor=self.border_color,
            lightcolor=self.border_color,
            darkcolor=self.border_color,
            arrowcolor=self.text_color,
        )
        style.configure(
            "Vertical.TScrollbar",
            background=self.button_bg,
            troughcolor=self.shell_bg,
            bordercolor=self.border_color,
            lightcolor=self.border_color,
            darkcolor=self.border_color,
            arrowcolor=self.text_color,
        )
        style.configure(
            "Horizontal.TScrollbar",
            background=self.button_bg,
            troughcolor=self.shell_bg,
            bordercolor=self.border_color,
            lightcolor=self.border_color,
            darkcolor=self.border_color,
            arrowcolor=self.text_color,
        )
        style.configure("Vault.TFrame", background=self.shell_bg)
        style.configure("Vault.Card.TFrame", background=self.card_bg)
        style.configure("Vault.TLabel", background=self.shell_bg, foreground=self.text_color)
        style.configure("Vault.TButton", padding=(7, 4), background=self.button_bg, foreground=self.text_color)
        style.configure("Vault.TMenubutton", padding=(7, 4), background=self.button_bg, foreground=self.text_color)
        style.configure("Vault.TCheckbutton", background=self.shell_bg, foreground=self.text_color)
        style.configure("Vault.TEntry", fieldbackground=self.card_bg, foreground=self.text_color, insertcolor=self.text_color)
        style.configure("Vault.TNotebook", background=self.shell_bg, borderwidth=0)
        style.configure("Vault.TNotebook.Tab", background=self.button_bg, foreground=self.muted_color, padding=(12, 7))
        style.configure("Vault.Treeview", background=self.card_bg, fieldbackground=self.card_bg, foreground=self.text_color, rowheight=26)
        style.configure("Vault.Treeview.Heading", background=self.heading_bg, foreground=self.text_color, relief="flat", padding=(8, 7))
        style.configure(
            "Vault.Vertical.TScrollbar",
            background=self.button_bg,
            troughcolor=self.shell_bg,
            bordercolor=self.border_color,
            lightcolor=self.border_color,
            darkcolor=self.border_color,
            arrowcolor=self.text_color,
        )
        style.configure(
            "Vault.Horizontal.TScrollbar",
            background=self.button_bg,
            troughcolor=self.shell_bg,
            bordercolor=self.border_color,
            lightcolor=self.border_color,
            darkcolor=self.border_color,
            arrowcolor=self.text_color,
        )
        style.configure("Shell.TFrame", background=self.shell_bg)
        style.configure("Card.TFrame", background=self.card_bg, relief="flat")
        style.configure("Title.TLabel", background=self.shell_bg, foreground=self.text_color, font=("Helvetica Neue", 18, "bold"))
        style.configure("Hint.TLabel", background=self.shell_bg, foreground=self.muted_color, font=("Helvetica Neue", 11))
        style.configure("CardHint.TLabel", background=self.card_bg, foreground=self.muted_color, font=("Helvetica Neue", 11))
        style.configure("Status.TLabel", background=self.shell_bg, foreground=self.muted_color, font=("Helvetica Neue", 11))
        style.configure("StatusStrip.TFrame", background=self.heading_bg, relief="solid", borderwidth=1)
        style.configure("StatusValue.TLabel", background=self.heading_bg, foreground=self.text_color, font=("Helvetica Neue", 11))
        style.configure("StatusMeta.TLabel", background=self.heading_bg, foreground=self.muted_color, font=("Helvetica Neue", 10))
        style.configure("Panel.TLabelframe", background=self.shell_bg, borderwidth=1, relief="solid")
        style.configure("Panel.TLabelframe.Label", background=self.shell_bg, foreground=self.text_color, font=("Helvetica Neue", 11, "bold"))
        style.configure("ThemeToggle.TCheckbutton", background=self.shell_bg, foreground=self.text_color, padding=(8, 4))
        style.configure("Action.TButton", padding=(7, 4), background=self.button_bg, foreground=self.text_color)
        style.configure("Action.TMenubutton", padding=(7, 4), background=self.button_bg, foreground=self.text_color)
        style.configure("TEntry", fieldbackground=self.card_bg, foreground=self.text_color, insertcolor=self.text_color)
        style.configure("TNotebook", background=self.shell_bg, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.button_bg, foreground=self.muted_color, padding=(12, 7))
        style.configure(
            "Treeview",
            background=self.card_bg,
            fieldbackground=self.card_bg,
            foreground=self.text_color,
            bordercolor=self.border_color,
            lightcolor=self.border_color,
            darkcolor=self.border_color,
            rowheight=26,
        )
        style.configure("Treeview.Heading", background=self.heading_bg, foreground=self.text_color, relief="flat", padding=(8, 7))
        style.map("Treeview", background=[("selected", self.selection_bg)], foreground=[("selected", self.text_color)])
        style.map(
            "ThemeToggle.TCheckbutton",
            background=[("active", self.shell_bg), ("selected", self.shell_bg)],
            foreground=[("active", self.text_color), ("selected", self.text_color)],
            indicatorcolor=[("selected", self.accent), ("!selected", self.card_bg)],
        )
        style.map(
            "TCheckbutton",
            background=[("active", self.shell_bg), ("selected", self.shell_bg)],
            foreground=[("active", self.text_color), ("selected", self.text_color)],
        )
        style.map(
            "Vault.TCheckbutton",
            background=[("active", self.shell_bg), ("selected", self.shell_bg)],
            foreground=[("active", self.text_color), ("selected", self.text_color)],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.card_bg), ("active", self.menu_active_bg)],
            foreground=[("selected", self.text_color), ("active", self.text_color)],
        )
        style.map(
            "Vault.TNotebook.Tab",
            background=[("selected", self.card_bg), ("active", self.menu_active_bg)],
            foreground=[("selected", self.text_color), ("active", self.text_color)],
        )
        style.map(
            "TEntry",
            fieldbackground=[("readonly", self.card_bg), ("disabled", self.card_bg)],
            foreground=[("disabled", self.muted_color)],
        )
        style.map(
            "Vault.TEntry",
            fieldbackground=[("readonly", self.card_bg), ("disabled", self.card_bg)],
            foreground=[("disabled", self.muted_color)],
        )
        style.map("Vault.Treeview", background=[("selected", self.selection_bg)], foreground=[("selected", self.text_color)])
        style.map(
            "TScrollbar",
            background=[("active", self.menu_active_bg), ("pressed", self.accent_dark)],
            arrowcolor=[("active", self.text_color), ("pressed", "#ffffff")],
        )
        style.map(
            "Vault.Vertical.TScrollbar",
            background=[("active", self.menu_active_bg), ("pressed", self.accent_dark)],
            arrowcolor=[("active", self.text_color), ("pressed", "#ffffff")],
        )
        style.map(
            "Vault.Horizontal.TScrollbar",
            background=[("active", self.menu_active_bg), ("pressed", self.accent_dark)],
            arrowcolor=[("active", self.text_color), ("pressed", "#ffffff")],
        )
        style.map(
            "Action.TButton",
            background=[("active", self.accent), ("pressed", self.accent_dark)],
            foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
        )
        style.map(
            "TButton",
            background=[("active", self.accent), ("pressed", self.accent_dark)],
            foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
        )
        style.map(
            "Vault.TButton",
            background=[("active", self.accent), ("pressed", self.accent_dark)],
            foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
        )
        style.map(
            "Vault.TMenubutton",
            background=[("active", self.menu_active_bg), ("pressed", self.menu_active_bg)],
            foreground=[("active", self.text_color)],
        )
        style.map(
            "Action.TMenubutton",
            background=[("active", self.menu_active_bg), ("pressed", self.menu_active_bg)],
            foreground=[("active", self.text_color)],
        )
        self.apply_theme_to_tk_widgets()

    def apply_theme_to_tk_widgets(self):
        self.apply_theme_to_widget_tree(self.root)

        for panedwindow_name in ("body_pane", "content", "albums_content", "playlist_pane"):
            panedwindow = getattr(self, panedwindow_name, None)
            if panedwindow is not None:
                panedwindow.configure(background=self.border_color)

        analyzer_canvas = getattr(self, "analyzer_canvas", None)
        if analyzer_canvas is not None:
            analyzer_canvas.configure(highlightbackground=self.border_color)

        transient_canvas = getattr(self, "transient_canvas", None)
        if transient_canvas is not None:
            transient_canvas.configure(highlightbackground=self.border_color)

        playlist_list = getattr(self, "playlist_list", None)
        if playlist_list is not None:
            playlist_list.configure(
                background=self.card_bg,
                foreground=self.text_color,
                selectbackground=self.selection_bg,
                selectforeground=self.text_color,
            )

        for menu in self.styled_menus:
            self.configure_menu(menu)

        self.draw_current_analyzer()

    def apply_theme_to_widget_tree(self, widget):
        widget_class = widget.winfo_class()

        try:
            if widget_class in {"TFrame", "Frame"}:
                self.configure_widget_style(widget, "Vault.TFrame")
            elif widget_class == "TLabel":
                self.configure_widget_style(widget, "Vault.TLabel")
            elif widget_class == "TButton":
                self.configure_widget_style(widget, "Vault.TButton")
            elif widget_class == "TMenubutton":
                self.configure_widget_style(widget, "Vault.TMenubutton")
            elif widget_class == "TCheckbutton":
                self.configure_widget_style(widget, "Vault.TCheckbutton")
            elif widget_class == "TNotebook":
                self.configure_widget_style(widget, "Vault.TNotebook")
            elif widget_class == "Treeview":
                self.configure_widget_style(widget, "Vault.Treeview")
                self.configure_treeview_theme(widget)
            elif widget_class == "TEntry":
                self.configure_widget_style(widget, "Vault.TEntry")
            elif widget_class == "TScrollbar":
                orient = str(widget.cget("orient"))
                style_name = "Vault.Horizontal.TScrollbar" if orient == tk.HORIZONTAL else "Vault.Vertical.TScrollbar"
                self.configure_widget_style(widget, style_name)
            elif widget_class == "Listbox":
                widget.configure(
                    background=self.card_bg,
                    foreground=self.text_color,
                    selectbackground=self.selection_bg,
                    selectforeground=self.text_color,
                    highlightbackground=self.border_color,
                    highlightcolor=self.accent,
                )
            elif widget_class == "Canvas":
                widget.configure(highlightbackground=self.border_color, highlightcolor=self.accent)
        except tk.TclError:
            pass

        for child in widget.winfo_children():
            self.apply_theme_to_widget_tree(child)

    def configure_widget_style(self, widget, style_name):
        try:
            current_style = widget.cget("style")
        except tk.TclError:
            return

        if current_style:
            return

        widget.configure(style=style_name)

    def configure_treeview_theme(self, tree):
        tree.tag_configure("theme-row", background=self.card_bg, foreground=self.text_color)
        for item_id in tree.get_children(""):
            tree.item(item_id, tags=self.theme_tree_tags(tree.item(item_id, "tags")))

    def theme_tree_tags(self, tags=()):
        current_tags = [tag for tag in tags if tag != "theme-row"]
        return ("theme-row", *current_tags)

    def configure_menu(self, menu):
        menu.configure(
            background=self.card_bg,
            foreground=self.text_color,
            activebackground=self.menu_active_bg,
            activeforeground=self.text_color,
            borderwidth=0,
            relief=tk.FLAT,
        )

    def create_menu(self, parent, track=False):
        menu = tk.Menu(parent, tearoff=False)
        self.configure_menu(menu)
        if track:
            self.styled_menus.append(menu)
        return menu

    def load_theme_mode(self):
        try:
            with open(self.paths.settings_db, "r", encoding="utf-8") as file:
                settings = json.load(file)
        except (OSError, json.JSONDecodeError):
            return "light"

        theme = settings.get("theme") if isinstance(settings, dict) else None
        return theme if theme in THEMES else "light"

    def save_theme_mode(self):
        settings = {}
        try:
            if self.paths.settings_db.exists():
                with open(self.paths.settings_db, "r", encoding="utf-8") as file:
                    loaded_settings = json.load(file)
                if isinstance(loaded_settings, dict):
                    settings = loaded_settings
        except (OSError, json.JSONDecodeError):
            settings = {}

        try:
            self.paths.app_support_dir.mkdir(parents=True, exist_ok=True)
            settings["theme"] = self.theme_mode
            write_json_atomic(self.paths.settings_db, settings)
        except OSError:
            pass

    def toggle_dark_mode(self):
        self.theme_mode = "dark" if self.dark_mode_var.get() else "light"
        self.save_theme_mode()
        self.configure_theme()

    def create_menu_button(self, parent, text, items):
        button = ttk.Menubutton(parent, text=text, style="Action.TMenubutton", direction="below")
        menu = self.create_menu(button, track=True)
        for item in items:
            if item == "separator":
                menu.add_separator()
                continue

            menu.add_command(label=item["label"], command=item["command"])

        button.configure(menu=menu)
        return button
