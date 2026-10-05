import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from audio_player.theme import ThemeMixin


class ThemeSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.data_dir = Path(self.temporary_directory.name) / "app-data"
        self.settings_db = self.data_dir / "settings.json"
        self.theme = ThemeMixin()
        self.theme.paths = SimpleNamespace(
            app_support_dir=self.data_dir, settings_db=self.settings_db,
        )

    def write_settings(self, text):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.settings_db.write_text(text, encoding="utf-8")

    def test_missing_malformed_or_unrecognized_settings_fall_back_to_light(self):
        self.assertEqual(self.theme.load_theme_mode(), "light")
        for text in ("not json", "[]", "null", "{}", '{"theme": "unknown"}'):
            with self.subTest(text=text):
                self.write_settings(text)
                self.assertEqual(self.theme.load_theme_mode(), "light")

    def test_load_accepts_both_supported_themes(self):
        for mode in ("light", "dark"):
            with self.subTest(mode=mode):
                self.write_settings(json.dumps({"theme": mode}))
                self.assertEqual(self.theme.load_theme_mode(), mode)

    def test_save_creates_storage_and_round_trips_the_theme(self):
        self.theme.theme_mode = "dark"

        self.theme.save_theme_mode()

        self.assertEqual(self.theme.load_theme_mode(), "dark")
        self.assertEqual(json.loads(self.settings_db.read_text(encoding="utf-8")), {"theme": "dark"})

    def test_save_preserves_unrelated_settings(self):
        self.write_settings('{"theme": "light", "volume": 0.5, "window": [1180, 760]}')
        self.theme.theme_mode = "dark"

        self.theme.save_theme_mode()

        self.assertEqual(json.loads(self.settings_db.read_text(encoding="utf-8")), {
            "theme": "dark", "volume": 0.5, "window": [1180, 760],
        })

    def test_failed_save_preserves_existing_settings(self):
        original = '{"theme": "light", "volume": 0.5}'
        self.write_settings(original)
        self.theme.theme_mode = "dark"
        with patch("audio_player.theme.write_json_atomic", side_effect=OSError("disk full")):
            self.theme.save_theme_mode()

        self.assertEqual(self.settings_db.read_text(encoding="utf-8"), original)

    def test_theme_row_tags_keep_other_tags_without_duplicate_theme_tags(self):
        self.assertEqual(
            self.theme.theme_tree_tags(("playing", "theme-row", "selected", "theme-row")),
            ("theme-row", "playing", "selected"),
        )


if __name__ == "__main__":
    unittest.main()
