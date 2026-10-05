"""Handle playback, removal, and search shortcuts without interrupting typing."""

import tkinter as tk


class KeyboardShortcutsMixin:
    def focus_accepts_text(self):
        focused_widget = self.root.focus_get()
        if focused_widget is None:
            return False

        try:
            widget_class = focused_widget.winfo_class()
        except tk.TclError:
            return False

        return widget_class in {"Entry", "TEntry", "Text", "Spinbox", "TSpinbox"}

    def on_return_key(self, _event):
        if self.focus_accepts_text():
            return None

        self.play_selected()
        return "break"

    def on_space_key(self, _event):
        if self.focus_accepts_text():
            return None

        self.pause_or_resume()
        return "break"

    def on_delete_key(self, _event):
        if self.focus_accepts_text():
            return None

        focused_widget = self.root.focus_get()
        if focused_widget == self.library_tree:
            self.remove_song()
            return "break"

        if focused_widget == self.album_song_tree:
            self.remove_song(self.get_selected_album_song_ids())
            return "break"

        if focused_widget == self.playlist_tree:
            self.remove_song_from_playlist()
            return "break"

        if focused_widget == self.playlist_list:
            self.delete_playlist()
            return "break"

        return None

    def focus_active_search(self, _event=None):
        focused_widget = self.root.focus_get()
        target = self.song_search_entry

        if focused_widget in (self.playlist_list, self.playlist_search_entry):
            target = self.playlist_search_entry
        elif focused_widget in (self.playlist_tree, self.playlist_song_search_entry):
            target = self.playlist_song_search_entry
        elif self.current_notebook_tab() == str(self.albums_tab):
            if focused_widget in (self.album_song_tree, self.album_song_search_entry):
                target = self.album_song_search_entry
            else:
                target = self.album_search_entry

        target.focus_set()
        target.select_range(0, tk.END)
        return "break"

    def clear_focused_filter(self, _event=None):
        focused_widget = self.root.focus_get()
        filter_pairs = (
            (self.song_search_entry, self.song_search_var),
            (self.album_search_entry, self.album_search_var),
            (self.album_song_search_entry, self.album_song_search_var),
            (self.playlist_search_entry, self.playlist_search_var),
            (self.playlist_song_search_entry, self.playlist_song_search_var),
        )

        for entry, variable in filter_pairs:
            if focused_widget == entry and variable.get():
                variable.set("")
                return "break"

        return None
