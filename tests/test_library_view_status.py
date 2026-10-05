import unittest
from unittest.mock import Mock

from audio_player.library_views import LibraryViewsMixin


class LibraryViewStatusTests(unittest.TestCase):
    def setUp(self):
        self.view = LibraryViewsMixin()
        self.events = []
        self.view.update_status_strip = Mock(side_effect=lambda: self.events.append("status"))
        for name in ("refresh_library_tree", "refresh_album_tree", "refresh_playlist_list", "refresh_playlist_tree"):
            def refresh(_name=name):
                self.events.append(_name)
                self.view._update_view_status()
            setattr(self.view, name, Mock(side_effect=refresh))

    def test_full_refresh_updates_status_once_after_all_views(self):
        self.view.refresh_all_views()

        self.assertEqual(self.events, [
            "refresh_library_tree", "refresh_album_tree",
            "refresh_playlist_list", "refresh_playlist_tree", "status",
        ])
        self.view.update_status_strip.assert_called_once_with()

    def test_individual_view_refresh_updates_status_immediately(self):
        self.view.refresh_library_tree()

        self.assertEqual(self.events, ["refresh_library_tree", "status"])
        self.view.update_status_strip.assert_called_once_with()

    def test_nested_full_refresh_updates_status_once_at_outer_end(self):
        entered = False
        def refresh():
            nonlocal entered
            if not entered:
                entered = True
                self.view.refresh_all_views()
            self.view._update_view_status()
        self.view.refresh_library_tree.side_effect = refresh

        self.view.refresh_all_views()

        self.view.update_status_strip.assert_called_once_with()
        self.assertEqual(self.events[-1], "status")

    def test_failed_refresh_does_not_suppress_later_status_updates(self):
        self.view.refresh_album_tree.side_effect = RuntimeError("refresh failed")

        with self.assertRaisesRegex(RuntimeError, "refresh failed"):
            self.view.refresh_all_views()
        self.view.update_status_strip.assert_not_called()

        self.view.refresh_library_tree()
        self.view.update_status_strip.assert_called_once_with()
        self.view.refresh_album_tree.side_effect = self.view._update_view_status
        self.view.refresh_all_views()
        self.assertEqual(self.view.update_status_strip.call_count, 2)


if __name__ == "__main__":
    unittest.main()
