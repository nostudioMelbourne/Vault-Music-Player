import importlib.util
import math
import struct
import unittest
from dataclasses import replace

from audio_player.cdj_formats import (
    ExportTrack, analysis_directory, build_analysis_files, build_device_library,
    encode_device_string, inspect_analysis_file, tempo_units,
)


class CdjFormatTests(unittest.TestCase):
    def setUp(self):
        self.track = ExportTrack(1, "Probe", "Artist", "Album", "/Contents/Probe.wav", 127.5, 16.0, 1000)

    def test_analysis_path_matches_published_reference_vectors(self):
        cases = (
            ("/Contents/Leo Portela/Bon Vibrant - Leo Portela.flac", "P00E/000281CE"),
            ("/Contents/Daniela Cast/Jazzy - Daniela Cast.flac", "P00A/0000CC9C"),
            ("/Contents/Huerta/Tatra Motokov - Huerta.flac", "P028/0000F098"),
        )
        for path, expected in cases:
            with self.subTest(path=path):
                self.assertEqual(analysis_directory(path), "/PIONEER/USBANLZ/" + expected)

    def test_bpm_keeps_hundredths_and_rejects_unrepresentable_values(self):
        self.assertEqual(tempo_units(127.5), 12750)
        self.assertEqual(tempo_units(127.505), 12751)
        self.assertEqual(tempo_units(655.35), 65535)
        for bpm in (0, -1, math.inf, math.nan, 655.36, 0.001):
            with self.subTest(bpm=bpm), self.assertRaises(ValueError):
                tempo_units(bpm)

    def test_unsafe_or_non_normalized_audio_paths_are_rejected(self):
        for path in ("relative.wav", "/Other/probe.wav", "/Contents/../probe.wav", "/Contents//probe.wav", "/Contents/a\\b.wav", "/Contents/a\x00.wav"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                analysis_directory(path)

    def test_track_rejects_metadata_outside_proof_profile(self):
        for changes in (
            {"track_id": 0}, {"file_size": 2**32}, {"duration_seconds": math.nan},
            {"duration_seconds": 65536}, {"sample_rate": 96000}, {"sample_depth": 24},
            {"audio_path": "/Contents/Probe.flac"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.track, **changes)

    def test_device_strings_handle_ascii_boundaries_and_unicode(self):
        self.assertEqual(encode_device_string(""), b"\x03")
        self.assertEqual(encode_device_string("a" * 126)[0], 255)
        self.assertEqual(encode_device_string("a" * 127)[0], 0x40)
        unicode_text = "夜 🎵"
        encoded = encode_device_string(unicode_text)
        self.assertEqual(encoded[0], 0x90)
        self.assertEqual(struct.unpack_from("<H", encoded, 1)[0], len(encoded))
        self.assertEqual(encoded[4:].decode("utf-16-le"), unicode_text)
        with self.assertRaises(ValueError):
            encode_device_string("bad\x00text")

    def test_analysis_contains_exact_beats_and_waveform_dimensions(self):
        beat_times = (2000, 2471, 2941, 3412, 3882)
        files = build_analysis_files(self.track.audio_path, self.track.bpm, beat_times, [0.5] * 400, [0, 0.5, 1] * 800)
        dat_sections = {tag: (header, data) for tag, header, data in inspect_analysis_file(files[".DAT"])}
        self.assertEqual(dat_sections["PQTZ"][0], 24)
        beats = tuple(struct.iter_unpack(">HHI", dat_sections["PQTZ"][1][24:]))
        self.assertEqual([beat[0] for beat in beats], [1, 2, 3, 4, 1])
        self.assertEqual([beat[1] for beat in beats], [12750] * 5)
        self.assertEqual([beat[2] for beat in beats], list(beat_times))
        self.assertEqual(len(dat_sections["PWAV"][1]) - 20, 400)
        path_section = dat_sections["PPTH"][1]
        self.assertEqual(path_section[16:].decode("utf-16-be"), self.track.audio_path + "\x00")
        self.assertEqual(struct.unpack_from(">I", path_section, 12)[0], len(path_section) - 16)
        ext_sections = {tag: data for tag, _header, data in inspect_analysis_file(files[".EXT"])}
        self.assertEqual(struct.unpack_from(">I", ext_sections["PWV3"], 16)[0], 2400)
        self.assertEqual(len(ext_sections["PWV3"]) - 24, 2400)

    def test_analysis_rejects_invalid_grids_and_waveforms(self):
        for beat_times in ((), (500, 500), (500, 400), (-1, 100), (0, 2**32)):
            with self.subTest(beat_times=beat_times), self.assertRaises(ValueError):
                build_analysis_files(self.track.audio_path, 120, beat_times, [0.5] * 400, [0.5])
        for peaks in ([math.nan], [1.1], [-0.1], []):
            with self.subTest(peaks=peaks), self.assertRaises(ValueError):
                build_analysis_files(self.track.audio_path, 120, [0, 500], [0.5] * 400, peaks)
        with self.assertRaises(ValueError):
            build_analysis_files(self.track.audio_path, 120, [0, 500], [0.5] * 399, [0.5])

    def test_analysis_inspector_rejects_truncation_and_invalid_lengths(self):
        data = build_analysis_files(self.track.audio_path, 120, [0, 500], [0.5] * 400, [0.5])[".DAT"]
        invalid_tag_length = bytearray(data)
        struct.pack_into(">I", invalid_tag_length, 36, len(data))
        for malformed in (b"", data[:-1], bytes(invalid_tag_length)):
            with self.subTest(length=len(malformed)), self.assertRaises(ValueError):
                inspect_analysis_file(malformed)

    def test_database_rejects_empty_playlists_and_duplicate_ids_or_paths(self):
        for tracks, name in (([], "Probe"), ([self.track], " "), ([self.track, self.track], "Probe"), ([self.track, replace(self.track, track_id=2)], "Probe")):
            with self.subTest(name=name, count=len(tracks)), self.assertRaises(ValueError):
                build_device_library(tracks, name)

    def test_database_sequences_links_and_row_space_are_consistent(self):
        tracks = [replace(self.track, track_id=index, audio_path=f"/Contents/Track-{index}.wav") for index in range(1, 100)]
        data = build_device_library(tracks, "Probe")
        page_size, table_count, next_unused = struct.unpack_from("<III", data, 4)
        sequence = struct.unpack_from("<I", data, 20)[0]
        self.assertEqual(len(data), next_unused * page_size)
        self.assertEqual(table_count, 20)
        for table_index in range(table_count):
            table_type, candidate, first, last = struct.unpack_from("<IIII", data, 28 + table_index * 16)
            self.assertLess(candidate, next_unused)
            page_index = first
            visited = set()
            while True:
                self.assertNotIn(page_index, visited)
                visited.add(page_index)
                page = data[page_index * page_size:(page_index + 1) * page_size]
                self.assertEqual(struct.unpack_from("<II", page, 4), (page_index, table_type))
                self.assertLess(struct.unpack_from("<I", page, 16)[0], sequence)
                if not page[27] & 0x40:
                    count = page[24] + ((page[25] & 1) << 8)
                    free, used = struct.unpack_from("<HH", page, 28)
                    self.assertEqual(40 + free + used + math.ceil(count / 16) * 36, page_size)
                if page_index == last:
                    break
                page_index = struct.unpack_from("<I", page, 12)[0]

    @unittest.skipUnless(importlib.util.find_spec("rekordbox_pdb"), "Independent database parser is not installed")
    def test_independent_reader_decodes_unicode_and_multiple_database_pages(self):
        from rekordbox_pdb import Database

        tracks = [
            replace(self.track, track_id=index, title=f"夜 🎵 {index}", artist="演奏者", album="夜のアルバム", audio_path=f"/Contents/夜 🎵 {index}.wav")
            for index in range(1, 100)
        ]
        database = Database.from_bytes(build_device_library(tracks, "夜のプレイリスト"))
        self.assertEqual([track.title for track in database.tracks], [track.title for track in tracks])
        self.assertEqual([track.file_path for track in database.tracks], [track.audio_path for track in tracks])
        self.assertEqual([track.tempo for track in database.tracks], [12750] * 99)
        self.assertEqual([entry.track_id for entry in database.playlist_entries], list(range(1, 100)))
        self.assertEqual([entry.entry_index for entry in database.playlist_entries], list(range(1, 100)))
        self.assertEqual(database.playlist_tree[0].name, "夜のプレイリスト")
        self.assertEqual(database.artists[0].name, "演奏者")
        self.assertEqual(database.albums[0].name, "夜のアルバム")


if __name__ == "__main__":
    unittest.main()
