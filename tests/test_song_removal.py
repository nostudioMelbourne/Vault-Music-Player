import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audio_player.config import AppPaths
from audio_player.library import LibraryManager


class SongRemovalTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.data_dir = self.root / "app-data"
        self.script_dir = self.root / "application"
        self.script_dir.mkdir()
        self.paths = AppPaths(
            script_dir=self.script_dir,
            app_support_dir=self.data_dir,
            songs_dir=self.data_dir / "songs",
            library_db=self.data_dir / "library.json",
            playlist_db=self.data_dir / "playlists.json",
            settings_db=self.data_dir / "settings.json",
            legacy_songs_dir=self.script_dir / "songs",
            legacy_playlists_dir=self.script_dir / "playlists",
            icon_candidates=(),
        )
        self.library = LibraryManager(self.paths)
        source = self.root / "Track.mp3"
        source.write_bytes(b"audio data")
        self.library.import_files([source])
        self.song = self.library.library[0]
        self.library.create_playlist("Favorites")
        self.library.add_songs_to_playlist("Favorites", [self.song.id])

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_successful_removal_moves_file_and_prunes_playlist(self):
        song_path = self.library.song_path(self.song)
        with patch("audio_player.library.move_to_trash", side_effect=lambda path: path.unlink()) as move:
            removed, failures = self.library.remove_songs([self.song.id])

        self.assertEqual([song.id for song in removed], [self.song.id])
        self.assertEqual(failures, [])
        move.assert_called_once_with(song_path)
        self.assertFalse(song_path.exists())
        self.assertEqual(self.library.playlists["Favorites"], [])

    def test_failed_trash_operation_keeps_file_library_entry_and_playlist(self):
        song_path = self.library.song_path(self.song)
        with patch("audio_player.library.move_to_trash", side_effect=OSError("Trash unavailable")):
            removed, failures = self.library.remove_songs([self.song.id])

        self.assertEqual(removed, [])
        self.assertEqual(failures, ["Track: Trash unavailable"])
        self.assertTrue(song_path.exists())
        self.assertIsNotNone(self.library.get_song(self.song.id))
        self.assertEqual(self.library.playlists["Favorites"], [self.song.id])


if __name__ == "__main__":
    unittest.main()
