import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock


@unittest.skipUnless(sys.platform == "darwin", "Vault's app uses macOS AppKit")
class PlaylistDragDropTests(unittest.TestCase):
    def setUp(self):
        from audio_player.app import AudioPlayerApp

        self.app = AudioPlayerApp.__new__(AudioPlayerApp)
        self.app.root = Mock()
        self.app.library_tree = Mock()
        self.app.album_tree = Mock()
        self.app.album_song_tree = Mock()
        self.app.playlist_list = Mock()
        self.app.playlist_tree = Mock()
        self.app.playlist_names = ["Warmup"]
        self.app.status_label = Mock()
        self.app.status_label.cget.return_value = "Ready"
        self.app.get_selected_playlist_name = Mock(return_value="Warmup")
        self.app.get_selected_library_song_ids = Mock(return_value=["first", "second"])
        self.app.select_tree_item_for_event = Mock(return_value="first")
        self.app.select_playlist_by_name = Mock()
        self.app.refresh_playlist_tree = Mock()
        self.app.add_song_ids_to_playlist_named = Mock(return_value=2)
        self.app.library = Mock()
        self.app.drag_origin = None
        self.app.drag_payload = None
        self.app.drag_target_playlist = None
        self.app.playlist_list.winfo_rooty.return_value = 100
        self.app.playlist_list.nearest.return_value = 0
        self.app.playlist_list.bbox.return_value = (0, 0, 200, 20)
        self.press = SimpleNamespace(widget=self.app.library_tree, x=10, y=10, x_root=10, y_root=10)
        self.drop = SimpleNamespace(widget=self.app.library_tree, x=300, y=110, x_root=300, y_root=110)

    def test_drop_on_playlist_track_area_targets_selected_playlist(self):
        self.app.root.winfo_containing.return_value = self.app.playlist_tree

        self.assertEqual(self.app.playlist_name_at_pointer(300, 110), "Warmup")
        self.app.root.winfo_containing.assert_called_once_with(300, 110)
        self.app.root.winfo_pointerx.assert_not_called()

    def test_playlist_list_rows_are_targets_but_blank_space_is_not(self):
        self.app.root.winfo_containing.return_value = self.app.playlist_list

        self.assertEqual(self.app.playlist_name_at_pointer(300, 110), "Warmup")
        self.assertIsNone(self.app.playlist_name_at_pointer(300, 150))

    def test_track_area_requires_a_selected_playlist(self):
        self.app.root.winfo_containing.return_value = self.app.playlist_tree
        self.app.get_selected_playlist_name.return_value = None

        self.assertIsNone(self.app.playlist_name_at_pointer(300, 110))

    def test_drag_snapshots_selection_and_adds_all_originally_selected_songs(self):
        self.app.root.winfo_containing.return_value = self.app.playlist_tree
        self.app.on_drag_press(self.press)
        self.app.get_selected_library_song_ids.return_value = ["second"]

        self.assertEqual(self.app.on_drag_motion(self.drop), "break")
        self.assertEqual(self.app.on_drag_release(self.drop), "break")

        self.app.add_song_ids_to_playlist_named.assert_called_once_with("Warmup", ["first", "second"])
        self.assertIsNone(self.app.drag_origin)
        self.assertIsNone(self.app.drag_payload)

    def test_click_without_drag_does_not_add_tracks(self):
        self.app.on_drag_press(self.press)
        tiny_motion = SimpleNamespace(x_root=12, y_root=12)

        self.assertIsNone(self.app.on_drag_motion(tiny_motion))
        self.assertIsNone(self.app.on_drag_release(self.press))
        self.app.add_song_ids_to_playlist_named.assert_not_called()

    def test_cancelled_drop_restores_original_playlist_and_status(self):
        self.app.root.winfo_containing.return_value = self.app.playlist_list
        self.app.on_drag_press(self.press)
        self.app.on_drag_motion(self.drop)
        self.app.root.winfo_containing.return_value = self.app.library_tree

        self.assertEqual(self.app.on_drag_release(self.drop), "break")
        self.app.add_song_ids_to_playlist_named.assert_not_called()
        self.app.status_label.config.assert_called_with(text="Ready")
        self.app.select_playlist_by_name.assert_called_with("Warmup")

    def test_duplicate_drop_reports_existing_membership(self):
        self.app.root.winfo_containing.return_value = self.app.playlist_tree
        self.app.add_song_ids_to_playlist_named.return_value = 0
        self.app.on_drag_press(self.press)
        self.app.on_drag_motion(self.drop)

        self.assertEqual(self.app.on_drag_release(self.drop), "break")
        self.app.status_label.config.assert_called_with(text="2 songs already in Warmup")


if __name__ == "__main__":
    unittest.main()
