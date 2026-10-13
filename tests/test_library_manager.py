import tempfile
import unittest
from pathlib import Path

from audio_player.config import AppPaths
from audio_player.library import LibraryManager


class LibraryManagerTests(unittest.TestCase):
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

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_import_files_copies_supported_audio_and_assigns_unique_names(self):
        first_source = self.root / "first"
        second_source = self.root / "second"
        unsupported_source = self.root / "notes.txt"
        first_source.mkdir()
        second_source.mkdir()
        (first_source / "Track.mp3").write_bytes(b"first audio")
        (second_source / "Track.mp3").write_bytes(b"second audio")
        unsupported_source.write_text("not audio", encoding="utf-8")

        imported_count = self.library.import_files(
            [first_source / "Track.mp3", second_source / "Track.mp3", unsupported_source]
        )

        self.assertEqual(imported_count, 2)
        self.assertEqual({song.filename for song in self.library.library}, {"Track.mp3", "Track 2.mp3"})
        self.assertEqual((self.paths.songs_dir / "Track.mp3").read_bytes(), b"first audio")
        self.assertEqual((self.paths.songs_dir / "Track 2.mp3").read_bytes(), b"second audio")

    def test_import_album_assigns_album_and_artist(self):
        album_dir = self.root / "album-source"
        album_dir.mkdir()
        (album_dir / "01 - Intro.wav").write_bytes(b"intro")
        (album_dir / "02 - Finale.flac").write_bytes(b"finale")

        imported_songs = self.library.import_album(album_dir, "Night Drive", "The Example")

        self.assertEqual(len(imported_songs), 2)
        self.assertEqual({song.album for song in imported_songs}, {"Night Drive"})
        self.assertEqual({song.artist for song in imported_songs}, {"The Example"})

    def test_aiff_import_reload_and_playlist_export_preserve_files(self):
        source_paths = []
        for index, suffix in enumerate((".aif", ".aiff", ".AIF", ".AIFF")):
            source = self.root / f"Track {index}{suffix}"
            source.write_bytes(f"AIFF audio {index}".encode("utf-8"))
            source_paths.append(source)

        self.assertEqual(self.library.import_files(source_paths), 4)
        self.library.create_playlist("AIFF playlist")
        self.library.add_songs_to_playlist("AIFF playlist", [song.id for song in self.library.library])
        reloaded_library = LibraryManager(self.paths)
        self.assertEqual(len(reloaded_library.playlist_songs("AIFF playlist")), 4)
        export_root, playlist_file, missing_titles, copied_count = reloaded_library.export_playlist(
            "AIFF playlist", self.root / "exports",
        )

        self.assertEqual(copied_count, 4)
        self.assertEqual(missing_titles, [])
        for source in source_paths:
            exported_name = source.stem + source.suffix.lower()
            self.assertEqual((export_root / exported_name).read_bytes(), source.read_bytes())
            self.assertIn(exported_name, playlist_file.read_text(encoding="utf-8"))

    def test_import_album_accepts_aiff_in_nested_folders(self):
        album_dir = self.root / "aiff-album"
        nested_dir = album_dir / "disc-two"
        nested_dir.mkdir(parents=True)
        (album_dir / "Intro.aif").write_bytes(b"intro")
        (nested_dir / "Finale.AIFF").write_bytes(b"finale")
        (album_dir / "notes.txt").write_text("not audio", encoding="utf-8")

        imported_songs = self.library.import_album(album_dir, "AIFF Album", "The Example")

        self.assertEqual({song.filename for song in imported_songs}, {"Intro.aif", "Finale.aiff"})
        self.assertEqual({song.album for song in imported_songs}, {"AIFF Album"})
        self.assertEqual({song.artist for song in imported_songs}, {"The Example"})

    def test_library_discovers_aiff_copied_into_songs_folder(self):
        (self.paths.songs_dir / "Existing.AIFF").write_bytes(b"existing audio")

        reloaded_library = LibraryManager(self.paths)

        self.assertEqual([song.filename for song in reloaded_library.library], ["Existing.AIFF"])

    def test_playlist_order_and_membership_survive_reload(self):
        songs = self._import_songs("one.mp3", "two.mp3")
        self.library.create_playlist("Road Trip")

        added_count = self.library.add_songs_to_playlist(
            "Road Trip", [songs[1].id, songs[1].id, "unknown-id", songs[0].id]
        )
        reloaded_library = LibraryManager(self.paths)

        self.assertEqual(added_count, 2)
        self.assertEqual(
            [song.title for song in reloaded_library.playlist_songs("Road Trip")],
            ["two", "one"],
        )

    def test_export_writes_ordered_portable_playlist_bundle(self):
        songs = self._import_songs("one.mp3", "two.mp3")
        self.library.update_artist([songs[0].id, songs[1].id], "The Example")
        self.library.create_playlist("Road Trip")
        self.library.add_songs_to_playlist("Road Trip", [songs[1].id, songs[0].id])

        export_root, playlist_file, missing_titles, copied_count = self.library.export_playlist(
            "Road Trip", self.root / "exports"
        )

        self.assertEqual(copied_count, 2)
        self.assertEqual(missing_titles, [])
        self.assertTrue((export_root / "one.mp3").is_file())
        self.assertTrue((export_root / "two.mp3").is_file())
        self.assertEqual(
            playlist_file.read_text(encoding="utf-8"),
            "#EXTM3U\n#EXTINF:-1,two - The Example\ntwo.mp3\n"
            "#EXTINF:-1,one - The Example\none.mp3\n",
        )

    def _import_songs(self, *filenames):
        source_dir = self.root / f"source-{len(list(self.root.iterdir()))}"
        source_dir.mkdir()
        source_paths = []
        for filename in filenames:
            source = source_dir / filename
            source.write_bytes(filename.encode("utf-8"))
            source_paths.append(source)

        self.library.import_files(source_paths)
        songs_by_filename = {song.filename: song for song in self.library.library}
        return [songs_by_filename[path.name] for path in source_paths]


if __name__ == "__main__":
    unittest.main()
