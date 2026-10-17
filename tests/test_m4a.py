import os
import subprocess
import sys
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from audio_player import audio_decode
from audio_player.bpm import analyze_bpm
from audio_player.spectral import build_spectrogram
from audio_player.waveform import build_waveform_peaks


@unittest.skipUnless(sys.platform == "darwin" and audio_decode.np is not None, "macOS afconvert and NumPy are required")
class M4aTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.sample_rate = 44100
        samples = audio_decode.np.zeros(self.sample_rate * 12)
        beat_times = audio_decode.np.arange(self.sample_rate // 10) / self.sample_rate
        beat = 0.5 * audio_decode.np.sin(2 * audio_decode.np.pi * 440 * beat_times)
        beat *= audio_decode.np.exp(-beat_times * 40)
        for start in range(0, samples.size - beat.size, self.sample_rate // 2):
            samples[start:start + beat.size] = beat
        stereo = audio_decode.np.column_stack((samples, samples * 0.5))
        self.pcm = audio_decode.np.round(stereo * 32767).astype("<i2")
        self.source = self.root / "Beat.wav"
        self.write_wav(self.source, self.pcm)

    def write_wav(self, path, pcm):
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(2)
            audio.setsampwidth(2)
            audio.setframerate(self.sample_rate)
            audio.writeframes(pcm.tobytes())

    def encode_m4a(self, filename, codec, source=None):
        path = self.root / filename
        subprocess.run(
            ["/usr/bin/afconvert", str(source or self.source), str(path), "-f", "m4af", "-d", codec],
            check=True, capture_output=True,
        )
        return path

    def test_decodes_real_aac_and_lossless_m4a_with_both_extension_cases(self):
        for codec in ("aac", "alac"):
            for suffix in (".m4a", ".M4A"):
                with self.subTest(codec=codec, suffix=suffix):
                    path = self.encode_m4a(f"Decode-{codec}{suffix}", codec)
                    with patch("audio_player.audio_decode.sf", None):
                        decoded = audio_decode.read_mono_samples(path, max_seconds=0.25)
                    self.assertIsNotNone(decoded)
                    sample_rate, samples = decoded
                    self.assertEqual(sample_rate, self.sample_rate)
                    self.assertEqual(samples.size, self.sample_rate // 4)
                    self.assertGreater(float(audio_decode.np.max(audio_decode.np.abs(samples))), 0.1)
                    if codec == "alac":
                        expected = self.pcm[:samples.size].astype("float32").mean(axis=1) / 32768
                        audio_decode.np.testing.assert_array_equal(samples, expected)

    def test_m4a_waveform_spectrogram_and_bpm_are_available(self):
        expected_peaks = build_waveform_peaks(self.source)
        expected_spectrogram = build_spectrogram(self.source)
        expected_bpm = analyze_bpm(self.source)
        self.assertIsNotNone(expected_bpm)
        for codec in ("aac", "alac"):
            with self.subTest(codec=codec):
                path = self.encode_m4a(f"Analysis-{codec}.m4a", codec)
                peaks = build_waveform_peaks(path)
                spectrogram = build_spectrogram(path)
                bpm = analyze_bpm(path)
                self.assertEqual(len(peaks), 256)
                self.assertGreater(max(peaks), 0)
                self.assertIsNotNone(spectrogram)
                self.assertIsNotNone(bpm)
                self.assertAlmostEqual(bpm, expected_bpm, delta=1)
                if codec == "alac":
                    self.assertEqual(peaks, expected_peaks)
                    audio_decode.np.testing.assert_array_equal(spectrogram.values, expected_spectrogram.values)

    def test_invalid_m4a_has_no_decoded_audio(self):
        path = self.root / "Invalid.m4a"
        path.write_bytes(b"not an audio file")

        self.assertIsNone(audio_decode.read_mono_samples(path))

    @unittest.skipUnless(os.environ.get("VAULT_TEST_AUDIO") == "1", "Set VAULT_TEST_AUDIO=1 to test native audio playback")
    def test_native_backend_plays_aac_and_lossless_m4a_and_advances(self):
        from audio_player.app import AudioPlayerApp
        from audio_player.playback import NSSoundBackend

        silent_source = self.root / "Silent.wav"
        self.write_wav(silent_source, audio_decode.np.zeros((self.sample_rate * 2, 2), dtype="<i2"))
        player = NSSoundBackend()
        self.addCleanup(player.stop)
        for codec in ("aac", "alac"):
            for suffix in (".m4a", ".M4A"):
                with self.subTest(codec=codec, suffix=suffix):
                    path = self.encode_m4a(f"Playback-{codec}{suffix}", codec, silent_source)
                    self.assertTrue(AudioPlayerApp.is_supported_audio_file(None, path))
                    self.assertTrue(AudioPlayerApp.directory_has_supported_audio(None, self.root))
                    player.play(path)
                    self.assertAlmostEqual(player.duration(), 2.0, delta=0.1)
                    deadline = time.monotonic() + 0.5
                    while player.current_time() <= 0 and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(player.is_playing())
                    self.assertGreater(player.current_time(), 0)
                    player.stop()


if __name__ == "__main__":
    unittest.main()
