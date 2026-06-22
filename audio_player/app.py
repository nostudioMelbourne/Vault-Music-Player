import json
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, simpledialog, ttk

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "audio_player"

from .bpm import analyze_bpm
from .config import build_paths
from .library import LibraryManager
from .playback import NSSoundBackend
from .spectral import build_spectrogram
from .utils import describe_song, format_seconds, sanitize_name
from .waveform import build_waveform_peaks


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


class AudioPlayerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Vault Music")
        self.root.geometry("1180x760")
        self.root.minsize(940, 640)

        self.paths = build_paths()
        self.library = LibraryManager(self.paths)
        self.player = NSSoundBackend()
        self.app_icon_image = None
        self.styled_menus = []
        self.theme_mode = self.load_theme_mode()

        self.all_playlist_names = []
        self.playlist_names = []
        self.current_queue = []
        self.current_queue_index = None
        self.current_queue_source = "Library"
        self.current_song_id = None
        self.active_play_source = "library"
        self.syncing_playback_selection = False
        self.dragging_progress = False
        self.spectrogram_data = None
        self.spectrogram_loading = False
        self.transient_peaks = []
        self.transient_loading = False
        self.analyzer_job_token = 0
        self.spectrogram_photo = None
        self.spectrogram_photo_cache_key = None
        self.spectrogram_palette = self.build_spectrogram_palette()
        self.bpm_analysis_song_ids = set()
        self.resize_job = None

        self.album_key_by_item = {}
        self.album_summary_by_key = {}
        self.visible_library_song_ids = []
        self.visible_album_song_ids = []
        self.visible_playlist_song_ids = []

        self.song_search_var = tk.StringVar()
        self.album_search_var = tk.StringVar()
        self.album_song_search_var = tk.StringVar()
        self.playlist_search_var = tk.StringVar()
        self.playlist_song_search_var = tk.StringVar()
        self.songs_summary_var = tk.StringVar(value="0 songs")

        self.progress_var = tk.DoubleVar(value=0.0)
        self.time_label_var = tk.StringVar(value="0:00 / 0:00")
        self.dark_mode_var = tk.BooleanVar(value=self.theme_mode == "dark")

        self.drag_origin = None
        self.drag_payload = None
        self.drag_target_playlist = None
        self.status_before_drag = ""
        self.playlist_before_drag = None
        self.initial_pane_layout_applied = False
        self.tree_resize_job = None

        self.build_ui()
        self.configure_interactions()
        self.refresh_all_views()
        self.update_progress_ui(reset=True)
        self.root.after(250, self.poll_player)

    def build_ui(self):
        self.configure_theme()
        self.apply_app_icon()

        self.root.option_add("*tearOff", False)

        self.container = ttk.Frame(self.root, padding=14, style="Shell.TFrame")
        self.container.pack(fill=tk.BOTH, expand=True)

        self.header_frame = ttk.Frame(self.container, style="Shell.TFrame")
        self.header_frame.pack(fill=tk.X, pady=(0, 10))
        self.header_frame.columnconfigure(0, weight=1)
        self.header_frame.columnconfigure(1, weight=0)

        ttk.Label(self.header_frame, text="Vault Music", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.header_subtitle = ttk.Label(
            self.header_frame,
            text="Simple library, album, and playlist management for local files.",
            style="Hint.TLabel",
        )
        self.header_subtitle.grid(row=1, column=0, sticky="w", pady=(2, 0))
        self.dark_mode_toggle = ttk.Checkbutton(
            self.header_frame,
            text="Dark Mode",
            variable=self.dark_mode_var,
            command=self.toggle_dark_mode,
            style="ThemeToggle.TCheckbutton",
        )
        self.dark_mode_toggle.grid(row=0, column=1, rowspan=2, sticky="ne", padx=(12, 0))

        self.controls_card = ttk.Frame(self.container, padding=12, style="Card.TFrame")
        self.controls_card.pack(fill=tk.X)

        style = ttk.Style()
        style.configure("Treeview", rowheight=26)

        self.controls = ttk.Frame(self.controls_card, style="Card.TFrame")
        self.controls.pack(fill=tk.X)
        self.controls.columnconfigure(0, weight=1)

        self.transport_controls = ttk.Frame(self.controls, style="Card.TFrame")
        self.transport_controls.grid(row=0, column=0, sticky="w")

        self.utility_controls = ttk.Frame(self.controls, style="Card.TFrame")
        self.utility_controls.grid(row=0, column=1, sticky="e")

        self.transport_buttons = [
            ttk.Button(self.transport_controls, text="Play", command=self.play_selected, style="Action.TButton"),
            ttk.Button(self.transport_controls, text="Pause", command=self.pause_or_resume, style="Action.TButton"),
            ttk.Button(self.transport_controls, text="Stop", command=self.stop_playback, style="Action.TButton"),
            ttk.Button(self.transport_controls, text="Prev", command=self.previous_song, style="Action.TButton"),
            ttk.Button(self.transport_controls, text="Next", command=self.next_song, style="Action.TButton"),
        ]
        self.library_menu_button = self.create_menu_button(
            self.utility_controls,
            "Library",
            [
                {"label": "Open Songs Folder", "command": self.open_songs_folder},
                {"label": "Import Songs", "command": self.add_songs},
                {"label": "Import Album", "command": self.import_album},
            ],
        )
        self.utility_buttons = [self.library_menu_button]

        self.status_label = ttk.Label(self.container, text="No song playing", anchor="w", style="Status.TLabel")
        self.status_label.pack(fill=tk.X, pady=(10, 8))

        self.progress_frame = ttk.Frame(self.container, padding=12, style="Card.TFrame")
        self.progress_frame.pack(fill=tk.X, pady=(0, 12))
        self.progress_frame.columnconfigure(0, weight=1)

        self.analyzer_notebook = ttk.Notebook(self.progress_frame)
        self.analyzer_notebook.grid(row=0, column=0, columnspan=2, sticky="ew")

        self.spectrogram_tab = ttk.Frame(self.analyzer_notebook, style="Card.TFrame")
        self.spectrogram_tab.columnconfigure(0, weight=1)
        self.spectrogram_tab.rowconfigure(0, weight=1)

        self.analyzer_canvas = tk.Canvas(
            self.spectrogram_tab,
            height=154,
            background="#05070b",
            highlightthickness=1,
            highlightbackground=self.border_color,
            bd=0,
            cursor="hand2",
        )
        self.analyzer_canvas.grid(row=0, column=0, sticky="ew")
        self.analyzer_canvas.bind("<Configure>", lambda _event: self.draw_spectrogram())
        self.analyzer_canvas.bind("<ButtonPress-1>", self.on_progress_press)
        self.analyzer_canvas.bind("<B1-Motion>", self.on_progress_drag)
        self.analyzer_canvas.bind("<ButtonRelease-1>", self.on_progress_release)

        self.transient_tab = ttk.Frame(self.analyzer_notebook, style="Card.TFrame")
        self.transient_tab.columnconfigure(0, weight=1)
        self.transient_tab.rowconfigure(0, weight=1)

        self.transient_canvas = tk.Canvas(
            self.transient_tab,
            height=154,
            background="#050505",
            highlightthickness=1,
            highlightbackground=self.border_color,
            bd=0,
            cursor="hand2",
        )
        self.transient_canvas.grid(row=0, column=0, sticky="ew")
        self.transient_canvas.bind("<Configure>", lambda _event: self.draw_transient())
        self.transient_canvas.bind("<ButtonPress-1>", self.on_progress_press)
        self.transient_canvas.bind("<B1-Motion>", self.on_progress_drag)
        self.transient_canvas.bind("<ButtonRelease-1>", self.on_progress_release)

        self.analyzer_notebook.add(self.spectrogram_tab, text="Spectrogram")
        self.analyzer_notebook.add(self.transient_tab, text="Transient")

        self.analyzer_label = ttk.Label(
            self.progress_frame,
            text="Spectrogram analyzer",
            anchor="w",
            style="CardHint.TLabel",
        )
        self.analyzer_label.grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.time_label = ttk.Label(
            self.progress_frame,
            textvariable=self.time_label_var,
            width=14,
            anchor="e",
            style="CardHint.TLabel",
        )
        self.time_label.grid(row=1, column=1, padx=(12, 0), pady=(6, 0))
        self.analyzer_notebook.bind("<<NotebookTabChanged>>", self.on_analyzer_tab_changed)

        self.content = self.create_panedwindow(self.container, orient=tk.HORIZONTAL)
        self.content.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(self.content)

        self.build_songs_tab()
        self.build_albums_tab()
        self.build_playlist_sidebar()

        self.content.add(self.notebook, minsize=520, stretch="always")
        self.content.add(self.playlist_sidebar, minsize=320, stretch="always")

        self.root.bind("<Configure>", self.on_window_configure)
        self.root.after_idle(self.apply_responsive_layout)

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

        try:
            tkfont.nametofont("TkDefaultFont").configure(family="Helvetica Neue", size=12)
            tkfont.nametofont("TkTextFont").configure(family="Helvetica Neue", size=12)
            tkfont.nametofont("TkHeadingFont").configure(family="Helvetica Neue", size=13, weight="bold")
        except tk.TclError:
            pass

        style.configure(".", background=self.shell_bg, foreground=self.text_color)
        style.configure("Shell.TFrame", background=self.shell_bg)
        style.configure("Card.TFrame", background=self.card_bg, relief="flat")
        style.configure("Title.TLabel", background=self.shell_bg, foreground=self.text_color, font=("Helvetica Neue", 18, "bold"))
        style.configure("Hint.TLabel", background=self.shell_bg, foreground=self.muted_color, font=("Helvetica Neue", 11))
        style.configure("CardHint.TLabel", background=self.card_bg, foreground=self.muted_color, font=("Helvetica Neue", 11))
        style.configure("Status.TLabel", background=self.shell_bg, foreground=self.muted_color, font=("Helvetica Neue", 11))
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
            "TNotebook.Tab",
            background=[("selected", self.card_bg), ("active", self.menu_active_bg)],
            foreground=[("selected", self.text_color), ("active", self.text_color)],
        )
        style.map(
            "TEntry",
            fieldbackground=[("readonly", self.card_bg), ("disabled", self.card_bg)],
            foreground=[("disabled", self.muted_color)],
        )
        style.map(
            "Action.TButton",
            background=[("active", self.accent), ("pressed", self.accent_dark)],
            foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
        )
        style.map(
            "Action.TMenubutton",
            background=[("active", self.menu_active_bg), ("pressed", self.menu_active_bg)],
            foreground=[("active", self.text_color)],
        )
        self.apply_theme_to_tk_widgets()

    def apply_theme_to_tk_widgets(self):
        for panedwindow_name in ("content", "albums_content", "playlist_pane"):
            panedwindow = getattr(self, panedwindow_name, None)
            if panedwindow is not None:
                panedwindow.configure(background=self.border_color)

        waveform_canvas = getattr(self, "waveform_canvas", None)
        if waveform_canvas is not None:
            waveform_canvas.configure(background=self.card_bg, highlightbackground=self.border_color)

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

        self.draw_waveform()

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
            with open(self.paths.settings_db, "w", encoding="utf-8") as file:
                json.dump(settings, file, indent=2)
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

    def apply_app_icon(self):
        for icon_path in self.paths.icon_candidates:
            if not icon_path.exists() or icon_path.suffix.lower() != ".png":
                continue

            try:
                self.app_icon_image = tk.PhotoImage(file=str(icon_path))
                self.root.iconphoto(True, self.app_icon_image)
                return
            except tk.TclError:
                continue

    def configure_interactions(self):
        for variable in (
            self.song_search_var,
            self.album_search_var,
            self.album_song_search_var,
            self.playlist_search_var,
            self.playlist_song_search_var,
        ):
            variable.trace_add("write", self.on_filter_change)

        self.bind_context_menu(self.library_tree, self.show_library_context_menu)
        self.bind_context_menu(self.album_tree, self.show_album_context_menu)
        self.bind_context_menu(self.album_song_tree, self.show_album_song_context_menu)
        self.bind_context_menu(self.playlist_list, self.show_playlist_list_context_menu)
        self.bind_context_menu(self.playlist_tree, self.show_playlist_song_context_menu)

        self.library_tree.bind("<<TreeviewSelect>>", lambda _event: self.set_active_play_source("library"), add="+")
        self.album_tree.bind("<<TreeviewSelect>>", lambda _event: self.set_active_play_source("album"), add="+")
        self.album_song_tree.bind("<<TreeviewSelect>>", lambda _event: self.set_active_play_source("album_song"), add="+")
        self.playlist_list.bind("<<ListboxSelect>>", lambda _event: self.set_active_play_source("playlist"), add="+")
        self.playlist_tree.bind("<<TreeviewSelect>>", lambda _event: self.set_active_play_source("playlist_song"), add="+")

        for widget in (self.library_tree, self.album_tree, self.album_song_tree):
            widget.bind("<ButtonPress-1>", self.on_drag_press, add="+")
            widget.bind("<B1-Motion>", self.on_drag_motion, add="+")
            widget.bind("<ButtonRelease-1>", self.on_drag_release, add="+")

        for widget in (self.library_tree, self.album_tree, self.album_song_tree, self.playlist_tree):
            widget.bind("<Configure>", self.schedule_tree_column_update, add="+")

    def on_filter_change(self, *_args):
        self.refresh_all_views()

    def set_active_play_source(self, source):
        if self.syncing_playback_selection:
            return

        self.active_play_source = source

    def schedule_tree_column_update(self, *_args):
        if self.tree_resize_job is not None:
            self.root.after_cancel(self.tree_resize_job)

        self.tree_resize_job = self.root.after_idle(self.run_scheduled_tree_column_update)

    def run_scheduled_tree_column_update(self):
        self.tree_resize_job = None
        stacked_split_view = str(self.albums_content.cget("orient")) == str(tk.VERTICAL)
        self.update_tree_columns(stacked_split_view)

    def bind_context_menu(self, widget, handler):
        for sequence in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
            widget.bind(sequence, handler, add="+")

    def build_songs_tab(self):
        self.songs_tab = ttk.Frame(self.notebook, padding=10, style="Shell.TFrame")
        self.notebook.add(self.songs_tab, text="Songs")
        self.songs_tab.columnconfigure(0, weight=1)
        self.songs_tab.rowconfigure(2, weight=1)

        self.songs_hint_label = ttk.Label(
            self.songs_tab,
            text="Direct song view with fast search, batch edits, and drag-to-playlist.",
            anchor="w",
            style="Hint.TLabel",
        )
        self.songs_hint_label.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.songs_filter_frame = ttk.Frame(self.songs_tab, style="Shell.TFrame")
        self.songs_filter_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.songs_filter_frame.columnconfigure(1, weight=1)
        self.songs_filter_frame.columnconfigure(4, weight=1)

        self.song_search_label = ttk.Label(self.songs_filter_frame, text="Search", style="Hint.TLabel")
        self.song_search_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.song_search_entry = ttk.Entry(self.songs_filter_frame, textvariable=self.song_search_var)
        self.song_search_entry.grid(row=0, column=1, sticky="ew")
        self.song_clear_button = ttk.Button(
            self.songs_filter_frame,
            text="Clear",
            command=lambda: self.song_search_var.set(""),
            style="Action.TButton",
        )
        self.song_clear_button.grid(
            row=0,
            column=2,
            padx=(8, 12),
        )
        self.song_summary_label = ttk.Label(
            self.songs_filter_frame,
            textvariable=self.songs_summary_var,
            anchor="e",
            style="Hint.TLabel",
        )
        self.song_summary_label.grid(
            row=0,
            column=3,
            sticky="e",
            padx=(0, 12),
        )

        self.song_buttons_frame = ttk.Frame(self.songs_filter_frame, style="Shell.TFrame")
        self.song_buttons_frame.grid(row=0, column=4, sticky="e")
        self.song_import_button = self.create_menu_button(
            self.song_buttons_frame,
            "Import",
            [
                {"label": "Import Songs", "command": self.add_songs},
                {"label": "Import Album", "command": self.import_album},
            ],
        )
        self.song_edit_button = self.create_menu_button(
            self.song_buttons_frame,
            "Edit",
            [
                {"label": "Rename Song(s)", "command": self.rename_song},
                {"label": "Edit Artist", "command": self.edit_artist},
                {"label": "Set Album", "command": self.edit_album},
                "separator",
                {"label": "Remove Song(s)", "command": self.remove_song},
            ],
        )
        self.song_playlist_button = self.create_menu_button(
            self.song_buttons_frame,
            "Playlist",
            [
                {"label": "Add To Selected Playlist", "command": lambda: self.add_song_ids_to_selected_playlist(self.get_selected_library_song_ids())},
                {"label": "Add To Playlist...", "command": self.add_selected_songs_to_playlist},
            ],
        )
        self.song_action_buttons = [
            self.song_import_button,
            ttk.Button(self.song_buttons_frame, text="Play", command=self.play_selected_library_song, style="Action.TButton"),
            self.song_edit_button,
            self.song_playlist_button,
        ]

        songs_tree_frame = ttk.Frame(self.songs_tab, style="Card.TFrame")
        songs_tree_frame.grid(row=2, column=0, sticky="nsew")
        songs_tree_frame.columnconfigure(0, weight=1)
        songs_tree_frame.rowconfigure(0, weight=1)

        self.library_tree = ttk.Treeview(
            songs_tree_frame,
            columns=("title", "artist", "album", "bpm", "plays", "filename"),
            show="headings",
            selectmode="extended",
        )
        self.library_tree.heading("title", text="Title")
        self.library_tree.heading("artist", text="Artist")
        self.library_tree.heading("album", text="Album")
        self.library_tree.heading("bpm", text="BPM")
        self.library_tree.heading("plays", text="Plays")
        self.library_tree.heading("filename", text="File")
        self.library_tree.grid(row=0, column=0, sticky="nsew")
        self.library_tree.bind("<Double-1>", lambda _event: self.play_selected_library_song())

        library_scrollbar = ttk.Scrollbar(songs_tree_frame, orient=tk.VERTICAL, command=self.library_tree.yview)
        library_scrollbar.grid(row=0, column=1, sticky="ns")
        library_x_scrollbar = ttk.Scrollbar(songs_tree_frame, orient=tk.HORIZONTAL, command=self.library_tree.xview)
        library_x_scrollbar.grid(row=1, column=0, sticky="ew")
        self.library_tree.configure(yscrollcommand=library_scrollbar.set, xscrollcommand=library_x_scrollbar.set)

    def build_albums_tab(self):
        self.albums_tab = ttk.Frame(self.notebook, padding=10, style="Shell.TFrame")
        self.notebook.add(self.albums_tab, text="Albums")
        self.albums_tab.columnconfigure(0, weight=1)
        self.albums_tab.rowconfigure(2, weight=1)

        self.albums_hint_label = ttk.Label(
            self.albums_tab,
            text="Album-first browsing keeps releases together and ready to queue or export into playlists.",
            anchor="w",
            style="Hint.TLabel",
        )
        self.albums_hint_label.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.albums_content = self.create_panedwindow(self.albums_tab, orient=tk.HORIZONTAL)
        self.albums_content.grid(row=2, column=0, sticky="nsew")

        self.album_list_frame = ttk.LabelFrame(self.albums_content, text="Albums", padding=10, style="Panel.TLabelframe")
        self.album_list_frame.columnconfigure(0, weight=1)
        self.album_list_frame.rowconfigure(1, weight=1)

        self.album_filter_frame = ttk.Frame(self.album_list_frame, style="Shell.TFrame")
        self.album_filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.album_filter_frame.columnconfigure(1, weight=1)
        self.album_filter_frame.columnconfigure(3, weight=1)

        self.album_search_label = ttk.Label(self.album_filter_frame, text="Search", style="Hint.TLabel")
        self.album_search_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.album_search_entry = ttk.Entry(self.album_filter_frame, textvariable=self.album_search_var)
        self.album_search_entry.grid(row=0, column=1, sticky="ew")
        self.album_clear_button = ttk.Button(
            self.album_filter_frame,
            text="Clear",
            command=lambda: self.album_search_var.set(""),
            style="Action.TButton",
        )
        self.album_clear_button.grid(
            row=0,
            column=2,
            padx=(8, 12),
        )

        self.album_buttons_frame = ttk.Frame(self.album_filter_frame, style="Shell.TFrame")
        self.album_buttons_frame.grid(row=0, column=3, sticky="e")
        self.album_playlist_button = self.create_menu_button(
            self.album_buttons_frame,
            "Playlist",
            [
                {"label": "Add Album To Selected Playlist", "command": lambda: self.add_song_ids_to_selected_playlist(self.library.album_queue(self.get_selected_album_key() or ""))},
                {"label": "Add Album To Playlist...", "command": lambda: self.add_song_ids_to_playlist(self.library.album_queue(self.get_selected_album_key() or ""))},
            ],
        )
        self.album_action_buttons = [
            ttk.Button(self.album_buttons_frame, text="Import Album", command=self.import_album, style="Action.TButton"),
            ttk.Button(self.album_buttons_frame, text="Play Album", command=self.play_album, style="Action.TButton"),
            self.album_playlist_button,
        ]

        album_tree_frame = ttk.Frame(self.album_list_frame)
        album_tree_frame.grid(row=1, column=0, sticky="nsew")
        album_tree_frame.columnconfigure(0, weight=1)
        album_tree_frame.rowconfigure(0, weight=1)

        self.album_tree = ttk.Treeview(
            album_tree_frame,
            columns=("album", "artist", "songs"),
            show="headings",
            selectmode="browse",
        )
        self.album_tree.heading("album", text="Album")
        self.album_tree.heading("artist", text="Artist")
        self.album_tree.heading("songs", text="Songs")
        self.album_tree.grid(row=0, column=0, sticky="nsew")
        self.album_tree.bind("<<TreeviewSelect>>", lambda _event: self.refresh_album_song_tree())
        self.album_tree.bind("<Double-1>", lambda _event: self.play_album())

        album_scrollbar = ttk.Scrollbar(album_tree_frame, orient=tk.VERTICAL, command=self.album_tree.yview)
        album_scrollbar.grid(row=0, column=1, sticky="ns")
        album_x_scrollbar = ttk.Scrollbar(album_tree_frame, orient=tk.HORIZONTAL, command=self.album_tree.xview)
        album_x_scrollbar.grid(row=1, column=0, sticky="ew")
        self.album_tree.configure(yscrollcommand=album_scrollbar.set, xscrollcommand=album_x_scrollbar.set)

        self.album_song_frame = ttk.LabelFrame(self.albums_content, text="Album Songs", padding=10, style="Panel.TLabelframe")
        self.album_song_frame.columnconfigure(0, weight=1)
        self.album_song_frame.rowconfigure(1, weight=1)

        self.album_song_filter_frame = ttk.Frame(self.album_song_frame, style="Shell.TFrame")
        self.album_song_filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.album_song_filter_frame.columnconfigure(1, weight=1)
        self.album_song_filter_frame.columnconfigure(3, weight=1)

        self.album_song_search_label = ttk.Label(self.album_song_filter_frame, text="Filter Tracks", style="Hint.TLabel")
        self.album_song_search_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.album_song_search_entry = ttk.Entry(self.album_song_filter_frame, textvariable=self.album_song_search_var)
        self.album_song_search_entry.grid(row=0, column=1, sticky="ew")
        self.album_song_clear_button = ttk.Button(
            self.album_song_filter_frame,
            text="Clear",
            command=lambda: self.album_song_search_var.set(""),
            style="Action.TButton",
        )
        self.album_song_clear_button.grid(row=0, column=2, padx=(8, 12))

        self.album_song_buttons_frame = ttk.Frame(self.album_song_filter_frame, style="Shell.TFrame")
        self.album_song_buttons_frame.grid(row=0, column=3, sticky="e")
        self.album_song_edit_button = self.create_menu_button(
            self.album_song_buttons_frame,
            "Edit",
            [
                {"label": "Rename Track(s)", "command": lambda: self.rename_song(self.get_selected_album_song_ids() or self.visible_album_song_ids)},
                {"label": "Edit Artist", "command": lambda: self.edit_artist(self.get_selected_album_song_ids() or self.visible_album_song_ids)},
                {"label": "Set Album", "command": lambda: self.edit_album(self.get_selected_album_song_ids() or self.visible_album_song_ids)},
                "separator",
                {"label": "Remove Track(s)", "command": lambda: self.remove_song(self.get_selected_album_song_ids() or self.visible_album_song_ids)},
            ],
        )
        self.album_song_playlist_button = self.create_menu_button(
            self.album_song_buttons_frame,
            "Playlist",
            [
                {"label": "Add To Selected Playlist", "command": lambda: self.add_song_ids_to_selected_playlist(self.get_selected_album_song_ids() or self.visible_album_song_ids)},
                {"label": "Add To Playlist...", "command": self.add_selected_album_songs_to_playlist},
            ],
        )
        self.album_song_action_buttons = [
            ttk.Button(self.album_song_buttons_frame, text="Play", command=self.play_selected_album_song, style="Action.TButton"),
            self.album_song_edit_button,
            self.album_song_playlist_button,
        ]

        album_song_tree_frame = ttk.Frame(self.album_song_frame)
        album_song_tree_frame.grid(row=1, column=0, sticky="nsew")
        album_song_tree_frame.columnconfigure(0, weight=1)
        album_song_tree_frame.rowconfigure(0, weight=1)

        self.album_song_tree = ttk.Treeview(
            album_song_tree_frame,
            columns=("title", "artist", "bpm", "plays", "filename"),
            show="headings",
            selectmode="extended",
        )
        self.album_song_tree.heading("title", text="Title")
        self.album_song_tree.heading("artist", text="Artist")
        self.album_song_tree.heading("bpm", text="BPM")
        self.album_song_tree.heading("plays", text="Plays")
        self.album_song_tree.heading("filename", text="File")
        self.album_song_tree.grid(row=0, column=0, sticky="nsew")
        self.album_song_tree.bind("<Double-1>", lambda _event: self.play_selected_album_song())

        album_song_scrollbar = ttk.Scrollbar(
            album_song_tree_frame,
            orient=tk.VERTICAL,
            command=self.album_song_tree.yview,
        )
        album_song_scrollbar.grid(row=0, column=1, sticky="ns")
        album_song_x_scrollbar = ttk.Scrollbar(
            album_song_tree_frame,
            orient=tk.HORIZONTAL,
            command=self.album_song_tree.xview,
        )
        album_song_x_scrollbar.grid(row=1, column=0, sticky="ew")
        self.album_song_tree.configure(yscrollcommand=album_song_scrollbar.set, xscrollcommand=album_song_x_scrollbar.set)

        self.albums_content.add(self.album_list_frame, minsize=300, stretch="always")
        self.albums_content.add(self.album_song_frame, minsize=360, stretch="always")

    def build_playlist_sidebar(self):
        self.playlist_sidebar = ttk.Frame(self.content, style="Shell.TFrame")
        self.playlist_sidebar.columnconfigure(0, weight=1)
        self.playlist_sidebar.rowconfigure(1, weight=1)

        self.playlists_hint_label = ttk.Label(
            self.playlist_sidebar,
            text="Keep playlists open while browsing, then drag songs or albums straight into them.",
            anchor="w",
            style="Hint.TLabel",
        )
        self.playlists_hint_label.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.playlist_pane = self.create_panedwindow(self.playlist_sidebar, orient=tk.VERTICAL)
        self.playlist_pane.grid(row=1, column=0, sticky="nsew")

        self.playlist_list_frame = ttk.LabelFrame(self.playlist_pane, text="Playlists", padding=10, style="Panel.TLabelframe")
        self.playlist_list_frame.columnconfigure(0, weight=1)
        self.playlist_list_frame.rowconfigure(1, weight=1)

        self.playlist_filter_frame = ttk.Frame(self.playlist_list_frame, style="Shell.TFrame")
        self.playlist_filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.playlist_filter_frame.columnconfigure(1, weight=1)
        self.playlist_filter_frame.columnconfigure(3, weight=1)

        self.playlist_search_label = ttk.Label(self.playlist_filter_frame, text="Search", style="Hint.TLabel")
        self.playlist_search_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.playlist_search_entry = ttk.Entry(self.playlist_filter_frame, textvariable=self.playlist_search_var)
        self.playlist_search_entry.grid(row=0, column=1, sticky="ew")
        self.playlist_clear_button = ttk.Button(
            self.playlist_filter_frame,
            text="Clear",
            command=lambda: self.playlist_search_var.set(""),
            style="Action.TButton",
        )
        self.playlist_clear_button.grid(row=0, column=2, padx=(8, 12))

        self.playlist_buttons_frame = ttk.Frame(self.playlist_filter_frame, style="Shell.TFrame")
        self.playlist_buttons_frame.grid(row=0, column=3, sticky="e")
        self.playlist_manage_button = self.create_menu_button(
            self.playlist_buttons_frame,
            "Manage",
            [
                {"label": "Rename Playlist", "command": self.rename_playlist},
                {"label": "Delete Playlist", "command": self.delete_playlist},
                "separator",
                {"label": "Export Playlist", "command": self.export_playlist},
            ],
        )
        self.playlist_action_buttons = [
            ttk.Button(self.playlist_buttons_frame, text="New Playlist", command=self.create_playlist, style="Action.TButton"),
            self.playlist_manage_button,
        ]

        playlist_browser_frame = ttk.Frame(self.playlist_list_frame)
        playlist_browser_frame.grid(row=1, column=0, sticky="nsew")
        playlist_browser_frame.columnconfigure(0, weight=1)
        playlist_browser_frame.rowconfigure(0, weight=1)

        self.playlist_list = tk.Listbox(playlist_browser_frame, exportselection=False)
        self.playlist_list.grid(row=0, column=0, sticky="nsew")
        self.playlist_list.configure(
            activestyle="none",
            background=self.card_bg,
            borderwidth=0,
            foreground=self.text_color,
            highlightthickness=0,
            relief="flat",
            selectbackground=self.selection_bg,
            selectforeground=self.text_color,
        )
        self.playlist_list.bind("<<ListboxSelect>>", lambda _event: self.refresh_playlist_tree())

        playlist_scrollbar = ttk.Scrollbar(playlist_browser_frame, orient=tk.VERTICAL, command=self.playlist_list.yview)
        playlist_scrollbar.grid(row=0, column=1, sticky="ns")
        self.playlist_list.configure(yscrollcommand=playlist_scrollbar.set)

        self.playlist_song_frame = ttk.LabelFrame(self.playlist_pane, text="Playlist Songs", padding=10, style="Panel.TLabelframe")
        self.playlist_song_frame.columnconfigure(0, weight=1)
        self.playlist_song_frame.rowconfigure(1, weight=1)

        self.playlist_song_filter_frame = ttk.Frame(self.playlist_song_frame, style="Shell.TFrame")
        self.playlist_song_filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.playlist_song_filter_frame.columnconfigure(1, weight=1)
        self.playlist_song_filter_frame.columnconfigure(3, weight=1)

        self.playlist_song_search_label = ttk.Label(self.playlist_song_filter_frame, text="Filter Tracks", style="Hint.TLabel")
        self.playlist_song_search_label.grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.playlist_song_search_entry = ttk.Entry(
            self.playlist_song_filter_frame,
            textvariable=self.playlist_song_search_var,
        )
        self.playlist_song_search_entry.grid(row=0, column=1, sticky="ew")
        self.playlist_song_clear_button = ttk.Button(
            self.playlist_song_filter_frame,
            text="Clear",
            command=lambda: self.playlist_song_search_var.set(""),
            style="Action.TButton",
        )
        self.playlist_song_clear_button.grid(row=0, column=2, padx=(8, 12))

        self.playlist_song_buttons_frame = ttk.Frame(self.playlist_song_filter_frame, style="Shell.TFrame")
        self.playlist_song_buttons_frame.grid(row=0, column=3, sticky="e")
        self.playlist_song_action_buttons = [
            ttk.Button(self.playlist_song_buttons_frame, text="Play", command=self.play_selected_playlist_song, style="Action.TButton"),
            ttk.Button(
                self.playlist_song_buttons_frame,
                text="Remove",
                command=self.remove_song_from_playlist,
                style="Action.TButton",
            ),
        ]

        playlist_song_tree_frame = ttk.Frame(self.playlist_song_frame)
        playlist_song_tree_frame.grid(row=1, column=0, sticky="nsew")
        playlist_song_tree_frame.columnconfigure(0, weight=1)
        playlist_song_tree_frame.rowconfigure(0, weight=1)

        self.playlist_tree = ttk.Treeview(
            playlist_song_tree_frame,
            columns=("title", "artist", "album", "bpm", "plays"),
            show="headings",
            selectmode="browse",
        )
        self.playlist_tree.heading("title", text="Title")
        self.playlist_tree.heading("artist", text="Artist")
        self.playlist_tree.heading("album", text="Album")
        self.playlist_tree.heading("bpm", text="BPM")
        self.playlist_tree.heading("plays", text="Plays")
        self.playlist_tree.grid(row=0, column=0, sticky="nsew")
        self.playlist_tree.bind("<Double-1>", lambda _event: self.play_selected_playlist_song())

        playlist_song_scrollbar = ttk.Scrollbar(
            playlist_song_tree_frame,
            orient=tk.VERTICAL,
            command=self.playlist_tree.yview,
        )
        playlist_song_scrollbar.grid(row=0, column=1, sticky="ns")
        playlist_song_x_scrollbar = ttk.Scrollbar(
            playlist_song_tree_frame,
            orient=tk.HORIZONTAL,
            command=self.playlist_tree.xview,
        )
        playlist_song_x_scrollbar.grid(row=1, column=0, sticky="ew")
        self.playlist_tree.configure(yscrollcommand=playlist_song_scrollbar.set, xscrollcommand=playlist_song_x_scrollbar.set)

        self.playlist_pane.add(self.playlist_list_frame, minsize=110, stretch="always")
        self.playlist_pane.add(self.playlist_song_frame, minsize=130, stretch="always")


    def create_panedwindow(self, parent, orient):
        return tk.PanedWindow(
            parent,
            orient=orient,
            background=self.border_color,
            borderwidth=0,
            sashwidth=6,
            showhandle=False,
            relief=tk.FLAT,
        )

    def layout_button_group(self, frame, buttons, preferred_columns=None, fill=False):
        columns = max(1, min(len(buttons), preferred_columns or len(buttons)))

        for button in buttons:
            button.grid_forget()
            try:
                label_width = max(8, min(14, len(str(button.cget("text"))) + 2))
                button.configure(width=label_width)
            except tk.TclError:
                pass

        for index in range(len(buttons)):
            frame.grid_columnconfigure(index, weight=0)

        for index, button in enumerate(buttons):
            row = index // columns
            column = index % columns
            button.grid(
                row=row,
                column=column,
                sticky="ew" if fill else "w",
                padx=4,
                pady=4,
            )

        if fill:
            for column in range(columns):
                frame.grid_columnconfigure(column, weight=1)

    def reflow_filter_search(self, label, entry, clear_button, compact):
        if compact:
            label.grid_remove()
            entry.grid_configure(column=0, columnspan=2, sticky="ew")
            clear_button.grid_configure(column=2, padx=(8, 0))
        else:
            label.grid()
            entry.grid_configure(column=1, columnspan=1, sticky="ew")
            clear_button.grid_configure(column=2, padx=(8, 12))

    def reflow_filter_actions(self, filter_frame, buttons_frame, stacked, button_column, column_span):
        if stacked:
            buttons_frame.grid_configure(row=1, column=0, columnspan=column_span, sticky="ew", pady=(8, 0))
        else:
            buttons_frame.grid_configure(row=0, column=button_column, columnspan=1, sticky="e", pady=0)

        for column in range(column_span):
            filter_frame.grid_columnconfigure(column, weight=0)

        filter_frame.grid_columnconfigure(1, weight=1)
        if stacked:
            filter_frame.grid_columnconfigure(0, weight=1)

    def set_grid_visibility(self, widget, visible):
        if visible:
            widget.grid()
        else:
            widget.grid_remove()

    def widget_width(self, widget, fallback):
        width = widget.winfo_width()
        return width if width > 1 else fallback

    def paneconfigure_safe(self, panedwindow, child, **options):
        try:
            panedwindow.paneconfigure(child, **options)
        except tk.TclError:
            pass

    def configure_pane_limits(self, content_stacked, albums_stacked):
        if content_stacked:
            self.paneconfigure_safe(self.content, self.notebook, minsize=230)
            self.paneconfigure_safe(self.content, self.playlist_sidebar, minsize=170)
        else:
            self.paneconfigure_safe(self.content, self.notebook, minsize=520)
            self.paneconfigure_safe(self.content, self.playlist_sidebar, minsize=320)

        if albums_stacked:
            self.paneconfigure_safe(self.albums_content, self.album_list_frame, minsize=150)
            self.paneconfigure_safe(self.albums_content, self.album_song_frame, minsize=180)
        else:
            self.paneconfigure_safe(self.albums_content, self.album_list_frame, minsize=300)
            self.paneconfigure_safe(self.albums_content, self.album_song_frame, minsize=360)

        self.paneconfigure_safe(self.playlist_pane, self.playlist_list_frame, minsize=110)
        self.paneconfigure_safe(self.playlist_pane, self.playlist_song_frame, minsize=130)

    def set_sash_position(self, panedwindow, index, position):
        try:
            position = max(0, int(position))
            if hasattr(panedwindow, "sashpos"):
                panedwindow.sashpos(index, position)
            elif str(panedwindow.cget("orient")) == str(tk.HORIZONTAL):
                panedwindow.sash_place(index, position, 0)
            else:
                panedwindow.sash_place(index, 0, position)
        except (AttributeError, tk.TclError):
            pass

    def apply_initial_pane_layout(self):
        self.root.update_idletasks()

        content_orient = str(self.content.cget("orient"))
        albums_orient = str(self.albums_content.cget("orient"))
        playlist_orient = str(self.playlist_pane.cget("orient"))

        content_size = self.content.winfo_width() if content_orient == str(tk.HORIZONTAL) else self.content.winfo_height()
        albums_size = self.albums_content.winfo_width() if albums_orient == str(tk.HORIZONTAL) else self.albums_content.winfo_height()
        playlist_size = self.playlist_pane.winfo_width() if playlist_orient == str(tk.HORIZONTAL) else self.playlist_pane.winfo_height()

        if content_size > 0:
            main_ratio = 0.56 if content_orient == str(tk.HORIZONTAL) else 0.58
            self.set_sash_position(self.content, 0, content_size * main_ratio)

        if albums_size > 0:
            albums_ratio = 0.38 if albums_orient == str(tk.HORIZONTAL) else 0.42
            self.set_sash_position(self.albums_content, 0, albums_size * albums_ratio)

        if playlist_size > 0:
            playlist_ratio = 0.40 if playlist_orient == str(tk.VERTICAL) else 0.42
            self.set_sash_position(self.playlist_pane, 0, playlist_size * playlist_ratio)

    def on_window_configure(self, event):
        if event.widget is not self.root:
            return

        if self.resize_job is not None:
            self.root.after_cancel(self.resize_job)

        self.resize_job = self.root.after(60, self.apply_responsive_layout)

    def apply_responsive_layout(self):
        self.resize_job = None
        width = max(self.root.winfo_width(), self.root.winfo_reqwidth())
        height = max(self.root.winfo_height(), self.root.winfo_reqheight())

        compact_controls = width < 1180
        narrow_controls = width < 920
        stacked_main_content = width < 1100 and height >= 720
        stacked_split_view = width < 1040
        compact_chrome = width < 980 or height < 660
        hidden_hints = width < 1120 or height < 700
        hidden_summary = width < 1160 or height < 660

        next_album_orient = tk.VERTICAL if stacked_split_view else tk.HORIZONTAL
        next_content_orient = tk.VERTICAL if stacked_main_content else tk.HORIZONTAL
        content_stacked = next_content_orient == tk.VERTICAL
        albums_stacked = next_album_orient == tk.VERTICAL
        available_width = max(width - (20 if compact_chrome else 28), 320)
        main_width = available_width if content_stacked else self.widget_width(self.notebook, int(available_width * 0.57))
        sidebar_width = available_width if content_stacked else self.widget_width(self.playlist_sidebar, int(available_width * 0.38))
        album_list_width = available_width if albums_stacked else self.widget_width(self.album_list_frame, int(main_width * 0.38))
        album_song_width = available_width if albums_stacked else self.widget_width(self.album_song_frame, int(main_width * 0.56))
        song_filter_width = self.widget_width(self.songs_filter_frame, main_width)
        album_filter_width = self.widget_width(self.album_filter_frame, album_list_width)
        album_song_filter_width = self.widget_width(self.album_song_filter_frame, album_song_width)
        playlist_filter_width = self.widget_width(self.playlist_filter_frame, sidebar_width)
        playlist_song_filter_width = self.widget_width(self.playlist_song_filter_frame, sidebar_width)

        stacked_song_actions = song_filter_width < 900
        stacked_album_actions = album_filter_width < 620
        stacked_album_song_actions = album_song_filter_width < 660
        stacked_playlist_actions = playlist_filter_width < 560
        stacked_playlist_song_actions = playlist_song_filter_width < 520

        self.container.configure(padding=10 if compact_chrome else 14)
        self.controls_card.configure(padding=8 if compact_chrome else 12)
        self.progress_frame.configure(padding=8 if compact_chrome else 12)
        analyzer_height = 112 if compact_chrome else 154
        self.analyzer_canvas.configure(height=analyzer_height)
        self.transient_canvas.configure(height=analyzer_height)
        self.set_grid_visibility(self.header_subtitle, not compact_chrome)
        self.set_grid_visibility(self.songs_hint_label, not hidden_hints)
        self.set_grid_visibility(self.albums_hint_label, not hidden_hints)
        self.set_grid_visibility(self.playlists_hint_label, not hidden_hints)
        self.set_grid_visibility(self.song_summary_label, not hidden_summary)

        self.layout_button_group(
            self.transport_controls,
            self.transport_buttons,
            5 if not compact_controls else 3 if not narrow_controls else 2,
        )
        self.layout_button_group(self.utility_controls, self.utility_buttons, 1)
        self.layout_button_group(
            self.song_buttons_frame,
            self.song_action_buttons,
            4 if song_filter_width >= 860 else 3 if song_filter_width >= 640 else 2,
            fill=stacked_song_actions and song_filter_width < 720,
        )
        self.layout_button_group(
            self.album_buttons_frame,
            self.album_action_buttons,
            3 if album_filter_width >= 720 else 2 if album_filter_width >= 520 else 1,
            fill=stacked_album_actions and album_filter_width < 540,
        )
        self.layout_button_group(
            self.album_song_buttons_frame,
            self.album_song_action_buttons,
            3 if album_song_filter_width >= 720 else 2 if album_song_filter_width >= 520 else 1,
            fill=stacked_album_song_actions and album_song_filter_width < 540,
        )
        self.layout_button_group(
            self.playlist_buttons_frame,
            self.playlist_action_buttons,
            2 if playlist_filter_width >= 440 else 1,
            fill=stacked_playlist_actions,
        )
        self.layout_button_group(
            self.playlist_song_buttons_frame,
            self.playlist_song_action_buttons,
            2 if playlist_song_filter_width >= 420 else 1,
            fill=stacked_playlist_song_actions,
        )

        self.reflow_filter_search(self.song_search_label, self.song_search_entry, self.song_clear_button, song_filter_width < 560)
        self.reflow_filter_search(self.album_search_label, self.album_search_entry, self.album_clear_button, album_filter_width < 480)
        self.reflow_filter_search(
            self.album_song_search_label,
            self.album_song_search_entry,
            self.album_song_clear_button,
            album_song_filter_width < 500,
        )
        self.reflow_filter_search(self.playlist_search_label, self.playlist_search_entry, self.playlist_clear_button, playlist_filter_width < 430)
        self.reflow_filter_search(
            self.playlist_song_search_label,
            self.playlist_song_search_entry,
            self.playlist_song_clear_button,
            playlist_song_filter_width < 430,
        )

        self.reflow_filter_actions(self.songs_filter_frame, self.song_buttons_frame, stacked_song_actions, 4, 5)
        self.reflow_filter_actions(self.album_filter_frame, self.album_buttons_frame, stacked_album_actions, 3, 4)
        self.reflow_filter_actions(self.album_song_filter_frame, self.album_song_buttons_frame, stacked_album_song_actions, 3, 4)
        self.reflow_filter_actions(self.playlist_filter_frame, self.playlist_buttons_frame, stacked_playlist_actions, 3, 4)
        self.reflow_filter_actions(self.playlist_song_filter_frame, self.playlist_song_buttons_frame, stacked_playlist_song_actions, 3, 4)

        self.transport_controls.grid_configure(row=0, column=0, sticky="w")
        if compact_controls:
            self.utility_controls.grid_configure(row=1, column=0, sticky="w", pady=(4, 0))
        else:
            self.utility_controls.grid_configure(row=0, column=1, sticky="e", pady=0)

        album_orient_changed = str(self.albums_content.cget("orient")) != str(next_album_orient)
        content_orient_changed = str(self.content.cget("orient")) != str(next_content_orient)

        self.configure_split_view(self.albums_content, stacked_split_view)
        self.content.configure(orient=next_content_orient)
        self.playlist_pane.configure(orient=tk.VERTICAL)
        self.configure_pane_limits(content_stacked, albums_stacked)

        if not self.initial_pane_layout_applied or album_orient_changed or content_orient_changed:
            self.initial_pane_layout_applied = True
            self.root.after_idle(self.apply_initial_pane_layout)

        self.status_label.configure(wraplength=max(width - 48, 320))
        self.update_tree_columns(stacked_split_view)

    def configure_split_view(self, panedwindow, stacked):
        panedwindow.configure(orient=tk.VERTICAL if stacked else tk.HORIZONTAL)

    def update_tree_columns(self, stacked_split_view):
        songs_width = max(self.library_tree.winfo_width(), 620)
        songs_usable = max(songs_width - 24, 520)
        plays_width = 70
        bpm_width = 74
        title_width = max(170, int(songs_usable * 0.24))
        artist_width = max(130, int(songs_usable * 0.18))
        album_width = max(150, int(songs_usable * 0.21))
        filename_width = max(150, songs_usable - title_width - artist_width - album_width - bpm_width - plays_width)
        self.library_tree.column("title", width=title_width, minwidth=140, stretch=True)
        self.library_tree.column("artist", width=artist_width, minwidth=110, stretch=True)
        self.library_tree.column("album", width=album_width, minwidth=120, stretch=True)
        self.library_tree.column("bpm", width=bpm_width, minwidth=70, stretch=False, anchor="center")
        self.library_tree.column("plays", width=plays_width, minwidth=60, stretch=False, anchor="center")
        self.library_tree.column("filename", width=filename_width, minwidth=140, stretch=True)

        album_list_width = max(self.album_tree.winfo_width(), 320)
        album_list_usable = max(album_list_width - 24, 260)
        album_title_width = max(140, int(album_list_usable * 0.48))
        album_artist_width = max(110, int(album_list_usable * 0.30))
        album_count_width = max(70, album_list_usable - album_title_width - album_artist_width)
        self.album_tree.column("album", width=album_title_width, minwidth=130, stretch=True)
        self.album_tree.column("artist", width=album_artist_width, minwidth=100, stretch=True)
        self.album_tree.column("songs", width=album_count_width, minwidth=60, stretch=False, anchor="center")

        album_song_width = max(self.album_song_tree.winfo_width(), 420 if not stacked_split_view else 560)
        album_song_usable = max(album_song_width - 24, 340)
        song_plays_width = 70
        song_bpm_width = 74
        song_title_width = max(170, int(album_song_usable * 0.35))
        song_artist_width = max(120, int(album_song_usable * 0.20))
        song_filename_width = max(140, album_song_usable - song_title_width - song_artist_width - song_bpm_width - song_plays_width)
        self.album_song_tree.column("title", width=song_title_width, minwidth=140, stretch=True)
        self.album_song_tree.column("artist", width=song_artist_width, minwidth=110, stretch=True)
        self.album_song_tree.column("bpm", width=song_bpm_width, minwidth=70, stretch=False, anchor="center")
        self.album_song_tree.column("plays", width=song_plays_width, minwidth=60, stretch=False, anchor="center")
        self.album_song_tree.column("filename", width=song_filename_width, minwidth=130, stretch=True)

        playlist_width = max(self.playlist_tree.winfo_width(), 420 if not stacked_split_view else 560)
        playlist_usable = max(playlist_width - 24, 340)
        playlist_plays_width = 70
        playlist_bpm_width = 74
        playlist_title_width = max(160, int(playlist_usable * 0.32))
        playlist_artist_width = max(120, int(playlist_usable * 0.20))
        playlist_album_width = max(130, playlist_usable - playlist_title_width - playlist_artist_width - playlist_bpm_width - playlist_plays_width)
        self.playlist_tree.column("title", width=playlist_title_width, minwidth=140, stretch=True)
        self.playlist_tree.column("artist", width=playlist_artist_width, minwidth=110, stretch=True)
        self.playlist_tree.column("album", width=playlist_album_width, minwidth=120, stretch=True)
        self.playlist_tree.column("bpm", width=playlist_bpm_width, minwidth=70, stretch=False, anchor="center")
        self.playlist_tree.column("plays", width=playlist_plays_width, minwidth=60, stretch=False, anchor="center")

    def normalized_query(self, value):
        return value.strip().casefold()

    def song_matches_query(self, song, query):
        if not query:
            return True

        fields = (
            song.title,
            song.artist or "",
            song.album or "",
            song.filename,
            str(song.bpm or ""),
        )
        return any(query in field.casefold() for field in fields)

    def album_matches_query(self, summary, query):
        if not query:
            return True

        if query in summary.title.casefold() or query in summary.artist_label.casefold():
            return True

        return any(self.song_matches_query(song, query) for song in self.library.album_songs(summary.key))

    def songs_from_ids(self, song_ids):
        songs = []
        seen = set()
        for song_id in song_ids:
            if song_id in seen:
                continue

            song = self.library.get_song(song_id)
            if song is None:
                continue

            songs.append(song)
            seen.add(song_id)

        return songs

    def select_playlist_by_name(self, playlist_name):
        if playlist_name not in self.playlist_names:
            return False

        index = self.playlist_names.index(playlist_name)
        self.playlist_list.selection_clear(0, tk.END)
        self.playlist_list.selection_set(index)
        self.playlist_list.activate(index)
        self.playlist_list.see(index)
        return True

    def tree_item_at_y(self, tree, y):
        item_id = tree.identify_row(y)
        if not item_id:
            return None
        return item_id if tree.bbox(item_id) else None

    def select_tree_item_for_event(self, tree, event, browse=False):
        item_id = self.tree_item_at_y(tree, event.y)
        if item_id is None:
            return None

        current_selection = set(tree.selection())
        if browse or item_id not in current_selection:
            tree.selection_set(item_id)
        tree.focus(item_id)

        if tree is self.album_tree:
            self.refresh_album_song_tree()

        return item_id

    def playlist_name_at_y(self, y):
        if not self.playlist_names:
            return None

        index = self.playlist_list.nearest(y)
        if index < 0 or index >= len(self.playlist_names):
            return None

        bbox = self.playlist_list.bbox(index)
        if bbox is None:
            return None

        _x, row_y, _width, row_height = bbox
        if y < row_y or y > row_y + row_height:
            return None

        return self.playlist_names[index]

    def select_playlist_at_event(self, event):
        playlist_name = self.playlist_name_at_y(event.y)
        if playlist_name is None:
            return None

        self.select_playlist_by_name(playlist_name)
        self.refresh_playlist_tree()
        return playlist_name

    def playlist_name_at_pointer(self):
        pointer_x = self.root.winfo_pointerx()
        pointer_y = self.root.winfo_pointery()
        widget = self.root.winfo_containing(pointer_x, pointer_y)
        if widget is not self.playlist_list:
            return None

        local_y = pointer_y - self.playlist_list.winfo_rooty()
        return self.playlist_name_at_y(local_y)

    def popup_menu(self, menu, event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def refresh_status_for_current_state(self):
        if self.current_song_id:
            song = self.library.get_song(self.current_song_id)
            if song:
                if self.player.paused:
                    self.status_label.config(text=f"Paused: {describe_song(song)}")
                else:
                    self.status_label.config(text=f"Now playing: {describe_song(song)}")
                return

        self.status_label.config(text="No song playing")

    def refresh_all_views(self):
        self.refresh_library_tree()
        self.refresh_album_tree()
        self.refresh_playlist_list()
        self.refresh_playlist_tree()

    def song_tree_values(self, tree, song):
        if tree is self.library_tree:
            return (
                song.title,
                song.artist or "Unknown Artist",
                song.album or "Singles / Unassigned",
                self.bpm_label(song),
                song.play_count,
                song.filename,
            )

        if tree is self.album_song_tree:
            return (song.title, song.artist or "Unknown Artist", self.bpm_label(song), song.play_count, song.filename)

        return (
            song.title,
            song.artist or "Unknown Artist",
            song.album or "Singles / Unassigned",
            self.bpm_label(song),
            song.play_count,
        )

    def bpm_label(self, song):
        if song.id in self.bpm_analysis_song_ids:
            return "Analyzing..."

        return str(song.bpm) if song.bpm else ""

    def update_song_tree_rows(self, song):
        for tree in (self.library_tree, self.album_song_tree, self.playlist_tree):
            if tree.exists(song.id):
                tree.item(song.id, values=self.song_tree_values(tree, song))

    def get_selected_library_song_ids(self):
        selected_ids = set(self.library_tree.selection())
        if not selected_ids:
            return []

        ordered_ids = []
        for item_id in self.library_tree.get_children():
            if item_id in selected_ids:
                ordered_ids.append(item_id)

        return ordered_ids

    def get_primary_library_song_id(self):
        selection = self.get_selected_library_song_ids()
        if not selection:
            return None

        focused_id = self.library_tree.focus()
        if focused_id in selection:
            return focused_id

        return selection[0]

    def get_selected_library_songs(self):
        return self.songs_from_ids(self.get_selected_library_song_ids())

    def get_selected_album_key(self):
        selection = self.album_tree.selection()
        if not selection:
            return None
        return self.album_key_by_item.get(selection[0])

    def get_selected_album_summary(self):
        album_key = self.get_selected_album_key()
        if album_key is None:
            return None
        return self.album_summary_by_key.get(album_key)

    def get_selected_album_song_ids(self):
        selected_ids = set(self.album_song_tree.selection())
        if not selected_ids:
            return []

        ordered_ids = []
        for item_id in self.album_song_tree.get_children():
            if item_id in selected_ids:
                ordered_ids.append(item_id)

        return ordered_ids

    def get_primary_album_song_id(self):
        selection = self.get_selected_album_song_ids()
        if not selection:
            return None

        focused_id = self.album_song_tree.focus()
        if focused_id in selection:
            return focused_id

        return selection[0]

    def get_selected_album_songs(self):
        return self.songs_from_ids(self.get_selected_album_song_ids())

    def get_selected_playlist_name(self):
        selection = self.playlist_list.curselection()
        if not selection:
            return None
        index = selection[0]
        if index >= len(self.playlist_names):
            return None
        return self.playlist_names[index]

    def get_selected_playlist_song_id(self):
        selection = self.playlist_tree.selection()
        return selection[0] if selection else None

    def refresh_library_tree(self):
        selected_song_ids = self.get_selected_library_song_ids()
        focused_song_id = self.library_tree.focus()
        all_songs = self.library.sorted_songs()
        query = self.normalized_query(self.song_search_var.get())
        visible_songs = [song for song in all_songs if self.song_matches_query(song, query)]
        self.visible_library_song_ids = [song.id for song in visible_songs]

        for item in self.library_tree.get_children():
            self.library_tree.delete(item)

        for song in visible_songs:
            self.library_tree.insert(
                "",
                tk.END,
                iid=song.id,
                values=self.song_tree_values(self.library_tree, song),
            )

        existing_selection = [song_id for song_id in selected_song_ids if self.library_tree.exists(song_id)]
        if existing_selection:
            self.library_tree.selection_set(existing_selection)

        if focused_song_id and self.library_tree.exists(focused_song_id):
            self.library_tree.focus(focused_song_id)
        elif existing_selection:
            self.library_tree.focus(existing_selection[0])

        if query:
            self.songs_summary_var.set(f"Showing {len(visible_songs)} of {len(all_songs)} songs")
        else:
            self.songs_summary_var.set(f"{len(all_songs)} songs")

    def refresh_album_tree(self):
        previous_key = self.get_selected_album_key()
        self.album_key_by_item = {}
        self.album_summary_by_key = {}
        all_summaries = self.library.album_groups()
        query = self.normalized_query(self.album_search_var.get())
        visible_summaries = [summary for summary in all_summaries if self.album_matches_query(summary, query)]

        for item in self.album_tree.get_children():
            self.album_tree.delete(item)

        for index, summary in enumerate(visible_summaries):
            item_id = f"album-{index}"
            self.album_key_by_item[item_id] = summary.key
            self.album_summary_by_key[summary.key] = summary
            self.album_tree.insert(
                "",
                tk.END,
                iid=item_id,
                values=(summary.title, summary.artist_label, summary.song_count),
            )

        self.album_list_frame.configure(text=f"Albums ({len(visible_summaries)}/{len(all_summaries)})")

        selected_item = None
        for item_id, album_key in self.album_key_by_item.items():
            if album_key == previous_key:
                selected_item = item_id
                break

        if selected_item is None and self.album_key_by_item:
            selected_item = next(iter(self.album_key_by_item))

        if selected_item is not None:
            self.album_tree.selection_set(selected_item)
            self.album_tree.focus(selected_item)

        self.refresh_album_song_tree()

    def select_album_key(self, album_key):
        for item_id, key in self.album_key_by_item.items():
            if key != album_key:
                continue

            self.album_tree.selection_set(item_id)
            self.album_tree.focus(item_id)
            self.refresh_album_song_tree()
            return

    def refresh_album_song_tree(self):
        selected_song_ids = self.get_selected_album_song_ids()
        focused_song_id = self.album_song_tree.focus()
        self.visible_album_song_ids = []

        for item in self.album_song_tree.get_children():
            self.album_song_tree.delete(item)

        album_key = self.get_selected_album_key()
        if album_key is None:
            self.album_song_frame.configure(text="Album Songs")
            return

        summary = self.album_summary_by_key.get(album_key)
        all_songs = self.library.album_songs(album_key)
        query = self.normalized_query(self.album_song_search_var.get())
        visible_songs = [song for song in all_songs if self.song_matches_query(song, query)]
        self.visible_album_song_ids = [song.id for song in visible_songs]

        title = f"Album Songs: {summary.title}" if summary else "Album Songs"
        if query:
            title = f"{title} ({len(visible_songs)}/{len(all_songs)})"
        elif all_songs:
            title = f"{title} ({len(all_songs)})"
        self.album_song_frame.configure(text=title)

        for song in visible_songs:
            self.album_song_tree.insert(
                "",
                tk.END,
                iid=song.id,
                values=self.song_tree_values(self.album_song_tree, song),
            )

        existing_selection = [song_id for song_id in selected_song_ids if self.album_song_tree.exists(song_id)]
        if existing_selection:
            self.album_song_tree.selection_set(existing_selection)

        if focused_song_id and self.album_song_tree.exists(focused_song_id):
            self.album_song_tree.focus(focused_song_id)
        elif existing_selection:
            self.album_song_tree.focus(existing_selection[0])

    def refresh_playlist_list(self):
        selected_playlist = self.get_selected_playlist_name()
        self.all_playlist_names = sorted(self.library.playlists, key=str.casefold)
        query = self.normalized_query(self.playlist_search_var.get())
        self.playlist_names = [name for name in self.all_playlist_names if query in name.casefold()]

        self.playlist_list.delete(0, tk.END)
        for name in self.playlist_names:
            self.playlist_list.insert(tk.END, name)

        self.playlist_list_frame.configure(text=f"Playlists ({len(self.playlist_names)}/{len(self.all_playlist_names)})")

        if not self.playlist_names:
            self.playlist_list.selection_clear(0, tk.END)
            self.refresh_playlist_tree()
            return

        if selected_playlist not in self.playlist_names:
            selected_playlist = self.playlist_names[0]

        index = self.playlist_names.index(selected_playlist)
        self.playlist_list.selection_clear(0, tk.END)
        self.playlist_list.selection_set(index)
        self.playlist_list.activate(index)
        self.playlist_list.see(index)

    def refresh_playlist_tree(self):
        selected_song_id = self.get_selected_playlist_song_id()
        self.visible_playlist_song_ids = []

        for item in self.playlist_tree.get_children():
            self.playlist_tree.delete(item)

        playlist_name = self.get_selected_playlist_name()
        if not playlist_name:
            self.playlist_song_frame.configure(text="Playlist Songs")
            return

        all_songs = self.library.playlist_songs(playlist_name)
        query = self.normalized_query(self.playlist_song_search_var.get())
        visible_songs = [song for song in all_songs if self.song_matches_query(song, query)]
        self.visible_playlist_song_ids = [song.id for song in visible_songs]

        title = f"Playlist Songs: {playlist_name}"
        if query:
            title = f"{title} ({len(visible_songs)}/{len(all_songs)})"
        elif all_songs:
            title = f"{title} ({len(all_songs)})"
        self.playlist_song_frame.configure(text=title)
        for song in visible_songs:
            self.playlist_tree.insert(
                "",
                tk.END,
                iid=song.id,
                values=self.song_tree_values(self.playlist_tree, song),
            )

        if selected_song_id and self.playlist_tree.exists(selected_song_id):
            self.playlist_tree.selection_set(selected_song_id)
            self.playlist_tree.focus(selected_song_id)

    def add_songs(self):
        selected_paths = filedialog.askopenfilenames(
            title="Import Songs",
            filetypes=[
                ("Audio files", "*.mp3 *.wav *.flac"),
                ("MP3 files", "*.mp3"),
                ("WAV files", "*.wav"),
                ("FLAC files", "*.flac"),
            ],
        )
        if not selected_paths:
            return

        imported_count = self.library.import_files(selected_paths)
        self.refresh_library_tree()
        self.refresh_album_tree()

        if imported_count:
            self.status_label.config(text=f"Imported {imported_count} song(s)")

    def import_album(self):
        album_folder = filedialog.askdirectory(title="Choose album folder", mustexist=True)
        if not album_folder:
            return

        default_album_name = Path(album_folder).name.strip() or "Imported Album"
        album_name = simpledialog.askstring("Import Album", "Album name:", initialvalue=default_album_name)
        if album_name is None:
            return

        album_name = album_name.strip()
        if not album_name:
            messagebox.showerror("Invalid album", "Album name cannot be empty.")
            return

        artist_name = simpledialog.askstring(
            "Import Album",
            "Artist name for the whole album:\n\nLeave blank to keep artists editable per track.",
            initialvalue="",
        )
        if artist_name is None:
            return

        try:
            imported_songs = self.library.import_album(album_folder, album_name, artist_name)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import failed", str(exc))
            return

        self.refresh_all_views()
        self.notebook.select(self.albums_tab)
        self.select_album_key(album_name)

        if artist_name.strip():
            self.status_label.config(text=f"Imported album {album_name} by {artist_name.strip()}")
        else:
            self.status_label.config(text=f"Imported album {album_name} ({len(imported_songs)} songs)")

    def remove_song(self, song_ids=None):
        songs = self.songs_from_ids(song_ids or self.get_selected_library_song_ids())
        if not songs:
            messagebox.showinfo("Select songs", "Choose one or more songs first.")
            return

        prompt = (
            f"Remove '{songs[0].title}' from the library and delete the file from disk?"
            if len(songs) == 1
            else f"Remove {len(songs)} songs from the library and delete their files from disk?"
        )
        if not messagebox.askyesno("Remove Song", prompt):
            return

        removed_ids = {song.id for song in songs}
        if self.current_song_id in removed_ids:
            self.stop_playback()

        removed_songs, failures = self.library.remove_songs(removed_ids)
        if not removed_songs:
            messagebox.showerror("Delete failed", "\n".join(failures) if failures else "No songs were removed.")
            return

        self.current_queue = [song_id for song_id in self.current_queue if song_id not in removed_ids]
        if self.current_queue_index is not None and self.current_queue_index >= len(self.current_queue):
            self.current_queue_index = len(self.current_queue) - 1 if self.current_queue else None

        self.refresh_all_views()

        if failures:
            messagebox.showwarning("Some songs were not removed", "\n".join(failures))

        if len(removed_songs) == 1:
            self.status_label.config(text=f"Removed {removed_songs[0].title}")
        else:
            self.status_label.config(text=f"Removed {len(removed_songs)} songs")

    def analyze_bpm_for_song_ids(self, song_ids):
        songs = self.songs_from_ids(song_ids)
        if not songs:
            messagebox.showinfo("Select songs", "Choose one or more songs first.")
            return

        pending_songs = [song for song in songs if song.id not in self.bpm_analysis_song_ids]
        if not pending_songs:
            self.status_label.config(text="BPM analysis is already running for the selected song(s).")
            return

        for song in pending_songs:
            self.bpm_analysis_song_ids.add(song.id)
            self.update_song_tree_rows(song)

        if len(pending_songs) == 1:
            self.status_label.config(text=f"Analyzing BPM: {describe_song(pending_songs[0])}")
        else:
            self.status_label.config(text=f"Analyzing BPM for {len(pending_songs)} songs")

        analysis_items = [(song.id, song.title, self.library.song_path(song)) for song in pending_songs]

        def worker():
            results = []
            failures = []
            for song_id, title, path in analysis_items:
                if not path.exists():
                    failures.append(f"{title}: missing file")
                    continue

                bpm = analyze_bpm(path)
                if bpm is None:
                    failures.append(f"{title}: no clear tempo")
                else:
                    results.append((song_id, bpm))

            try:
                self.root.after(0, lambda: self.apply_bpm_results(analysis_items, results, failures))
            except RuntimeError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def apply_bpm_results(self, analysis_items, results, failures):
        for song_id, _title, _path in analysis_items:
            self.bpm_analysis_song_ids.discard(song_id)

        updated_songs = []
        for song_id, bpm in results:
            song = self.library.update_bpm(song_id, bpm)
            if song:
                updated_songs.append(song)

        for song_id, _title, _path in analysis_items:
            song = self.library.get_song(song_id)
            if song:
                self.update_song_tree_rows(song)

        if updated_songs:
            if len(updated_songs) == 1:
                self.status_label.config(text=f"BPM: {describe_song(updated_songs[0])} is {updated_songs[0].bpm}")
            else:
                self.status_label.config(text=f"Analyzed BPM for {len(updated_songs)} songs")
        elif failures:
            self.status_label.config(text="BPM analysis could not find a clear tempo.")
        else:
            self.status_label.config(text="BPM analysis finished.")

        if failures:
            messagebox.showwarning("BPM analysis", "\n".join(failures[:12]))

    def set_bpm_for_song_ids(self, song_ids):
        songs = self.songs_from_ids(song_ids)
        if not songs:
            messagebox.showinfo("Select songs", "Choose one or more songs first.")
            return

        initial_value = songs[0].bpm or 120
        bpm = simpledialog.askinteger(
            "Set BPM",
            "BPM:",
            initialvalue=initial_value,
            minvalue=1,
            maxvalue=300,
        )
        if bpm is None:
            return

        self.apply_bpm_to_songs(songs, bpm, "Set BPM")

    def apply_bpm_to_songs(self, songs, bpm, action_label):
        updated_songs = []
        for song in songs:
            updated_song = self.library.update_bpm(song.id, bpm)
            if updated_song:
                updated_songs.append(updated_song)
                self.update_song_tree_rows(updated_song)

        if len(updated_songs) == 1:
            self.status_label.config(text=f"{action_label}: {describe_song(updated_songs[0])} is {bpm}")
        else:
            self.status_label.config(text=f"{action_label} to {bpm} for {len(updated_songs)} songs")

    def open_tap_bpm_for_song_ids(self, song_ids):
        songs = self.songs_from_ids(song_ids)
        if not songs:
            messagebox.showinfo("Select songs", "Choose one or more songs first.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Tap BPM")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(background=self.card_bg)
        dialog.columnconfigure(0, weight=1)

        tap_times = []
        bpm_var = tk.StringVar(value="--")
        tap_count_var = tk.StringVar(value="0 taps")
        hint_var = tk.StringVar(value="Click the pad with the beat.")

        target_label = describe_song(songs[0]) if len(songs) == 1 else f"{len(songs)} selected songs"
        ttk.Label(dialog, text=target_label, style="CardHint.TLabel", anchor="center").grid(
            row=0,
            column=0,
            sticky="ew",
            padx=18,
            pady=(16, 6),
        )
        ttk.Label(dialog, textvariable=bpm_var, background=self.card_bg, foreground=self.text_color, font=("Helvetica Neue", 34, "bold")).grid(
            row=1,
            column=0,
            sticky="ew",
            padx=18,
        )
        ttk.Label(dialog, text="BPM", style="CardHint.TLabel", anchor="center").grid(row=2, column=0, sticky="ew", padx=18)

        tap_button = tk.Button(
            dialog,
            text="TAP",
            command=lambda: register_tap(),
            bg=self.accent,
            fg="#ffffff",
            activebackground=self.accent_dark,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            padx=36,
            pady=20,
            font=("Helvetica Neue", 22, "bold"),
            cursor="hand2",
        )
        tap_button.grid(row=3, column=0, sticky="nsew", padx=18, pady=(14, 10))
        tap_button.configure(width=10, height=4)

        ttk.Label(dialog, textvariable=tap_count_var, style="CardHint.TLabel", anchor="center").grid(row=4, column=0, sticky="ew", padx=18)
        ttk.Label(dialog, textvariable=hint_var, style="CardHint.TLabel", anchor="center").grid(row=5, column=0, sticky="ew", padx=18, pady=(2, 12))

        buttons = ttk.Frame(dialog, style="Card.TFrame")
        buttons.grid(row=6, column=0, sticky="ew", padx=18, pady=(0, 16))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        buttons.columnconfigure(2, weight=1)

        def current_bpm():
            try:
                return int(round(float(bpm_var.get())))
            except ValueError:
                return None

        def update_bpm():
            if len(tap_times) < 2:
                bpm_var.set("--")
                tap_count_var.set(f"{len(tap_times)} tap" if len(tap_times) == 1 else "0 taps")
                return

            intervals = [later - earlier for earlier, later in zip(tap_times, tap_times[1:]) if 0.18 <= later - earlier <= 2.4]
            if not intervals:
                bpm_var.set("--")
                tap_count_var.set(f"{len(tap_times)} taps")
                return

            recent_intervals = intervals[-12:]
            median_interval = sorted(recent_intervals)[len(recent_intervals) // 2]
            filtered = [interval for interval in recent_intervals if abs(interval - median_interval) <= median_interval * 0.22]
            bpm = 60.0 / (sum(filtered) / len(filtered or recent_intervals))
            bpm_var.set(str(int(round(max(1, min(300, bpm))))))
            tap_count_var.set(f"{len(tap_times)} taps")

        def register_tap():
            now = time.monotonic()
            if tap_times and now - tap_times[-1] > 3.0:
                tap_times.clear()

            tap_times.append(now)
            if len(tap_times) > 16:
                del tap_times[:-16]
            update_bpm()

        def reset_taps():
            tap_times.clear()
            bpm_var.set("--")
            tap_count_var.set("0 taps")
            hint_var.set("Click the pad with the beat.")

        def apply_tapped_bpm():
            bpm = current_bpm()
            if bpm is None:
                hint_var.set("Tap at least twice to calculate BPM.")
                return

            self.apply_bpm_to_songs(songs, bpm, "Tapped BPM")
            dialog.destroy()

        ttk.Button(buttons, text="Reset", command=reset_taps, style="Action.TButton").grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy, style="Action.TButton").grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(buttons, text="Apply", command=apply_tapped_bpm, style="Action.TButton").grid(row=0, column=2, sticky="ew", padx=(6, 0))

        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.update_idletasks()

        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - dialog.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - dialog.winfo_height()) // 3)
        dialog.geometry(f"+{x}+{y}")
        dialog.focus_set()

    def rename_song(self, song_ids=None):
        songs = self.songs_from_ids(song_ids or self.get_selected_library_song_ids())
        if not songs:
            messagebox.showinfo("Select songs", "Choose one or more songs first.")
            return

        selected_ids = [song.id for song in songs]
        if self.current_song_id in set(selected_ids):
            self.stop_playback()

        if len(songs) == 1:
            new_title = simpledialog.askstring("Rename Song", "New song title:", initialvalue=songs[0].title)
            if new_title is None:
                return

            try:
                renamed_song = self.library.rename_song(songs[0].id, new_title)
            except (OSError, FileNotFoundError, ValueError) as exc:
                messagebox.showerror("Rename failed", str(exc))
                return

            self.refresh_all_views()
            self.status_label.config(text=f"Renamed song to {renamed_song.title}")
            return

        base_title = simpledialog.askstring(
            "Batch Rename",
            f"Base title for {len(songs)} songs:\n\nSongs will be renamed as 'Base Title 01', 'Base Title 02', and so on.",
        )
        if base_title is None:
            return

        renamed_songs, failures = self.library.batch_rename(selected_ids, sanitize_name(base_title))
        if not renamed_songs:
            messagebox.showerror("Rename failed", "\n".join(failures) if failures else "No songs were renamed.")
            return

        self.refresh_all_views()
        if failures:
            messagebox.showwarning("Some songs were not renamed", "\n".join(failures))
        self.status_label.config(text=f"Renamed {len(renamed_songs)} songs")

    def edit_artist(self, song_ids=None):
        songs = self.songs_from_ids(song_ids or self.get_selected_library_song_ids())
        if not songs:
            messagebox.showinfo("Select songs", "Choose one or more songs first.")
            return

        existing_artists = {song.artist for song in songs}
        initial_artist = existing_artists.pop() if len(existing_artists) == 1 else ""
        prompt = "Artist name:" if len(songs) == 1 else f"Artist name for {len(songs)} selected songs:"
        artist = simpledialog.askstring("Artist Info", prompt, initialvalue=initial_artist)
        if artist is None:
            return

        updated_songs = self.library.update_artist([song.id for song in songs], artist)
        self.refresh_all_views()

        if len(updated_songs) == 1:
            self.status_label.config(text=f"Updated artist for {updated_songs[0].title}")
        else:
            self.status_label.config(text=f"Updated artist for {len(updated_songs)} songs")

    def edit_album(self, song_ids=None):
        songs = self.songs_from_ids(song_ids or self.get_selected_library_song_ids())
        if not songs:
            messagebox.showinfo("Select songs", "Choose one or more songs first.")
            return

        existing_albums = {song.album for song in songs}
        initial_album = existing_albums.pop() if len(existing_albums) == 1 else ""
        prompt = "Album name:" if len(songs) == 1 else f"Album name for {len(songs)} selected songs:"
        album = simpledialog.askstring("Album Info", prompt, initialvalue=initial_album)
        if album is None:
            return

        updated_songs = self.library.update_album([song.id for song in songs], album)
        self.refresh_all_views()

        clean_album = album.strip()
        if len(updated_songs) == 1:
            if clean_album:
                self.status_label.config(text=f"Set album for {updated_songs[0].title} to {clean_album}")
            else:
                self.status_label.config(text=f"Cleared album for {updated_songs[0].title}")
        else:
            if clean_album:
                self.status_label.config(text=f"Set album for {len(updated_songs)} songs to {clean_album}")
            else:
                self.status_label.config(text=f"Cleared album for {len(updated_songs)} songs")

    def prompt_for_playlist_name(self):
        if not self.library.playlists:
            create_now = messagebox.askyesno("No Playlists", "No playlists exist yet. Create one now?")
            if not create_now:
                return None

            new_name = self.create_playlist()
            if not new_name:
                return None

        available_names = self.all_playlist_names or sorted(self.library.playlists, key=str.casefold)
        choices = "\n".join(available_names)
        initial_value = self.get_selected_playlist_name() or available_names[0]
        response = simpledialog.askstring(
            "Choose Playlist",
            "Playlist name:\n\n" + choices,
            initialvalue=initial_value,
        )
        if response is None:
            return None

        normalized = response.strip().casefold()
        playlist_map = {name.casefold(): name for name in available_names}
        playlist_name = playlist_map.get(normalized)
        if playlist_name is None:
            messagebox.showerror("Playlist not found", "Choose an existing playlist by name.")
            return None

        return playlist_name

    def add_song_ids_to_playlist_named(self, playlist_name, song_ids):
        try:
            added_count = self.library.add_songs_to_playlist(playlist_name, song_ids)
        except KeyError:
            messagebox.showerror("Playlist not found", f"The playlist '{playlist_name}' no longer exists.")
            self.refresh_all_views()
            return 0

        self.refresh_playlist_list()
        self.select_playlist_by_name(playlist_name)
        self.refresh_playlist_tree()
        return added_count

    def add_song_ids_to_selected_playlist(self, song_ids):
        if not song_ids:
            messagebox.showinfo("Select songs", "Choose one or more songs first.")
            return

        playlist_name = self.get_selected_playlist_name()
        if not playlist_name:
            self.add_song_ids_to_playlist(song_ids)
            return

        added_count = self.add_song_ids_to_playlist_named(playlist_name, song_ids)
        if not added_count:
            messagebox.showinfo("Already added", "The selected songs are already in the playlist.")
            return

        if added_count == 1:
            song = self.library.get_song(song_ids[0])
            title = song.title if song else "song"
            self.status_label.config(text=f"Added {title} to {playlist_name}")
        else:
            self.status_label.config(text=f"Added {added_count} songs to {playlist_name}")

    def add_song_ids_to_playlist(self, song_ids):
        if not song_ids:
            messagebox.showinfo("Select songs", "Choose one or more songs first.")
            return

        playlist_name = self.prompt_for_playlist_name()
        if not playlist_name:
            return

        added_count = self.add_song_ids_to_playlist_named(playlist_name, song_ids)

        if not added_count:
            messagebox.showinfo("Already added", "The selected songs are already in the playlist.")
            return

        if added_count == 1:
            song = self.library.get_song(song_ids[0])
            title = song.title if song else "song"
            self.status_label.config(text=f"Added {title} to {playlist_name}")
        else:
            self.status_label.config(text=f"Added {added_count} songs to {playlist_name}")

    def add_selected_songs_to_playlist(self):
        self.add_song_ids_to_playlist(self.get_selected_library_song_ids())

    def add_selected_album_songs_to_playlist(self):
        song_ids = self.get_selected_album_song_ids() or self.visible_album_song_ids
        if not song_ids:
            song_ids = self.library.album_queue(self.get_selected_album_key() or "")
        self.add_song_ids_to_playlist(song_ids)

    def create_playlist(self):
        name = simpledialog.askstring("New Playlist", "Playlist name:")
        if name is None:
            return None

        try:
            playlist_name = self.library.create_playlist(name)
        except ValueError as exc:
            messagebox.showerror("Invalid playlist", str(exc))
            return None

        self.refresh_playlist_list()
        self.select_playlist_by_name(playlist_name)
        self.refresh_playlist_tree()
        self.status_label.config(text=f"Created playlist: {playlist_name}")
        return playlist_name

    def rename_playlist(self):
        playlist_name = self.get_selected_playlist_name()
        if not playlist_name:
            messagebox.showinfo("Select a playlist", "Choose a playlist from the playlist sidebar first.")
            return

        new_name = simpledialog.askstring("Rename Playlist", "New playlist name:", initialvalue=playlist_name)
        if new_name is None:
            return

        try:
            renamed_playlist = self.library.rename_playlist(playlist_name, new_name)
        except ValueError as exc:
            messagebox.showerror("Invalid playlist", str(exc))
            return
        except KeyError:
            messagebox.showerror("Playlist not found", "That playlist no longer exists.")
            self.refresh_all_views()
            return

        if self.current_queue_source == playlist_name:
            self.current_queue_source = renamed_playlist

        self.refresh_playlist_list()
        self.select_playlist_by_name(renamed_playlist)
        self.refresh_playlist_tree()
        self.status_label.config(text=f"Renamed playlist to {renamed_playlist}")

    def delete_playlist(self):
        playlist_name = self.get_selected_playlist_name()
        if not playlist_name:
            messagebox.showinfo("Select a playlist", "Choose a playlist from the playlist sidebar first.")
            return

        if not messagebox.askyesno("Delete Playlist", f"Delete playlist '{playlist_name}'?"):
            return

        if self.current_queue_source == playlist_name:
            self.stop_playback()
            self.current_queue = []
            self.current_queue_index = None
            self.current_queue_source = "Library"

        self.library.delete_playlist(playlist_name)
        self.refresh_playlist_list()
        self.refresh_playlist_tree()
        self.status_label.config(text=f"Deleted playlist: {playlist_name}")

    def export_playlist(self):
        playlist_name = self.get_selected_playlist_name()
        if not playlist_name:
            messagebox.showinfo("Select a playlist", "Choose a playlist from the playlist sidebar first.")
            return

        destination = filedialog.askdirectory(title="Choose export destination", mustexist=True)
        if not destination:
            return

        try:
            export_root, playlist_file, missing_titles, copied_count = self.library.export_playlist(playlist_name, destination)
        except (OSError, FileNotFoundError, ValueError) as exc:
            messagebox.showerror("Export failed", str(exc))
            return

        summary_lines = [
            f"Exported {copied_count} song(s) to:",
            str(export_root),
            "",
            f"Playlist file: {playlist_file.name}",
        ]
        if missing_titles:
            summary_lines.extend(["", "Missing source files:", *missing_titles])

        self.status_label.config(text=f"Exported playlist '{playlist_name}'")
        messagebox.showinfo("Playlist Exported", "\n".join(summary_lines))

    def show_library_context_menu(self, event):
        item_id = self.select_tree_item_for_event(self.library_tree, event)
        menu = self.create_menu(self.root)

        if item_id is None:
            menu.add_command(label="Import Songs", command=self.add_songs)
            menu.add_command(label="Import Album", command=self.import_album)
        else:
            selected_ids = self.get_selected_library_song_ids()
            menu.add_command(label="Play", command=self.play_selected_library_song)
            menu.add_command(label="Analyze BPM", command=lambda: self.analyze_bpm_for_song_ids(selected_ids))
            menu.add_command(label="Tap BPM...", command=lambda: self.open_tap_bpm_for_song_ids(selected_ids))
            menu.add_command(label="Set BPM...", command=lambda: self.set_bpm_for_song_ids(selected_ids))
            menu.add_separator()
            menu.add_command(
                label="Add to Selected Playlist",
                command=lambda: self.add_song_ids_to_selected_playlist(selected_ids),
            )
            menu.add_command(label="Add to Playlist...", command=self.add_selected_songs_to_playlist)
            menu.add_separator()
            menu.add_command(label="Rename Song(s)", command=self.rename_song)
            menu.add_command(label="Edit Artist", command=self.edit_artist)
            menu.add_command(label="Set Album", command=self.edit_album)
            menu.add_separator()
            menu.add_command(label="Remove Song(s)", command=self.remove_song)

        self.popup_menu(menu, event)

    def show_album_context_menu(self, event):
        item_id = self.select_tree_item_for_event(self.album_tree, event, browse=True)
        menu = self.create_menu(self.root)

        if item_id is None:
            menu.add_command(label="Import Album", command=self.import_album)
        else:
            song_ids = self.library.album_queue(self.get_selected_album_key() or "")
            menu.add_command(label="Play Album", command=self.play_album)
            menu.add_separator()
            menu.add_command(
                label="Add Album to Selected Playlist",
                command=lambda: self.add_song_ids_to_selected_playlist(song_ids),
            )
            menu.add_command(label="Add Album to Playlist...", command=lambda: self.add_song_ids_to_playlist(song_ids))

        self.popup_menu(menu, event)

    def show_album_song_context_menu(self, event):
        item_id = self.select_tree_item_for_event(self.album_song_tree, event)
        if item_id is None:
            return

        selected_ids = self.get_selected_album_song_ids()
        menu = self.create_menu(self.root)
        menu.add_command(label="Play", command=self.play_selected_album_song)
        menu.add_command(label="Analyze BPM", command=lambda: self.analyze_bpm_for_song_ids(selected_ids))
        menu.add_command(label="Tap BPM...", command=lambda: self.open_tap_bpm_for_song_ids(selected_ids))
        menu.add_command(label="Set BPM...", command=lambda: self.set_bpm_for_song_ids(selected_ids))
        menu.add_separator()
        menu.add_command(
            label="Add to Selected Playlist",
            command=lambda: self.add_song_ids_to_selected_playlist(selected_ids),
        )
        menu.add_command(label="Add to Playlist...", command=self.add_selected_album_songs_to_playlist)
        menu.add_separator()
        menu.add_command(label="Rename Song(s)", command=lambda: self.rename_song(selected_ids))
        menu.add_command(label="Edit Artist", command=lambda: self.edit_artist(selected_ids))
        menu.add_command(label="Set Album", command=lambda: self.edit_album(selected_ids))
        menu.add_separator()
        menu.add_command(label="Remove Song(s)", command=lambda: self.remove_song(selected_ids))
        self.popup_menu(menu, event)

    def show_playlist_list_context_menu(self, event):
        playlist_name = self.select_playlist_at_event(event)
        menu = self.create_menu(self.root)
        menu.add_command(label="New Playlist", command=self.create_playlist)

        if playlist_name is not None:
            menu.add_command(label="Rename Playlist", command=self.rename_playlist)
            menu.add_command(label="Delete Playlist", command=self.delete_playlist)
            menu.add_separator()
            menu.add_command(label="Export Playlist", command=self.export_playlist)

        self.popup_menu(menu, event)

    def show_playlist_song_context_menu(self, event):
        item_id = self.select_tree_item_for_event(self.playlist_tree, event, browse=True)
        if item_id is None:
            return

        menu = self.create_menu(self.root)
        menu.add_command(label="Play", command=self.play_selected_playlist_song)
        menu.add_command(label="Analyze BPM", command=lambda: self.analyze_bpm_for_song_ids([item_id]))
        menu.add_command(label="Tap BPM...", command=lambda: self.open_tap_bpm_for_song_ids([item_id]))
        menu.add_command(label="Set BPM...", command=lambda: self.set_bpm_for_song_ids([item_id]))
        menu.add_separator()
        menu.add_command(label="Remove From Playlist", command=self.remove_song_from_playlist)
        self.popup_menu(menu, event)

    def build_drag_payload(self, widget):
        if widget is self.library_tree:
            song_ids = self.get_selected_library_song_ids()
            if not song_ids:
                return None
            label = f"{len(song_ids)} song" if len(song_ids) == 1 else f"{len(song_ids)} songs"
            return {"song_ids": song_ids, "label": label}

        if widget is self.album_song_tree:
            song_ids = self.get_selected_album_song_ids() or self.visible_album_song_ids
            if not song_ids:
                return None
            label = f"{len(song_ids)} track" if len(song_ids) == 1 else f"{len(song_ids)} tracks"
            return {"song_ids": song_ids, "label": label}

        if widget is self.album_tree:
            album_key = self.get_selected_album_key()
            if album_key is None:
                return None

            song_ids = self.library.album_queue(album_key)
            if not song_ids:
                return None

            summary = self.get_selected_album_summary()
            album_title = summary.title if summary else "album"
            label = f"album '{album_title}'"
            return {"song_ids": song_ids, "label": label}

        return None

    def on_drag_press(self, event):
        widget = event.widget
        if widget is self.album_tree:
            item_id = self.select_tree_item_for_event(widget, event, browse=True)
        else:
            item_id = self.select_tree_item_for_event(widget, event)

        if item_id is None:
            self.drag_origin = None
            self.drag_payload = None
            return

        self.drag_origin = {
            "widget": widget,
            "x_root": event.x_root,
            "y_root": event.y_root,
        }
        self.drag_payload = None
        self.drag_target_playlist = None
        self.status_before_drag = self.status_label.cget("text")
        self.playlist_before_drag = self.get_selected_playlist_name()

    def on_drag_motion(self, event):
        if self.drag_origin is None:
            return

        if self.drag_payload is None:
            moved_x = abs(event.x_root - self.drag_origin["x_root"])
            moved_y = abs(event.y_root - self.drag_origin["y_root"])
            if max(moved_x, moved_y) < 8:
                return

            self.drag_payload = self.build_drag_payload(self.drag_origin["widget"])
            if self.drag_payload is None:
                self.drag_origin = None
                return

        playlist_name = self.playlist_name_at_pointer()
        if playlist_name == self.drag_target_playlist:
            return

        self.drag_target_playlist = playlist_name
        if playlist_name is None:
            self.status_label.config(text=f"Dragging {self.drag_payload['label']} to a playlist")
            return

        self.select_playlist_by_name(playlist_name)
        self.refresh_playlist_tree()
        self.status_label.config(text=f"Drop on '{playlist_name}' to add {self.drag_payload['label']}")

    def on_drag_release(self, _event):
        if self.drag_origin is None:
            return

        payload = self.drag_payload
        target_playlist = self.playlist_name_at_pointer() if payload else None

        self.drag_origin = None
        self.drag_payload = None
        self.drag_target_playlist = None

        if payload is None:
            return

        if target_playlist is None:
            if self.playlist_before_drag:
                self.select_playlist_by_name(self.playlist_before_drag)
                self.refresh_playlist_tree()
            self.status_label.config(text=self.status_before_drag)
            return

        added_count = self.add_song_ids_to_playlist_named(target_playlist, payload["song_ids"])
        if not added_count:
            self.status_label.config(text=f"{payload['label'].capitalize()} already in {target_playlist}")
            return

        if added_count == 1 and len(payload["song_ids"]) == 1:
            song = self.library.get_song(payload["song_ids"][0])
            title = song.title if song else "song"
            self.status_label.config(text=f"Added {title} to {target_playlist}")
        else:
            self.status_label.config(text=f"Added {added_count} songs to {target_playlist}")

    def remove_song_from_playlist(self):
        playlist_name = self.get_selected_playlist_name()
        song_id = self.get_selected_playlist_song_id()
        if not playlist_name or not song_id:
            messagebox.showinfo("Select a song", "Choose a song from the playlist first.")
            return

        song = self.library.remove_song_from_playlist(playlist_name, song_id)
        if self.current_queue_source == playlist_name:
            self.current_queue = [item for item in self.current_queue if item != song_id]
            if self.current_queue_index is not None and self.current_queue_index >= len(self.current_queue):
                self.current_queue_index = len(self.current_queue) - 1 if self.current_queue else None

        self.refresh_playlist_tree()
        if song:
            self.status_label.config(text=f"Removed {song.title} from {playlist_name}")

    def start_playback(self, queue, song_id, source_name):
        song = self.library.get_song(song_id)
        if song is None:
            messagebox.showerror("Missing song", "That song is no longer in the library.")
            return

        path = self.library.song_path(song)
        if not path.exists():
            messagebox.showerror("Missing file", f"Could not find {path.name}.")
            self.library.reload_state()
            self.refresh_all_views()
            return

        valid_queue = [candidate for candidate in queue if self.library.get_song(candidate)]
        if song_id not in valid_queue:
            valid_queue = [song_id]

        try:
            self.player.play(path)
        except RuntimeError as exc:
            messagebox.showerror("Playback failed", str(exc))
            return

        self.current_queue = valid_queue
        self.current_queue_index = valid_queue.index(song_id)
        self.current_queue_source = source_name
        self.current_song_id = song_id
        self.load_analyzer_for_song(song_id, path)
        song = self.library.increment_play_count(song_id) or song
        self.update_song_tree_rows(song)
        self.status_label.config(text=f"Now playing: {describe_song(song)}")
        self.update_progress_ui()

        self.syncing_playback_selection = True
        try:
            if self.library_tree.exists(song_id):
                self.library_tree.selection_set(song_id)
                self.library_tree.focus(song_id)
            if self.album_song_tree.exists(song_id):
                self.album_song_tree.selection_set(song_id)
                self.album_song_tree.focus(song_id)
            if self.playlist_tree.exists(song_id):
                self.playlist_tree.selection_set(song_id)
                self.playlist_tree.focus(song_id)
        finally:
            self.syncing_playback_selection = False

    def play_selected_library_song(self):
        song_id = self.get_primary_library_song_id()
        if not song_id:
            messagebox.showinfo("Select a song", "Choose a song from the Songs view first.")
            return

        queue = self.visible_library_song_ids or [song.id for song in self.library.sorted_songs()]
        self.start_playback(queue, song_id, "Library")

    def play_album(self):
        album_key = self.get_selected_album_key()
        if album_key is None:
            messagebox.showinfo("Select an album", "Choose an album from the Albums view first.")
            return

        queue = self.library.album_queue(album_key)
        if not queue:
            messagebox.showinfo("Empty album", "That album does not contain any songs.")
            return

        song_id = self.get_primary_album_song_id() or queue[0]
        summary = self.get_selected_album_summary()
        source_name = summary.title if summary else "Album"
        self.start_playback(queue, song_id, source_name)

    def play_selected_album_song(self):
        album_key = self.get_selected_album_key()
        song_id = self.get_primary_album_song_id()
        if album_key is None or not song_id:
            messagebox.showinfo("Select a song", "Choose a song from the album first.")
            return

        summary = self.get_selected_album_summary()
        source_name = summary.title if summary else "Album"
        queue = self.visible_album_song_ids or self.library.album_queue(album_key)
        self.start_playback(queue, song_id, source_name)

    def play_selected_playlist_song(self):
        playlist_name = self.get_selected_playlist_name()
        song_id = self.get_selected_playlist_song_id()
        if not playlist_name or not song_id:
            messagebox.showinfo("Select a song", "Choose a song from the playlist first.")
            return

        queue = self.visible_playlist_song_ids or self.library.playlists[playlist_name]
        self.start_playback(queue, song_id, playlist_name)

    def play_selected(self):
        focused_widget = self.root.focus_get()
        if focused_widget == self.library_tree and self.get_primary_library_song_id():
            self.play_selected_library_song()
            return

        if focused_widget == self.album_tree and self.get_selected_album_key() is not None:
            self.play_album()
            return

        if focused_widget == self.album_song_tree and self.get_primary_album_song_id():
            self.play_selected_album_song()
            return

        if focused_widget == self.playlist_list and self.get_selected_playlist_name():
            self.play_selected_playlist_song()
            return

        if focused_widget == self.playlist_tree and self.get_selected_playlist_song_id():
            self.play_selected_playlist_song()
            return

        if self.active_play_source == "library" and self.get_primary_library_song_id():
            self.play_selected_library_song()
            return

        if self.active_play_source == "album" and self.get_selected_album_key() is not None:
            self.play_album()
            return

        if self.active_play_source == "album_song" and self.get_primary_album_song_id():
            self.play_selected_album_song()
            return

        if self.active_play_source in ("playlist", "playlist_song") and self.get_selected_playlist_song_id():
            self.play_selected_playlist_song()
            return

        current_tab = self.current_notebook_tab()
        if current_tab == str(self.albums_tab) and self.get_selected_album_key() is not None:
            self.play_album()
            return

        self.play_selected_library_song()

    def pause_or_resume(self):
        paused = self.player.toggle_pause()
        if paused is None:
            return

        song = self.library.get_song(self.current_song_id) if self.current_song_id else None
        if paused:
            self.status_label.config(text=f"Paused: {describe_song(song)}" if song else "Paused")
        else:
            self.status_label.config(text=f"Now playing: {describe_song(song)}" if song else "Now playing")

    def stop_playback(self):
        self.player.stop()
        song = self.library.get_song(self.current_song_id) if self.current_song_id else None
        self.current_song_id = None
        self.update_progress_ui(reset=True)

        if song:
            self.status_label.config(text=f"Stopped: {describe_song(song)}")
        else:
            self.status_label.config(text="Stopped")

    def current_notebook_tab(self):
        return self.notebook.select()

    def default_queue(self):
        current_tab = self.current_notebook_tab()
        focused_widget = self.root.focus_get()
        if current_tab == str(self.albums_tab):
            album_key = self.get_selected_album_key()
            if album_key is not None:
                queue = self.visible_album_song_ids or self.library.album_queue(album_key)
                if queue:
                    summary = self.get_selected_album_summary()
                    source_name = summary.title if summary else "Album"
                    return queue, source_name

        if focused_widget in (self.playlist_list, self.playlist_tree):
            playlist_name = self.get_selected_playlist_name()
            queue = self.visible_playlist_song_ids or self.library.playlists.get(playlist_name, [])
            if playlist_name and queue:
                return queue, playlist_name

        return (self.visible_library_song_ids or [song.id for song in self.library.sorted_songs()]), "Library"

    def change_song(self, step):
        queue = list(self.current_queue)
        source_name = self.current_queue_source

        if not queue:
            queue, source_name = self.default_queue()

        if not queue:
            messagebox.showinfo("No songs", "Import songs or create albums or playlists first.")
            return

        if self.current_song_id in queue:
            current_index = queue.index(self.current_song_id)
        elif self.current_queue_index is not None and self.current_queue_index < len(queue):
            current_index = self.current_queue_index
        else:
            current_index = 0 if step > 0 else len(queue) - 1

        new_index = (current_index + step) % len(queue)
        self.start_playback(queue, queue[new_index], source_name)

    def next_song(self):
        self.change_song(1)

    def previous_song(self):
        self.change_song(-1)

    def update_progress_ui(self, reset=False):
        if reset or self.current_song_id is None:
            self.progress_var.set(0.0)
            self.time_label_var.set("0:00 / 0:00")
            self.spectrogram_data = None
            self.spectrogram_loading = False
            self.transient_peaks = []
            self.transient_loading = False
            self.invalidate_spectrogram_photo()
            self.draw_current_analyzer()
            return

        duration = self.player.duration()
        current_time = self.player.current_time()
        upper_bound = duration if duration > 0 else 100
        if not self.dragging_progress:
            self.progress_var.set(min(current_time, upper_bound))
        self.time_label_var.set(f"{format_seconds(current_time)} / {format_seconds(duration)}")
        self.draw_current_analyzer()

    def load_analyzer_for_song(self, song_id, path):
        self.analyzer_job_token += 1
        token = self.analyzer_job_token
        self.spectrogram_data = None
        self.spectrogram_loading = True
        self.transient_peaks = []
        self.transient_loading = True
        self.invalidate_spectrogram_photo()
        self.draw_current_analyzer()

        def worker():
            try:
                peaks = build_waveform_peaks(path, target_bars=1200)
            except Exception:
                peaks = []

            try:
                self.root.after(0, lambda: self.apply_transient(token, song_id, peaks))
            except RuntimeError:
                return

            try:
                spectrogram = build_spectrogram(path)
            except Exception:
                spectrogram = None

            try:
                self.root.after(0, lambda: self.apply_spectrogram(token, song_id, spectrogram))
            except RuntimeError:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def apply_transient(self, token, song_id, peaks):
        if token != self.analyzer_job_token or song_id != self.current_song_id:
            return

        self.transient_peaks = peaks
        self.transient_loading = False
        if self.current_analyzer_mode() == "transient":
            self.draw_transient()

    def apply_spectrogram(self, token, song_id, spectrogram):
        if token != self.analyzer_job_token or song_id != self.current_song_id:
            return

        self.spectrogram_data = spectrogram
        self.spectrogram_loading = False
        self.invalidate_spectrogram_photo()
        if self.current_analyzer_mode() == "spectrogram":
            self.draw_spectrogram()

    def build_spectrogram_palette(self):
        stops = [
            (0.00, (0, 0, 8)),
            (0.12, (18, 0, 72)),
            (0.28, (0, 30, 190)),
            (0.45, (0, 205, 255)),
            (0.62, (35, 235, 75)),
            (0.78, (245, 245, 35)),
            (0.91, (255, 135, 0)),
            (1.00, (255, 25, 0)),
        ]

        palette = []
        stop_index = 0
        for value in range(256):
            ratio = value / 255.0
            while stop_index < len(stops) - 2 and ratio > stops[stop_index + 1][0]:
                stop_index += 1

            start_ratio, start_color = stops[stop_index]
            end_ratio, end_color = stops[stop_index + 1]
            span = max(0.0001, end_ratio - start_ratio)
            mix = min(1.0, max(0.0, (ratio - start_ratio) / span))
            red = int(start_color[0] + (end_color[0] - start_color[0]) * mix)
            green = int(start_color[1] + (end_color[1] - start_color[1]) * mix)
            blue = int(start_color[2] + (end_color[2] - start_color[2]) * mix)
            palette.append(bytes((red, green, blue)))

        return palette

    def invalidate_spectrogram_photo(self):
        self.spectrogram_photo = None
        self.spectrogram_photo_cache_key = None

    def current_analyzer_mode(self):
        notebook = getattr(self, "analyzer_notebook", None)
        transient_tab = getattr(self, "transient_tab", None)
        if notebook is None or transient_tab is None:
            return "spectrogram"

        try:
            return "transient" if notebook.select() == str(transient_tab) else "spectrogram"
        except tk.TclError:
            return "spectrogram"

    def draw_current_analyzer(self):
        if self.current_analyzer_mode() == "transient":
            self.draw_transient()
        else:
            self.draw_spectrogram()

    def on_analyzer_tab_changed(self, _event=None):
        if not hasattr(self, "analyzer_label"):
            return

        if self.current_analyzer_mode() == "transient":
            self.analyzer_label.configure(text="Transient analyzer")
        else:
            self.analyzer_label.configure(text="Spectrogram analyzer")

        self.draw_current_analyzer()

    def draw_spectrogram(self):
        canvas = getattr(self, "analyzer_canvas", None)
        if canvas is None:
            return

        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        left, top, plot_width, plot_height, show_axes, show_legend = self.spectrogram_plot_bounds(width, height)
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#05070b", outline="")

        if self.spectrogram_data is not None:
            photo = self.render_spectrogram_photo(self.spectrogram_data, plot_width, plot_height)
            canvas.create_image(left, top, image=photo, anchor="nw")
        else:
            self.draw_spectrogram_placeholder(canvas, left, top, plot_width, plot_height)

        duration = self.player.duration() if self.current_song_id else 0.0
        progress_ratio = 0.0
        if duration > 0:
            progress_ratio = min(1.0, max(0.0, self.progress_var.get() / duration))

        max_frequency = self.spectrogram_data.max_frequency if self.spectrogram_data is not None else 20000.0
        if show_axes:
            self.draw_spectrogram_axes(canvas, left, top, plot_width, plot_height, max_frequency, duration)
        else:
            canvas.create_rectangle(left, top, left + plot_width, top + plot_height, outline="#1c2735")

        if show_legend:
            self.draw_spectrogram_legend(canvas, left + plot_width + 12, top, plot_height)

        if self.spectrogram_loading:
            canvas.create_text(
                left + plot_width / 2,
                top + plot_height / 2,
                text="Analyzing spectrum...",
                fill="#d6deeb",
                font=("Helvetica Neue", 12, "bold"),
            )

        if duration > 0:
            cursor_x = left + (progress_ratio * plot_width)
            canvas.create_line(cursor_x, top, cursor_x, top + plot_height, fill="#ffffff", width=2)
            canvas.create_line(cursor_x + 1, top, cursor_x + 1, top + plot_height, fill="#18212f", width=1)

    def spectrogram_plot_bounds(self, width, height):
        show_axes = width >= 460 and height >= 118
        show_legend = width >= 620 and height >= 130
        left = 62 if show_axes else 8
        right = 88 if show_legend else 18 if show_axes else 8
        top = 16 if show_axes else 8
        bottom = 30 if show_axes else 8
        plot_width = max(1, width - left - right)
        plot_height = max(1, height - top - bottom)
        return left, top, plot_width, plot_height, show_axes, show_legend

    def render_spectrogram_photo(self, spectrogram, width, height):
        values = spectrogram.values
        cache_key = (id(values), width, height)
        if self.spectrogram_photo is not None and self.spectrogram_photo_cache_key == cache_key:
            return self.spectrogram_photo

        source_height, source_width = values.shape
        pixels = bytearray()
        for y in range(height):
            source_y = source_height - 1 - min(source_height - 1, int(y * source_height / height))
            row = values[source_y]
            for x in range(width):
                source_x = min(source_width - 1, int(x * source_width / width))
                pixels.extend(self.spectrogram_palette[int(row[source_x])])

        header = f"P6\n{width} {height}\n255\n".encode("ascii")
        self.spectrogram_photo = tk.PhotoImage(data=header + pixels, format="PPM")
        self.spectrogram_photo_cache_key = cache_key
        return self.spectrogram_photo

    def draw_spectrogram_placeholder(self, canvas, left, top, width, height):
        canvas.create_rectangle(left, top, left + width, top + height, fill="#060912", outline="")
        for x in range(0, width, 3):
            shimmer = ((x * 7) % 37) / 36.0
            low_band = int(height * (0.50 + shimmer * 0.22))
            mid_band = int(height * (0.25 + shimmer * 0.18))
            color = "#13233f" if self.spectrogram_loading else "#101827"
            canvas.create_line(left + x, top + low_band, left + x, top + height, fill=color)
            if x % 9 == 0:
                canvas.create_line(left + x, top + mid_band, left + x, top + low_band, fill="#0b1730")

    def draw_spectrogram_axes(self, canvas, left, top, width, height, max_frequency, duration):
        grid_color = "#1b2635"
        label_color = "#d6deeb"
        muted_color = "#8d99aa"

        frequency_ticks = [0, max_frequency * 0.25, max_frequency * 0.50, max_frequency * 0.75, max_frequency]
        for frequency in frequency_ticks:
            ratio = frequency / max(max_frequency, 1.0)
            y = top + height - (ratio * height)
            label_y = min(max(y, top + 7), top + height - 7)
            canvas.create_line(left, y, left + width, y, fill=grid_color)
            canvas.create_text(
                left - 8,
                label_y,
                text=self.format_frequency_label(frequency),
                anchor="e",
                fill=label_color,
                font=("Helvetica Neue", 10),
            )

        center_y = height / 2
        canvas.create_line(0, center_y, width, center_y, fill=self.waveform_axis_color)

        center_y = top + plot_height / 2
        canvas.create_line(left, center_y, left + plot_width, center_y, fill="#f1f1f1", width=1)

        peaks = self.transient_peaks or self.placeholder_transient_peaks(plot_width)
        duration = self.player.duration() if self.current_song_id else 0.0
        progress_ratio = 0.0
        if duration > 0:
            progress_ratio = min(1.0, max(0.0, self.progress_var.get() / duration))

        count = len(peaks)
        bar_gap = 2
        bar_width = max(2, min(5, int(width / max(count, 1)) - bar_gap))
        empty_color = self.waveform_empty_color if not self.waveform_loading else self.waveform_loading_color
        active_color = self.accent

        for index, peak in enumerate(peaks):
            ratio = (index + 0.5) / count
            x = left + ratio * plot_width
            amplitude = max(0.015, min(1.0, float(peak)))
            played = ratio <= progress_ratio
            upper_color = "#ffb000" if played else "#0b6dff"
            lower_color = "#c57400" if played else "#0050d8"
            highlight_color = "#f8f8f8" if played else "#d8edff"

            top_y = center_y - amplitude * upper_scale
            bottom_y = center_y + amplitude * lower_scale
            canvas.create_line(x, center_y, x, top_y, fill=upper_color, width=line_width)
            canvas.create_line(x, center_y, x, bottom_y, fill=lower_color, width=line_width)

            if amplitude > 0.18 and index % 2 == 0:
                ridge = max(1.0, amplitude * 5.0)
                canvas.create_line(x, center_y - ridge, x, center_y + ridge, fill=highlight_color, width=1)

        if self.transient_loading:
            canvas.create_text(
                left + plot_width / 2,
                top + plot_height / 2,
                text="Analyzing transients...",
                fill="#d8d8d8",
                font=("Helvetica Neue", 12, "bold"),
            )

        if duration > 0:
            cursor_x = progress_ratio * width
            canvas.create_line(cursor_x, 8, cursor_x, height - 8, fill=self.waveform_cursor_color, width=2)

    def placeholder_waveform_peaks(self, width):
        count = max(36, min(140, width // 7))
        peaks = []
        for index in range(count):
            pulse = 0.08 + 0.10 * ((index * 5) % 13) / 12
            accent = 0.32 if index % 47 in (0, 1, 2) else 0.0
            peaks.append(min(1.0, pulse + accent))
        return peaks

    def update_progress_from_event(self, event):
        if self.current_song_id is None:
            return

        duration = self.player.duration()
        if duration <= 0:
            return

        canvas = event.widget
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        if canvas == getattr(self, "transient_canvas", None):
            left, _top, plot_width, _plot_height = self.transient_plot_bounds(width, height)
        else:
            left, _top, plot_width, _plot_height, _show_axes, _show_legend = self.spectrogram_plot_bounds(width, height)

        ratio = min(1.0, max(0.0, (event.x - left) / plot_width))
        target_time = duration * ratio
        self.progress_var.set(target_time)
        self.time_label_var.set(f"{format_seconds(target_time)} / {format_seconds(duration)}")
        self.draw_current_analyzer()

    def on_progress_press(self, event):
        if self.current_song_id is None:
            return
        self.dragging_progress = True
        self.update_progress_from_event(event)

    def on_progress_drag(self, event):
        if self.current_song_id is None:
            return

        self.update_progress_from_event(event)

    def on_progress_release(self, event):
        if self.current_song_id is None:
            return

        self.update_progress_from_event(event)
        self.dragging_progress = False
        self.player.seek(self.progress_var.get())
        self.update_progress_ui()

    def poll_player(self):
        self.update_progress_ui()

        if self.player.finished():
            finished_song = self.library.get_song(self.current_song_id) if self.current_song_id else None
            self.player.stop()

            if self.current_queue and self.current_queue_index is not None:
                next_index = self.current_queue_index + 1
                if next_index < len(self.current_queue):
                    next_song_id = self.current_queue[next_index]
                    self.start_playback(self.current_queue, next_song_id, self.current_queue_source)
                else:
                    self.current_song_id = None
                    self.update_progress_ui(reset=True)
                    if finished_song:
                        self.status_label.config(text=f"Finished: {describe_song(finished_song)}")
                    else:
                        self.status_label.config(text="Finished")

        self.root.after(250, self.poll_player)

    def open_songs_folder(self):
        subprocess.Popen(["open", str(self.paths.songs_dir)])


def main():
    root = tk.Tk()

    try:
        app = AudioPlayerApp(root)
    except RuntimeError as exc:
        root.withdraw()
        messagebox.showerror("Startup Error", str(exc))
        root.destroy()
        raise SystemExit(1) from exc

    root.protocol("WM_DELETE_WINDOW", lambda: (app.player.stop(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
