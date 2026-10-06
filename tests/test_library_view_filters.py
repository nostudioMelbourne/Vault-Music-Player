import unittest
from unittest.mock import Mock

from audio_player.library_views import LibraryViewsMixin


class LibraryViewFilterTests(unittest.TestCase):
    def setUp(self):
        self.view = LibraryViewsMixin()
        self.view.song_search_var = "songs_filter"
        self.view.album_search_var = "albums_filter"
        self.view.playlist_search_var = "playlists_filter"
        self.view.playlist_names = ["Evening"]
        self.view.refresh_library_tree = Mock()
        self.view.refresh_album_tree = Mock()
        self.view.refresh_playlist_list = Mock()
        self.view.refresh_playlist_tree = Mock()
        self.view.refresh_all_views = Mock()

    def test_song_filter_trace_only_refreshes_songs(self):
        self.view.on_filter_change("songs_filter", "", "write")

        self.view.refresh_library_tree.assert_called_once_with()
        self.view.refresh_album_tree.assert_not_called()
        self.view.refresh_playlist_list.assert_not_called()
        self.view.refresh_playlist_tree.assert_not_called()
        self.view.refresh_all_views.assert_not_called()

    def test_album_filter_trace_only_refreshes_albums(self):
        self.view.on_filter_change("albums_filter", "", "write")

        self.view.refresh_album_tree.assert_called_once_with()
        self.view.refresh_library_tree.assert_not_called()
        self.view.refresh_playlist_list.assert_not_called()
        self.view.refresh_playlist_tree.assert_not_called()
        self.view.refresh_all_views.assert_not_called()

    def test_playlist_filter_refreshes_list_before_tracks_without_other_views(self):
        events = []
        self.view.refresh_playlist_list.side_effect = lambda: events.append("list")
        self.view.refresh_playlist_tree.side_effect = lambda: events.append("tracks")

        self.view.on_filter_change("playlists_filter", "", "write")

        self.assertEqual(events, ["list", "tracks"])
        self.view.refresh_playlist_list.assert_called_once_with()
        self.view.refresh_playlist_tree.assert_called_once_with()
        self.view.refresh_library_tree.assert_not_called()
        self.view.refresh_album_tree.assert_not_called()
        self.view.refresh_all_views.assert_not_called()

    def test_empty_playlist_filter_does_not_repeat_track_refresh(self):
        def clear_playlists():
            self.view.playlist_names = []
            self.view.refresh_playlist_tree()
        self.view.refresh_playlist_list.side_effect = clear_playlists

        self.view.on_filter_change("playlists_filter", "", "write")

        self.view.refresh_playlist_list.assert_called_once_with()
        self.view.refresh_playlist_tree.assert_called_once_with()
        self.view.refresh_library_tree.assert_not_called()
        self.view.refresh_album_tree.assert_not_called()
        self.view.refresh_all_views.assert_not_called()

    def test_other_filters_keep_the_existing_full_refresh(self):
        for name in ("album_tracks_filter", "playlist_tracks_filter"):
            with self.subTest(name=name):
                self.view.refresh_all_views.reset_mock()
                self.view.on_filter_change(name, "", "write")
                self.view.refresh_all_views.assert_called_once_with()
                self.view.refresh_library_tree.assert_not_called()
                self.view.refresh_album_tree.assert_not_called()
                self.view.refresh_playlist_list.assert_not_called()
                self.view.refresh_playlist_tree.assert_not_called()

    def test_manual_refresh_without_a_trace_name_still_refreshes_all_views(self):
        self.view.on_filter_change()

        self.view.refresh_all_views.assert_called_once_with()
        self.view.refresh_library_tree.assert_not_called()
        self.view.refresh_album_tree.assert_not_called()
        self.view.refresh_playlist_list.assert_not_called()
        self.view.refresh_playlist_tree.assert_not_called()


if __name__ == "__main__":
    unittest.main()
