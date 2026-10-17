import hashlib
import importlib.util
import io
import json
import math
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

from audio_player.cdj_probe import PROBE_PLAYLIST, create_probe_export


class CdjProbeTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.output = self.root / "probe"

    def test_bundle_contains_verifiable_audio_analysis_and_explicit_probe_status(self):
        manifest = create_probe_export(self.output)
        self.assertEqual(json.loads((self.output / "vault-cdj-probe.json").read_text()), manifest)
        self.assertFalse(manifest["hardware_verified"])
        self.assertFalse(manifest["onelibrary_included"])
        self.assertEqual(manifest["library_format"], "Device Library")
        self.assertEqual(manifest["playlist"], PROBE_PLAYLIST)
        self.assertEqual([track["bpm"] for track in manifest["tracks"]], [120.0, 127.5, 90.0])
        self.assertEqual(len(manifest["sha256"]), 10)
        for relative_path, checksum in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256((self.output / relative_path).read_bytes()).hexdigest(), checksum)
        for track in manifest["tracks"]:
            with wave.open(str(self.output / track["audio_path"].lstrip("/"))) as audio:
                self.assertEqual((audio.getnchannels(), audio.getsampwidth(), audio.getframerate()), (2, 2, 44100))
                samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").reshape(-1, 2)[:, 0]
                self.assertAlmostEqual(len(samples) / 44100, track["duration_seconds"])
            first_beat_frame = track["first_beat_ms"] * 44100 // 1000
            self.assertFalse(np.any(samples[:first_beat_frame]))
            for index, time_ms in enumerate(track["beat_times_ms"]):
                frame = round(time_ms * 44100 / 1000)
                self.assertGreater(np.max(np.abs(samples[frame:frame + 441])), 1000)
                expected_ms = track["first_beat_ms"] + index * 60000 / track["bpm"]
                self.assertLessEqual(abs(time_ms - expected_ms), 0.5)
            self.assertEqual(len(track["beat_times_ms"]), 32)
            self.assertEqual(track["detail_waveform_entries"], math.ceil(track["duration_seconds"] * 150))

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        existing = self.output / "existing.txt"
        existing.write_text("keep me", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            create_probe_export(self.output)
        self.assertEqual(existing.read_text(), "keep me")
        self.assertEqual(list(self.output.iterdir()), [existing])

    def test_dangling_symlinks_and_missing_parent_are_rejected(self):
        self.output.symlink_to(self.root / "missing")
        with self.assertRaises(FileExistsError):
            create_probe_export(self.output)
        with self.assertRaises(FileNotFoundError):
            create_probe_export(self.root / "no-parent" / "probe")

    def test_failed_preparation_does_not_publish_or_leave_staging_files(self):
        with patch("audio_player.cdj_probe._write_wav", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                create_probe_export(self.output)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_failed_publication_rolls_back_only_files_created_by_the_probe(self):
        original_rename = Path.rename

        def fail_database_publication(source, target):
            if source.name == "PIONEER":
                (self.output / "unrelated.txt").write_text("preserve this concurrent file", encoding="utf-8")
                raise OSError("USB disconnected")
            return original_rename(source, target)

        with patch.object(Path, "rename", fail_database_publication):
            with self.assertRaisesRegex(OSError, "USB disconnected"):
                create_probe_export(self.output)
        self.assertEqual([path.name for path in self.output.iterdir()], ["unrelated.txt"])
        self.assertEqual((self.output / "unrelated.txt").read_text(), "preserve this concurrent file")
        self.assertFalse(any(path.name.startswith(".vault-cdj-probe-") for path in self.root.iterdir()))

    @unittest.skipUnless(importlib.util.find_spec("rekordbox_pdb"), "Independent database parser is not installed")
    def test_independent_database_reader_matches_manifest_and_existing_audio(self):
        from rekordbox_pdb import Database

        manifest = create_probe_export(self.output)
        database = Database.from_file(self.output / "PIONEER" / "rekordbox" / "export.pdb")
        self.assertEqual([track.id for track in database.tracks], [track["track_id"] for track in manifest["tracks"]])
        self.assertEqual(database.playlist_tree[0].name, PROBE_PLAYLIST)
        self.assertEqual([entry.track_id for entry in database.playlist_entries], [1, 2, 3])
        for actual, expected in zip(database.tracks, manifest["tracks"]):
            self.assertEqual(actual.tempo, round(expected["bpm"] * 100))
            self.assertEqual(actual.title, expected["title"])
            self.assertEqual(actual.analyze_path, expected["analysis_path"])
            audio_path = self.output / actual.file_path.lstrip("/")
            self.assertTrue(audio_path.is_file())
            self.assertEqual(actual.file_size, audio_path.stat().st_size)
            self.assertTrue((self.output / actual.analyze_path.lstrip("/")).is_file())

    @unittest.skipUnless(
        importlib.util.find_spec("pyrekordbox") and importlib.util.find_spec("construct"),
        "Independent analysis parser is not installed",
    )
    def test_independent_analysis_reader_matches_paths_beats_and_waveforms(self):
        package = importlib.util.find_spec("pyrekordbox")
        source_path = Path(next(iter(package.submodule_search_locations))) / "anlz" / "structs.py"
        specification = importlib.util.spec_from_file_location("vault_independent_anlz_structs", source_path)
        structures = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(structures)
        manifest = create_probe_export(self.output)
        for track in manifest["tracks"]:
            dat_path = self.output / track["analysis_path"].lstrip("/")
            for path in (dat_path, dat_path.with_suffix(".EXT")):
                with self.subTest(path=path.name):
                    stream = io.BytesIO(path.read_bytes())
                    header = structures.AnlzFileHeader.parse_stream(stream)
                    self.assertEqual(header.type, "PMAI")
                    self.assertEqual(header.len_file, len(stream.getvalue()))
                    self.assertEqual(header.len_header, stream.tell())
                    tags = {}
                    while stream.tell() < header.len_file:
                        start = stream.tell()
                        section = structures.AnlzTag.parse_stream(stream)
                        self.assertEqual(stream.tell() - start, section.len_tag)
                        tags.setdefault(section.type, []).append(section.content)
                    self.assertEqual(tags["PPTH"][0].path, track["audio_path"])
                    self.assertEqual([cue.count for cue in tags["PCOB"]], [0, 0])
                    if path.suffix == ".DAT":
                        grid = tags["PQTZ"][0]
                        self.assertEqual([beat.time for beat in grid.entries], track["beat_times_ms"])
                        self.assertEqual([beat.tempo for beat in grid.entries], [round(track["bpm"] * 100)] * 32)
                        self.assertEqual([beat.beat for beat in grid.entries], [1, 2, 3, 4] * 8)
                        self.assertEqual(len(tags["PWAV"][0].entries), 400)
                        self.assertTrue(any(tags["PWAV"][0].entries))
                    else:
                        detail = tags["PWV3"][0]
                        self.assertEqual(len(detail.entries), track["detail_waveform_entries"])
                        self.assertTrue(any(detail.entries))


if __name__ == "__main__":
    unittest.main()
