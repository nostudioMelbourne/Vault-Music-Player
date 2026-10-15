import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .conversion import CONVERSION_FORMATS, ConversionCancelled, convert_audio_file
from .dialogs import QueryDialog


class ConversionDialog(QueryDialog):
    def __init__(self, parent, count):
        super().__init__(parent, "Convert Audio", f"Convert {count} selected file(s) to:")

    def body(self, master):
        ttk.Label(master, text=self.prompt).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.format_box = ttk.Combobox(
            master, state="readonly", values=[item.label for item in CONVERSION_FORMATS], width=32,
        )
        self.format_box.current(0)
        self.format_box.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Label(master, text="Save converted copies in:").grid(row=2, column=0, sticky="w", pady=(12, 4))
        self.folder_var = tk.StringVar(master=self)
        self.folder_entry = ttk.Entry(master, textvariable=self.folder_var, width=40)
        self.folder_entry.grid(row=3, column=0, sticky="ew")
        ttk.Button(master, text="Choose...", command=self.choose_folder, style="Action.TButton").grid(
            row=3, column=1, padx=(8, 0),
        )
        ttk.Label(
            master, text="Originals stay unchanged. Existing files are never overwritten.\n"
                         "Copies are not automatically added to your library.",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(12, 0))
        return self.format_box

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self, title="Save converted audio", mustexist=True)
        if folder:
            self.folder_var.set(folder)

    def validate(self):
        folder = self.folder_var.get().strip()
        if not folder or not Path(folder).is_dir():
            messagebox.showwarning("Convert Audio", "Choose an existing output folder.", parent=self)
            self.folder_entry.focus_set()
            return False
        self.result = (Path(folder), CONVERSION_FORMATS[self.format_box.current()])
        return True


class ConversionProgress:
    def __init__(self, parent, sources, destination, output_format):
        self.sources = sources
        self.destination = destination
        self.output_format = output_format
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.window = tk.Toplevel(parent)
        self.window.title("Converting Audio")
        self.window.transient(parent)
        self.window.resizable(False, False)
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        self.status = ttk.Label(frame, text=f"Converting 0 of {len(sources)} files", width=48)
        self.status.pack(anchor="w")
        self.progress = ttk.Progressbar(frame, maximum=len(sources), length=380)
        self.progress.pack(fill=tk.X, pady=12)
        self.cancel_button = ttk.Button(frame, text="Cancel", command=self.request_cancel, style="Action.TButton")
        self.cancel_button.pack(anchor="e")
        self.window.protocol("WM_DELETE_WINDOW", self.request_cancel)
        self.window.bind("<Escape>", lambda event: self.request_cancel())
        self.window.bind("<Destroy>", self.on_destroy, add="+")
        self.window.grab_set()
        threading.Thread(target=self.work, daemon=True).start()
        self.window.after(100, self.poll)

    def on_destroy(self, event):
        if event.widget is self.window:
            self.cancel.set()

    def request_cancel(self):
        self.cancel.set()
        self.cancel_button.config(state=tk.DISABLED)
        self.status.config(text="Cancelling; completed copies will be kept...")

    def work(self):
        outputs = []
        errors = []
        for index, source in enumerate(self.sources, start=1):
            if self.cancel.is_set():
                break
            self.events.put(("progress", index, source.name))
            try:
                outputs.append(convert_audio_file(source, self.destination, self.output_format, self.cancel))
            except ConversionCancelled:
                break
            except (OSError, ValueError) as error:
                errors.append(f"{source.name}: {error}")
            self.events.put(("completed", index))
        self.events.put(("done", outputs, errors, self.cancel.is_set()))

    def poll(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if event[0] == "progress":
                if not self.cancel.is_set():
                    self.status.config(text=f"Converting {event[1]} of {len(self.sources)}: {event[2]}")
            elif event[0] == "completed":
                self.progress.config(value=event[1])
            else:
                _, outputs, errors, cancelled = event
                parent = self.window.master
                self.window.destroy()
                summary = f"Saved {len(outputs)} of {len(self.sources)} converted copies in:\n{self.destination}"
                if cancelled:
                    summary += "\n\nCancelled. Completed copies were kept."
                if errors:
                    summary += f"\n\n{len(errors)} file(s) failed:\n" + "\n".join(errors[:5])
                    if len(errors) > 5:
                        summary += "\n..."
                summary += "\n\nOriginal files were not changed."
                notification = messagebox.showwarning if errors else messagebox.showinfo
                notification("Convert Audio", summary, parent=parent)
                return
        self.window.after(100, self.poll)


class AudioConversionMixin:
    def convert_song_ids(self, song_ids):
        songs = [self.library.get_song(song_id) for song_id in dict.fromkeys(song_ids)]
        sources = [self.library.song_path(song) for song in songs if song is not None]
        if not sources:
            messagebox.showinfo("Convert Audio", "Select one or more songs to convert.", parent=self.root)
            return
        selection = ConversionDialog(self.root, len(sources)).result
        if selection is not None:
            destination, output_format = selection
            ConversionProgress(self.root, sources, destination, output_format)
