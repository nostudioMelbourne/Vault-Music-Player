import math
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from audio_player.conversion import (
    CONVERSION_FORMATS, ConversionCancelled, convert_audio_file, publish_copy, run_encoder,
)


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.source = self.directory / "Track.wav"
        self.destination = self.directory / "output"
        self.destination.mkdir()
        self.audio = b"".join(
            struct.pack("<hh", int(4000 * math.sin(index * 2 * math.pi * 440 / 48000)), 1000)
            for index in range(12000)
        )
        with wave.open(str(self.source), "wb") as output:
            output.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
            output.writeframes(self.audio)

    def fake_encoder(self, command, cancel):
        shutil.copyfile(command[1], command[2])

    def test_same_folder_preserves_source_and_existing_outputs(self):
        original = self.source.read_bytes()
        existing = self.directory / "Track 2.wav"
        existing.write_bytes(b"Keep this file")
        with patch("audio_player.conversion.run_encoder", side_effect=self.fake_encoder):
            output = convert_audio_file(self.source, self.directory, CONVERSION_FORMATS[0])
        self.assertEqual(output.name, "Track 3.wav")
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(existing.read_bytes(), b"Keep this file")
        self.assertEqual(output.read_bytes(), original)
        self.assertFalse(list(self.directory.glob(".vault-convert-*")))

    def test_failure_and_empty_output_leave_no_partial_files(self):
        for error in (ValueError("Invalid audio"), FileNotFoundError("No encoder"), None):
            with self.subTest(error=error):
                with patch("audio_player.conversion.run_encoder", side_effect=error):
                    with self.assertRaises((OSError, ValueError)):
                        convert_audio_file(self.source, self.destination, CONVERSION_FORMATS[0])
                self.assertEqual(list(self.destination.iterdir()), [])

    def test_invalid_format_source_and_folder_are_rejected(self):
        cases = (
            (self.source, self.destination, "MP3", ValueError),
            (self.directory / "missing.wav", self.destination, CONVERSION_FORMATS[0], FileNotFoundError),
            (self.source, self.directory / "missing", CONVERSION_FORMATS[0], NotADirectoryError),
        )
        for source, destination, output_format, error in cases:
            with self.subTest(error=error):
                with self.assertRaises(error):
                    convert_audio_file(source, destination, output_format)

    def test_cancel_before_or_after_encoding_removes_staging(self):
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(ConversionCancelled):
            convert_audio_file(self.source, self.destination, CONVERSION_FORMATS[0], cancel)
        cancel.clear()

        def cancel_after_encoding(command, event):
            self.fake_encoder(command, event)
            event.set()

        with patch("audio_player.conversion.run_encoder", side_effect=cancel_after_encoding):
            with self.assertRaises(ConversionCancelled):
                convert_audio_file(self.source, self.destination, CONVERSION_FORMATS[0], cancel)
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_cancel_during_copy_removes_partial_output(self):
        class CancelDuringCopy:
            def __init__(self):
                self.calls = 0

            def is_set(self):
                self.calls += 1
                return self.calls >= 3

        with self.assertRaises(ConversionCancelled):
            publish_copy(self.source, self.destination, "Track", ".wav", CancelDuringCopy())
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_cancel_terminates_running_encoder(self):
        cancel = threading.Event()
        processes = []

        launch_process = subprocess.Popen

        def record_process(*arguments, **options):
            process = launch_process(*arguments, **options)
            processes.append(process)
            timer = threading.Timer(0.2, cancel.set)
            timer.start()
            self.addCleanup(timer.cancel)
            return process

        with patch("audio_player.conversion.subprocess.Popen", side_effect=record_process):
            with self.assertRaises(ConversionCancelled):
                run_encoder([sys.executable, "-c", "import time; time.sleep(60)"], cancel)
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS afconvert")
    def test_real_formats_round_trip_and_preserve_source(self):
        original = self.source.read_bytes()
        for output_format in CONVERSION_FORMATS:
            with self.subTest(format=output_format.label):
                output = convert_audio_file(self.source, self.destination, output_format)
                self.assertEqual(output.suffix, output_format.suffix)
                decoded = self.directory / "decoded.wav"
                subprocess.run([
                    "/usr/bin/afconvert", str(output), str(decoded), "-f", "WAVE", "-d", "LEI16",
                ], check=True, capture_output=True)
                with wave.open(str(decoded), "rb") as audio:
                    self.assertEqual(audio.getframerate(), 48000)
                    self.assertEqual(audio.getnchannels(), 2)
                    self.assertAlmostEqual(audio.getnframes() / 48000, 0.25, delta=0.05)
                    frames = audio.readframes(audio.getnframes())
                self.assertTrue(any(frames))
                if output_format.data_format != "aac":
                    self.assertEqual(frames, self.audio)
                self.assertEqual(self.source.read_bytes(), original)
                self.assertFalse(list(self.destination.glob(".vault-convert-*")))

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS afconvert")
    def test_converted_formats_can_be_used_as_conversion_inputs(self):
        for output_format in CONVERSION_FORMATS:
            with self.subTest(format=output_format.label):
                encoded = convert_audio_file(self.source, self.destination, output_format)
                decoded = convert_audio_file(encoded, self.destination, CONVERSION_FORMATS[1])
                with wave.open(str(decoded), "rb") as audio:
                    self.assertEqual(audio.getsampwidth(), 3)
                    self.assertEqual(audio.getnchannels(), 2)
                    self.assertEqual(audio.getframerate(), 48000)
                    self.assertAlmostEqual(audio.getnframes() / 48000, 0.25, delta=0.05)

    @unittest.skipUnless(sys.platform == "darwin", "Requires macOS afconvert")
    def test_real_malformed_audio_fails_cleanly(self):
        self.source.write_bytes(b"Not audio")
        with self.assertRaises(ValueError):
            convert_audio_file(self.source, self.destination, CONVERSION_FORMATS[0])
        self.assertEqual(list(self.destination.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
