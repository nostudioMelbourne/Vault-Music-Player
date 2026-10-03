import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from audio_player.utils import write_json_atomic


class WriteJsonAtomicTests(unittest.TestCase):
    def test_replaces_existing_json_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "library.json"
            path.write_text('{"old": true}', encoding="utf-8")

            write_json_atomic(path, {"songs": ["one", "two"]})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"songs": ["one", "two"]})
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_failed_serialization_preserves_existing_file_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "library.json"
            original_contents = '{"old": true}'
            path.write_text(original_contents, encoding="utf-8")

            with patch("audio_player.utils.json.dump", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    write_json_atomic(path, {"songs": ["new"]})

            self.assertEqual(path.read_text(encoding="utf-8"), original_contents)
            self.assertEqual(list(Path(directory).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
