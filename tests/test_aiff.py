import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from audio_player import audio_decode
from audio_player.bpm import analyze_bpm
from audio_player.spectral import build_spectrogram
from audio_player.waveform import build_waveform_peaks


@unittest.skipIf(audio_decode.np is None or audio_decode.sf is None, "NumPy and SoundFile are required")
class AiffTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.sample_rate = 44100
        sample_times = audio_decode.np.arange(self.sample_rate) / self.sample_rate
        self.signal = 0.25 * audio_decode.np.sin(2 * audio_decode.np.pi * 440 * sample_times)
        self.stereo = audio_decode.np.column_stack((self.signal, self.signal * 0.5))

    def write_audio(self, filename, samples=None, subtype="PCM_16", file_format="AIFF"):
        path = self.root / filename
        audio_decode.sf.write(
            path, self.stereo if samples is None else samples, self.sample_rate,
            format=file_format, subtype=subtype,
        )
        return path

    def test_decodes_real_aiff_files_with_both_extensions_and_sample_widths(self):
        for suffix in (".aif", ".aiff", ".AIF", ".AIFF"):
            for subtype in ("PCM_16", "PCM_24"):
                with self.subTest(suffix=suffix, subtype=subtype):
                    path = self.write_audio(f"Track{suffix}", subtype=subtype)
                    sample_rate, samples = audio_decode.read_mono_samples(path, max_seconds=0.25)

                    self.assertEqual(sample_rate, self.sample_rate)
                    self.assertEqual(samples.size, self.sample_rate // 4)
                    audio_decode.np.testing.assert_allclose(
                        samples, self.signal[:samples.size] * 0.75, atol=1 / 32768,
                    )

    @unittest.skipUnless(sys.platform == "darwin", "afconvert is available on macOS")
    def test_aiff_decode_falls_back_to_afconvert_without_soundfile(self):
        for suffix in (".aif", ".aiff"):
            with self.subTest(suffix=suffix):
                path = self.write_audio(f"Fallback{suffix}")
                with patch("audio_player.audio_decode.sf", None):
                    sample_rate, samples = audio_decode.read_mono_samples(path)

                self.assertEqual(sample_rate, self.sample_rate)
                audio_decode.np.testing.assert_allclose(samples, self.signal * 0.75, atol=2 / 32768)

    def test_aiff_waveform_spectrogram_and_bpm_match_wav(self):
        samples = audio_decode.np.zeros(self.sample_rate * 12)
        beat_times = audio_decode.np.arange(self.sample_rate // 10) / self.sample_rate
        beat = 0.5 * audio_decode.np.sin(2 * audio_decode.np.pi * 440 * beat_times)
        beat *= audio_decode.np.exp(-beat_times * 40)
        for start in range(0, samples.size - beat.size, self.sample_rate // 2):
            samples[start:start + beat.size] = beat
        aiff_path = self.write_audio("Beat.aiff", samples)
        wav_path = self.write_audio("Beat.wav", samples, file_format="WAV")

        self.assertEqual(build_waveform_peaks(aiff_path), build_waveform_peaks(wav_path))
        aiff_spectrogram = build_spectrogram(aiff_path)
        wav_spectrogram = build_spectrogram(wav_path)
        self.assertIsNotNone(aiff_spectrogram)
        self.assertIsNotNone(wav_spectrogram)
        audio_decode.np.testing.assert_array_equal(aiff_spectrogram.values, wav_spectrogram.values)
        aiff_bpm = analyze_bpm(aiff_path)
        self.assertIsNotNone(aiff_bpm)
        self.assertEqual(aiff_bpm, analyze_bpm(wav_path))

    @unittest.skipUnless(
        sys.platform == "darwin" and os.environ.get("VAULT_TEST_AUDIO") == "1",
        "Set VAULT_TEST_AUDIO=1 on macOS to test native audio playback",
    )
    def test_native_backend_plays_real_aiff_and_advances(self):
        from audio_player.app import AudioPlayerApp
        from audio_player.playback import NSSoundBackend

        player = NSSoundBackend()
        self.addCleanup(player.stop)
        for suffix in (".aif", ".aiff", ".AIF", ".AIFF"):
            for subtype in ("PCM_16", "PCM_24"):
                with self.subTest(suffix=suffix, subtype=subtype):
                    path = self.write_audio(
                        f"Playback{suffix}", audio_decode.np.zeros((self.sample_rate, 2)), subtype=subtype,
                    )
                    self.assertTrue(AudioPlayerApp.is_supported_audio_file(None, path))
                    self.assertTrue(AudioPlayerApp.directory_has_supported_audio(None, self.root))
                    player.play(path)
                    self.assertAlmostEqual(player.duration(), 1.0, places=2)
                    deadline = time.monotonic() + 0.5
                    while player.current_time() <= 0 and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(player.is_playing())
                    self.assertGreater(player.current_time(), 0)
                    player.stop()


if __name__ == "__main__":
    unittest.main()
