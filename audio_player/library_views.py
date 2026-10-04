"""Manage library view selections and refresh the visible widgets."""

import tkinter as tk


class LibraryViewsMixin:
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

    def refresh_all_views(self):
        self.refresh_library_tree()
        self.refresh_album_tree()
        self.refresh_playlist_list()
        self.refresh_playlist_tree()
        self.update_status_strip()

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
                tags=self.theme_tree_tags(),
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

        if not all_songs:
            self.songs_hint_label.configure(text="No songs in the vault yet. Use Library > Import Songs... or Import Album.")
        elif query and not visible_songs:
            self.songs_hint_label.configure(text=f"No songs match '{self.song_search_var.get().strip()}'. Clear search to return to the full library.")
        else:
            self.songs_hint_label.configure(text="Songs: double-click plays, right-click edits, drag rows into playlists.")

        self.update_status_strip()

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
                tags=self.theme_tree_tags(),
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

        if not self.normalized_query(self.album_song_search_var.get()):
            if not all_summaries:
                self.albums_hint_label.configure(text="Albums appear after imports. Unassigned tracks are grouped as Singles / Unassigned.")
            elif query and not visible_summaries:
                self.albums_hint_label.configure(text=f"No albums match '{self.album_search_var.get().strip()}'. Clear search to see all releases.")
            else:
                self.albums_hint_label.configure(text="Albums: play full releases, filter tracks, or drag an album into a playlist.")

        self.update_status_strip()

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
            self.update_status_strip()
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
                tags=self.theme_tree_tags(),
            )

        existing_selection = [song_id for song_id in selected_song_ids if self.album_song_tree.exists(song_id)]
        if existing_selection:
            self.album_song_tree.selection_set(existing_selection)

        if focused_song_id and self.album_song_tree.exists(focused_song_id):
            self.album_song_tree.focus(focused_song_id)
        elif existing_selection:
            self.album_song_tree.focus(existing_selection[0])

        if query and not visible_songs:
            self.albums_hint_label.configure(text=f"No tracks in this album match '{self.album_song_search_var.get().strip()}'.")
        elif query:
            self.albums_hint_label.configure(text=f"Album tracks: showing {len(visible_songs)} of {len(all_songs)} matches.")

        self.update_status_strip()

    def refresh_playlist_list(self):
        selected_playlist = self.get_selected_playlist_name()
        self.all_playlist_names = sorted(self.library.playlists, key=str.casefold)
        query = self.normalized_query(self.playlist_search_var.get())
        self.playlist_names = [name for name in self.all_playlist_names if query in name.casefold()]

        self.playlist_list.delete(0, tk.END)
        for name in self.playlist_names:
            self.playlist_list.insert(tk.END, name)

        self.playlist_list_frame.configure(text=f"Playlists ({len(self.playlist_names)}/{len(self.all_playlist_names)})")
        if not self.all_playlist_names:
            self.playlists_hint_label.configure(text="No playlists yet. Create one, then drag songs or albums straight into it.")
        elif query and not self.playlist_names:
            self.playlists_hint_label.configure(text=f"No playlists match '{self.playlist_search_var.get().strip()}'. Clear search to show them all.")
        else:
            self.playlists_hint_label.configure(text="Playlists stay open while you browse. Right-click to manage, drag rows to add.")

        if not self.playlist_names:
            self.playlist_list.selection_clear(0, tk.END)
            self.refresh_playlist_tree()
            self.update_status_strip()
            return

        if selected_playlist not in self.playlist_names:
            selected_playlist = self.playlist_names[0]

        index = self.playlist_names.index(selected_playlist)
        self.playlist_list.selection_clear(0, tk.END)
        self.playlist_list.selection_set(index)
        self.playlist_list.activate(index)
        self.playlist_list.see(index)
        self.update_status_strip()

    def refresh_playlist_tree(self):
        selected_song_id = self.get_selected_playlist_song_id()
        self.visible_playlist_song_ids = []

        for item in self.playlist_tree.get_children():
            self.playlist_tree.delete(item)

        playlist_name = self.get_selected_playlist_name()
        if not playlist_name:
            self.playlist_song_frame.configure(text="Playlist Songs")
            self.update_status_strip()
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
                tags=self.theme_tree_tags(),
            )

        if selected_song_id and self.playlist_tree.exists(selected_song_id):
            self.playlist_tree.selection_set(selected_song_id)
            self.playlist_tree.focus(selected_song_id)

        if not all_songs:
            self.playlists_hint_label.configure(text=f"Playlist '{playlist_name}' is empty. Drag songs or albums here to build it.")
        elif query and not visible_songs:
            self.playlists_hint_label.configure(text=f"No tracks in '{playlist_name}' match '{self.playlist_song_search_var.get().strip()}'.")

        self.update_status_strip()
