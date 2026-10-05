import unittest
from unittest.mock import Mock

from audio_player.library_views import LibraryViewsMixin


class LibraryViewFilterTests(unittest.TestCase):
    def setUp(self):
        self.view = LibraryViewsMixin()
        self.view.song_search_var = "songs_filter"
        self.view.refresh_library_tree = Mock()
        self.view.refresh_all_views = Mock()

    def test_song_filter_trace_only_refreshes_songs(self):
        self.view.on_filter_change("songs_filter", "", "write")

        self.view.refresh_library_tree.assert_called_once_with()
        self.view.refresh_all_views.assert_not_called()

    def test_other_filters_keep_the_existing_full_refresh(self):
        for name in ("albums_filter", "album_tracks_filter", "playlists_filter", "playlist_tracks_filter"):
            with self.subTest(name=name):
                self.view.refresh_all_views.reset_mock()
                self.view.on_filter_change(name, "", "write")
                self.view.refresh_all_views.assert_called_once_with()
                self.view.refresh_library_tree.assert_not_called()

    def test_manual_refresh_without_a_trace_name_still_refreshes_all_views(self):
        self.view.on_filter_change()

        self.view.refresh_all_views.assert_called_once_with()
        self.view.refresh_library_tree.assert_not_called()


if __name__ == "__main__":
    unittest.main()
