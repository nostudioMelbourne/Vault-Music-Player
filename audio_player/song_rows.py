class SongRowsMixin:
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
