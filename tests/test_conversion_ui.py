import os
import queue
import tempfile
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from audio_player.conversion import CONVERSION_FORMATS, ConversionCancelled
from audio_player.conversion_ui import AudioConversionMixin, ConversionDialog, ConversionProgress


class ConversionWorkflowTests(unittest.TestCase):
    def test_selection_is_deduplicated_and_dialog_cancel_stops_work(self):
        app = AudioConversionMixin()
        app.root = Mock()
        app.library = Mock()
        app.library.get_song.side_effect = lambda song_id: song_id if song_id != "missing" else None
        app.library.song_path.side_effect = lambda song: Path(f"{song}.wav")
        with patch("audio_player.conversion_ui.ConversionDialog") as dialog:
            dialog.return_value.result = None
            with patch("audio_player.conversion_ui.ConversionProgress") as progress:
                app.convert_song_ids(["first", "first", "second", "missing"])
                dialog.assert_called_once_with(app.root, 2)
                progress.assert_not_called()

    def test_worker_continues_after_failure_and_keeps_completed_files_on_cancel(self):
        progress = ConversionProgress.__new__(ConversionProgress)
        progress.sources = [Path("first.wav"), Path("bad.wav"), Path("third.wav"), Path("fourth.wav")]
        progress.destination = Path("output")
        progress.output_format = CONVERSION_FORMATS[0]
        progress.cancel = threading.Event()
        progress.events = queue.Queue()

        def convert(source, destination, output_format, cancel):
            if source.name == "bad.wav":
                raise ValueError("Invalid audio")
            if source.name == "third.wav":
                cancel.set()
                raise ConversionCancelled()
            return destination / source.name

        with patch("audio_player.conversion_ui.convert_audio_file", side_effect=convert) as converter:
            progress.work()
        self.assertEqual(converter.call_count, 3)
        events = []
        while not progress.events.empty():
            events.append(progress.events.get_nowait())
        self.assertEqual(events[-1], ("done", [Path("output/first.wav")], ["bad.wav: Invalid audio"], True))


@unittest.skipUnless(os.environ.get("VAULT_TEST_GUI") == "1", "Set VAULT_TEST_GUI=1 for Tk checks")
class ConversionDialogTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def interact(self, callback):
        failures = []

        def handle():
            dialog = next(child for child in self.root.winfo_children() if isinstance(child, ConversionDialog))
            try:
                callback(dialog)
            except Exception as error:
                failures.append(error)
                dialog.cancel()

        self.root.after(100, handle)
        dialog = ConversionDialog(self.root, 2)
        if failures:
            raise failures[0]
        return dialog.result

    def test_choose_format_and_folder(self):
        def accept(dialog):
            dialog.format_box.current(3)
            with patch("audio_player.conversion_ui.filedialog.askdirectory", return_value=self.directory.name):
                dialog.choose_folder()
            dialog.ok()

        self.assertEqual(self.interact(accept), (Path(self.directory.name), CONVERSION_FORMATS[3]))

    def test_invalid_folder_is_rejected_and_cancel_returns_none(self):
        def reject(dialog):
            with patch("audio_player.conversion_ui.messagebox.showwarning") as warning:
                self.assertFalse(dialog.validate())
                warning.assert_called_once()
            dialog.cancel()

        self.assertIsNone(self.interact(reject))

    def test_progress_completion_reports_results_on_main_thread(self):
        destination = Path(self.directory.name)
        with patch("audio_player.conversion_ui.convert_audio_file", return_value=destination / "copy.wav"):
            with patch("audio_player.conversion_ui.messagebox.showinfo") as notification:
                progress = ConversionProgress(self.root, [Path("source.wav")], destination, CONVERSION_FORMATS[0])
                deadline = time.monotonic() + 3
                while progress.window.winfo_exists() and time.monotonic() < deadline:
                    self.root.update()
                    time.sleep(0.01)
                self.assertFalse(progress.window.winfo_exists())
                notification.assert_called_once()
                self.assertIn("Saved 1 of 1", notification.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
