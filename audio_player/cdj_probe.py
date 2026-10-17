import hashlib
import json
import math
import tempfile
import wave
from pathlib import Path

import numpy as np

from .cdj_formats import ExportTrack, build_analysis_files, build_device_library, inspect_analysis_file, tempo_units


PROBE_PLAYLIST = "Vault USB Probe"
PROBE_CASES = (
    ("01 - Straight 120", 120.0, 0.0),
    ("02 - Fractional 127.50", 127.5, 0.0),
    ("03 - Leading Silence 90", 90.0, 2.0),
)


def _fixture_audio(bpm, first_beat_seconds):
    sample_rate = 44100
    tempo = tempo_units(bpm) / 100
    beat_seconds = tuple(first_beat_seconds + index * 60 / tempo for index in range(32))
    frame_count = math.ceil((first_beat_seconds + 32 * 60 / tempo) * sample_rate)
    samples = np.zeros(frame_count, dtype=np.float64)
    for index, beat_time in enumerate(beat_seconds):
        start = round(beat_time * sample_rate)
        beat_frames = min(round(sample_rate * 0.12), frame_count - start)
        local_time = np.arange(beat_frames) / sample_rate
        frequency = 110 if index % 4 == 0 else 440
        amplitude = 0.65 if index % 4 == 0 else 0.4
        pulse = amplitude * np.sin(2 * np.pi * frequency * local_time) * np.exp(-local_time * 35)
        samples[start:start + beat_frames] += pulse
    return samples, tuple(round(seconds * 1000) for seconds in beat_seconds)


def _peaks(samples, count):
    boundaries = np.linspace(0, len(samples), count + 1, dtype=np.int64)
    return [float(np.max(np.abs(samples[start:end]), initial=0)) for start, end in zip(boundaries, boundaries[1:])]


def _write_wav(path, samples):
    pcm = np.round(np.clip(samples, -1, 1) * 32767).astype("<i2")
    stereo = np.column_stack((pcm, pcm)).astype("<i2", copy=False)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        audio.writeframes(stereo.tobytes())
    return pcm.astype(np.float64) / 32768


def create_probe_export(output_directory):
    output = Path(output_directory).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Choose a new output folder; the proof will not overwrite an existing path.")
    if not output.parent.is_dir():
        raise FileNotFoundError("The output folder's parent must already exist.")
    with tempfile.TemporaryDirectory(prefix=".vault-cdj-probe-", dir=output.parent) as temporary:
        stage = Path(temporary) / "export"
        stage.mkdir()
        audio_folder = stage / "Contents" / "Vault USB Probe"
        audio_folder.mkdir(parents=True)
        tracks = []
        records = []
        for track_id, (title, bpm, first_beat) in enumerate(PROBE_CASES, 1):
            samples, beats = _fixture_audio(bpm, first_beat)
            audio_path = audio_folder / f"{title}.wav"
            decoded_samples = _write_wav(audio_path, samples)
            track = ExportTrack(
                track_id, title, "Vault Probe", "CDJ Export Proof",
                "/" + audio_path.relative_to(stage).as_posix(), bpm, len(samples) / 44100,
                audio_path.stat().st_size,
            )
            analysis_path = stage / track.analysis_path.lstrip("/")
            analysis_path.parent.mkdir(parents=True)
            detail_count = math.ceil(track.duration_seconds * 150)
            analysis_files = build_analysis_files(
                track.audio_path, bpm, beats, _peaks(decoded_samples, 400), _peaks(decoded_samples, detail_count),
            )
            for suffix, data in analysis_files.items():
                inspect_analysis_file(data)
                analysis_path.with_suffix(suffix).write_bytes(data)
            tracks.append(track)
            records.append({
                "track_id": track_id, "title": title, "bpm": bpm,
                "first_beat_ms": beats[0], "beat_times_ms": list(beats),
                "duration_seconds": track.duration_seconds, "sample_rate": 44100,
                "sample_depth": 16, "audio_path": track.audio_path,
                "analysis_path": track.analysis_path, "detail_waveform_entries": detail_count,
            })
        database_path = stage / "PIONEER" / "rekordbox" / "export.pdb"
        database_path.parent.mkdir(parents=True)
        database_path.write_bytes(build_device_library(tracks, PROBE_PLAYLIST))
        checksums = {
            path.relative_to(stage).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(stage.rglob("*")) if path.is_file()
        }
        manifest = {
            "format_version": 1, "kind": "synthetic-cdj-export-proof",
            "playlist": PROBE_PLAYLIST, "library_format": "Device Library",
            "hardware_verified": False, "onelibrary_included": False,
            "tracks": records, "sha256": checksums,
        }
        (stage / "vault-cdj-probe.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        output.mkdir()
        published = []
        try:
            for child in stage.iterdir():
                target = output / child.name
                child.rename(target)
                published.append(target)
        except OSError:
            for child in reversed(published):
                child.rename(stage / child.name)
            try:
                output.rmdir()
            except OSError:
                pass
            raise
    return manifest
