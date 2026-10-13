import math
import struct
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import PurePosixPath


PAGE_SIZE = 4096
PAGE_HEADER_SIZE = 40
TABLE_COUNT = 20
ROW_GROUP_SIZE = 36


def tempo_units(bpm):
    if not math.isfinite(bpm) or not 0 < bpm <= 655.35:
        raise ValueError("BPM must be positive and fit the CDJ beatgrid field.")
    value = int((Decimal(str(bpm)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if value == 0:
        raise ValueError("BPM is below the CDJ beatgrid precision.")
    return value


def validate_audio_path(audio_path):
    if not isinstance(audio_path, str) or "\x00" in audio_path or "\\" in audio_path:
        raise ValueError("Audio paths must be NUL-free USB-relative POSIX paths.")
    path = PurePosixPath(audio_path)
    if not audio_path.startswith("/Contents/") or ".." in path.parts or str(path) != audio_path:
        raise ValueError("Audio paths must be normalized paths under /Contents/.")


def analysis_directory(audio_path):
    validate_audio_path(audio_path)
    path_hash = 0
    for (code_unit,) in struct.iter_unpack("<H", audio_path.encode("utf-16-le")):
        first_round = (path_hash * 0x5BC9 + code_unit) & 0xFFFFFFFF
        path_hash = (first_round * 0x93B5 + code_unit) & 0xFFFFFFFF
    path_hash %= 200003
    directory_number = sum(((path_hash >> bit) & 1) << index for index, bit in enumerate((0, 2, 6, 7, 9, 13, 16)))
    return f"/PIONEER/USBANLZ/P{directory_number:03X}/{path_hash:08X}"


@dataclass(frozen=True)
class ExportTrack:
    track_id: int
    title: str
    artist: str
    album: str
    audio_path: str
    bpm: float
    duration_seconds: float
    file_size: int
    sample_rate: int = 44100
    sample_depth: int = 16

    def __post_init__(self):
        validate_audio_path(self.audio_path)
        tempo_units(self.bpm)
        if not 0 < self.track_id < 2**32 or not 0 < self.file_size < 2**32:
            raise ValueError("Track IDs and file sizes must fit the database fields.")
        if not math.isfinite(self.duration_seconds) or not 0 < self.duration_seconds <= 65535:
            raise ValueError("Track duration must fit the database field.")
        if self.sample_rate != 44100 or self.sample_depth != 16 or PurePosixPath(self.audio_path).suffix != ".wav":
            raise ValueError("The proof writer only supports 44.1 kHz, 16-bit PCM WAV.")

    @property
    def analysis_path(self):
        return analysis_directory(self.audio_path) + "/ANLZ0000.DAT"


def encode_device_string(value):
    if "\x00" in value:
        raise ValueError("Database text must not contain NUL characters.")
    if value.isascii():
        encoded = value.encode("ascii")
        if len(encoded) <= 126:
            return bytes([2 * (len(encoded) + 1) + 1]) + encoded
        kind = 0x40
    else:
        encoded = value.encode("utf-16-le")
        kind = 0x90
    if len(encoded) + 4 > 65535:
        raise ValueError("Database text is too long.")
    return struct.pack("<BHB", kind, len(encoded) + 4, 0) + encoded


def _aligned_length(length):
    return (length + 3) & ~3


def _track_row(track, artist_id, album_id):
    row = bytearray(136)
    struct.pack_into("<HH", row, 0, 0x24, 0)
    for offset, value in (
        (4, 0x000C0700), (8, track.sample_rate), (16, track.file_size),
        (20, 0x00100000 + track.track_id), (48, track.sample_rate * 32 // 1000),
        (52, track.track_id), (56, tempo_units(track.bpm)), (64, album_id),
        (68, artist_id), (72, track.track_id),
    ):
        struct.pack_into("<I", row, offset, value)
    struct.pack_into("<HH", row, 24, 0xAE49, 0x03DD)
    struct.pack_into("<HHHHHHBBHH", row, 76, 1, 0, 0, track.sample_depth, math.ceil(track.duration_seconds), 41, 0, 0, 11, 3)
    strings = [""] * 21
    strings[2] = "2"
    strings[3] = "2"
    strings[14] = track.analysis_path
    strings[16] = "Vault synthetic export proof; hardware validation pending"
    strings[17] = track.title
    strings[19] = PurePosixPath(track.audio_path).name
    strings[20] = track.audio_path
    encoded_strings = [encode_device_string(value) for value in strings]
    for index, encoded in enumerate(encoded_strings):
        if not encoded[0] & 1:
            row.extend(bytes(_aligned_length(len(row)) - len(row)))
        struct.pack_into("<H", row, 94 + index * 2, len(row))
        row.extend(encoded)
    allocation = 136 + sum(_aligned_length(len(encoded)) for encoded in encoded_strings) + 4
    row.extend(bytes(allocation - len(row)))
    return bytes(row)


def _named_rows(tracks):
    artist_ids = {}
    album_ids = {}
    artists = []
    albums = []
    for track in tracks:
        if track.artist and track.artist not in artist_ids:
            artist_id = len(artist_ids) + 1
            artist_ids[track.artist] = artist_id
            row = struct.pack("<HHIBB", 0x60, 0, artist_id, 3, 10) + encode_device_string(track.artist)
            artists.append(row + bytes(_aligned_length(len(row)) + 4 - len(row)))
        album_key = (track.album, track.artist)
        if track.album and album_key not in album_ids:
            album_id = len(album_ids) + 1
            album_ids[album_key] = album_id
            row = struct.pack("<HHIIIIBB", 0x80, 0, 0, artist_ids.get(track.artist, 0), album_id, 0, 3, 22)
            row += encode_device_string(track.album)
            albums.append(row + bytes(_aligned_length(len(row)) + 4 - len(row)))
    return artist_ids, album_ids, artists, albums


def _split_rows(rows):
    pages = []
    current = []
    used = 0
    for row in rows:
        allocation = _aligned_length(len(row))
        if PAGE_HEADER_SIZE + allocation + ROW_GROUP_SIZE > PAGE_SIZE:
            raise ValueError("Database row does not fit in a page.")
        count = len(current) + 1
        if PAGE_HEADER_SIZE + used + allocation + math.ceil(count / 16) * ROW_GROUP_SIZE > PAGE_SIZE:
            pages.append(current)
            current = []
            used = 0
        current.append(row)
        used += allocation
    if current:
        pages.append(current)
    return pages


def _index_page(page_index, table_type, next_page):
    page = bytearray(PAGE_SIZE)
    struct.pack_into("<IIIIII", page, 0, 0, page_index, table_type, next_page, 0, 0)
    page[27] = 0x64
    struct.pack_into("<HHHH", page, 32, 0x1FFF, 0x1FFF, 0x03EC, int(table_type in (0, 19)))
    struct.pack_into("<II", page, 56, 0x1FFF0001 if table_type in (0, 19) else 0x1FFF0000, (table_type + 1) * 16)
    return page


def _data_page(page_index, table_type, next_page, rows, sequence):
    page = bytearray(PAGE_SIZE)
    struct.pack_into("<IIIIII", page, 0, 0, page_index, table_type, next_page, sequence, 0)
    count = len(rows)
    page[24] = count & 0xFF
    struct.pack_into("<H", page, 25, (count << 5) | int(count > 255))
    page[27] = 0x24
    used = 0
    for index, row in enumerate(rows):
        row_start = PAGE_HEADER_SIZE + used
        page[row_start:row_start + len(row)] = row
        if table_type in (0, 2, 3):
            struct.pack_into("<H", page, row_start + 2, index * 32)
        group, group_index = divmod(index, 16)
        group_base = PAGE_SIZE - group * ROW_GROUP_SIZE
        struct.pack_into("<H", page, group_base - 6 - group_index * 2, used)
        flags = struct.unpack_from("<H", page, group_base - 4)[0] | (1 << group_index)
        struct.pack_into("<HH", page, group_base - 4, flags, flags)
        used += _aligned_length(len(row))
    free = PAGE_SIZE - PAGE_HEADER_SIZE - used - math.ceil(count / 16) * ROW_GROUP_SIZE
    struct.pack_into("<HHHH", page, 28, free, used, count, 0)
    return page


def build_device_library(tracks, playlist_name):
    tracks = tuple(tracks)
    if not tracks or not playlist_name.strip():
        raise ValueError("The proof needs at least one track and a playlist name.")
    if len({track.track_id for track in tracks}) != len(tracks):
        raise ValueError("Track IDs must be unique.")
    if len({track.audio_path for track in tracks}) != len(tracks):
        raise ValueError("Audio paths must be unique.")
    artist_ids, album_ids, artists, albums = _named_rows(tracks)
    tables = {table_type: [] for table_type in range(TABLE_COUNT)}
    tables[0] = [_track_row(track, artist_ids.get(track.artist, 0), album_ids.get((track.album, track.artist), 0)) for track in tracks]
    tables[2] = artists
    tables[3] = albums
    tables[7] = [struct.pack("<IIIII", 0, 0, 0, 1, 0) + encode_device_string(playlist_name)]
    tables[8] = [struct.pack("<III", index, track.track_id, 1) for index, track in enumerate(tracks, 1)]
    pages = [bytearray(PAGE_SIZE)]
    pointers = []
    sequence = 1
    for table_type, rows in tables.items():
        batches = _split_rows(rows)
        first_page = len(pages)
        last_page = first_page + len(batches)
        empty_candidate = last_page + 1
        pages.append(_index_page(first_page, table_type, first_page + 1))
        for offset, batch in enumerate(batches, 1):
            pages.append(_data_page(first_page + offset, table_type, first_page + offset + 1, batch, sequence))
            sequence += 1
        pages.append(_index_page(empty_candidate, table_type, empty_candidate))
        pointers.append((table_type, empty_candidate, first_page, last_page))
    struct.pack_into("<IIIIIII", pages[0], 0, 0, PAGE_SIZE, TABLE_COUNT, len(pages), 5, sequence, 0)
    for index, pointer in enumerate(pointers):
        struct.pack_into("<IIII", pages[0], 28 + 16 * index, *pointer)
    return b"".join(pages)


def _section(tag, header, payload=b""):
    header_length = 12 + len(header)
    return tag.encode("ascii") + struct.pack(">II", header_length, header_length + len(payload)) + header + payload


def _container(sections):
    body = b"".join(sections)
    return struct.pack(">4sIIIIII", b"PMAI", 28, 28 + len(body), 1, 0x10000, 0x10000, 0) + body


def _wave_bytes(peaks):
    if len(peaks) == 0:
        raise ValueError("Waveform data must not be empty.")
    values = []
    for peak in peaks:
        if not math.isfinite(peak) or not 0 <= peak <= 1:
            raise ValueError("Waveform peaks must be finite values between zero and one.")
        height = round(peak * 31)
        values.append(height | (4 << 5) if height else 0)
    return bytes(values)


def build_analysis_files(audio_path, bpm, beat_times_ms, overview_peaks, detail_peaks):
    validate_audio_path(audio_path)
    tempo = tempo_units(bpm)
    beat_times = tuple(beat_times_ms)
    if not beat_times or any(not isinstance(value, int) or not 0 <= value < 2**32 for value in beat_times):
        raise ValueError("Beat times must be nonempty unsigned integer milliseconds.")
    if any(second <= first for first, second in zip(beat_times, beat_times[1:])):
        raise ValueError("Beat times must be strictly increasing.")
    if len(overview_peaks) != 400:
        raise ValueError("The compact waveform must contain 400 entries.")
    path_bytes = audio_path.encode("utf-16-be") + b"\x00\x00"
    path_section = _section("PPTH", struct.pack(">I", len(path_bytes)), path_bytes)
    beats = b"".join(struct.pack(">HHI", index % 4 + 1, tempo, time_ms) for index, time_ms in enumerate(beat_times))
    beat_section = _section("PQTZ", struct.pack(">III", 0, 0x80000, len(beat_times)), beats)
    overview = _wave_bytes(overview_peaks)
    detail = _wave_bytes(detail_peaks)
    cues = [_section("PCOB", struct.pack(">IHHI", cue_type, 0, 0, 0xFFFFFFFF)) for cue_type in (1, 0)]
    dat_file = _container([
        path_section, _section("PVBR", struct.pack(">I", 0), bytes(1604)), beat_section,
        _section("PWAV", struct.pack(">II", len(overview), 0x10000), overview), *cues,
    ])
    ext_file = _container([
        path_section, _section("PWV3", struct.pack(">III", 1, len(detail), 0x960000), detail), *cues,
        *[_section("PCO2", struct.pack(">IHH", cue_type, 0, 0)) for cue_type in (1, 0)],
    ])
    return {".DAT": dat_file, ".EXT": ext_file}


def inspect_analysis_file(data):
    if len(data) < 28 or data[:4] != b"PMAI":
        raise ValueError("Invalid analysis file header.")
    header_length, file_length = struct.unpack_from(">II", data, 4)
    if header_length != 28 or file_length != len(data):
        raise ValueError("Invalid analysis file length.")
    offset = header_length
    sections = []
    while offset < file_length:
        if offset + 12 > file_length:
            raise ValueError("Truncated analysis section.")
        tag, tag_header, tag_length = struct.unpack_from(">4sII", data, offset)
        if not 12 <= tag_header <= tag_length or offset + tag_length > file_length:
            raise ValueError("Invalid analysis section length.")
        sections.append((tag.decode("ascii"), tag_header, data[offset:offset + tag_length]))
        offset += tag_length
    return sections
