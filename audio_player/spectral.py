import math
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None


@dataclass(frozen=True)
class SpectrumAnalysis:
    frames: object
    frame_interval: float
    frequencies: tuple

    def frame_at(self, seconds):
        if len(self.frames) == 0:
            return ()

        index = int(max(0.0, float(seconds)) / max(self.frame_interval, 0.001))
        return self.frames[min(index, len(self.frames) - 1)]


def build_spectrum_analysis(path, band_count=30, frames_per_second=12, max_frames=7200):
    if np is None:
        return None

    source_path = Path(path)
    wav_path = source_path
    temporary_path = None

    if source_path.suffix.lower() != ".wav":
        temporary = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temporary_path = Path(temporary.name)
        temporary.close()

        try:
            subprocess.run(
                [
                    "/usr/bin/afconvert",
                    str(source_path),
                    str(temporary_path),
                    "-f",
                    "WAVE",
                    "-d",
                    "LEI16",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            wav_path = temporary_path
        except (OSError, subprocess.CalledProcessError):
            temporary_path.unlink(missing_ok=True)
            return None

    try:
        return _read_spectrum_analysis(wav_path, band_count, frames_per_second, max_frames)
    except (OSError, EOFError, ValueError, wave.Error):
        return None
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def _read_spectrum_analysis(path, band_count, frames_per_second, max_frames):
    band_count = max(8, int(band_count or 0))
    frames_per_second = max(1.0, float(frames_per_second or 0))
    max_frames = max(1, int(max_frames or 0))

    with wave.open(str(path), "rb") as audio:
        sample_rate = audio.getframerate()
        channel_count = max(1, audio.getnchannels())
        sample_width = audio.getsampwidth()
        frame_count = audio.getnframes()

        if sample_rate <= 0 or frame_count <= 0 or sample_width not in (1, 2, 3, 4):
            raise ValueError("Unsupported or empty audio file.")

        duration = frame_count / sample_rate
        analysis_frame_count = min(max_frames, max(1, int(math.ceil(duration * frames_per_second))))
        frame_interval = duration / analysis_frame_count
        fft_size = 4096 if sample_rate >= 22050 else 2048
        window = np.hanning(fft_size).astype(np.float32)
        window_scale = max(float(window.sum()) / 2.0, 1.0)
        fft_frequencies = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
        max_frequency = min(16000.0, sample_rate / 2.0)
        band_edges = np.geomspace(45.0, max(46.0, max_frequency), band_count + 1)
        band_frequencies = np.sqrt(band_edges[:-1] * band_edges[1:])
        band_slices = _build_band_slices(fft_frequencies, band_edges)
        decibels = np.empty((analysis_frame_count, band_count), dtype=np.float32)

        for analysis_index in range(analysis_frame_count):
            center_frame = int((analysis_index + 0.5) * frame_interval * sample_rate)
            start_frame = max(0, min(frame_count - 1, center_frame - fft_size // 2))
            audio.setpos(start_frame)
            data = audio.readframes(min(fft_size, frame_count - start_frame))
            samples = _decode_mono_pcm(data, sample_width, channel_count)

            if samples.size < fft_size:
                samples = np.pad(samples, (0, fft_size - samples.size))
            else:
                samples = samples[:fft_size]

            samples = samples - float(samples.mean())
            magnitudes = np.abs(np.fft.rfft(samples * window)) / window_scale
            for band_index, (left, right) in enumerate(band_slices):
                magnitude = float(np.max(magnitudes[left:right], initial=0.0))
                decibels[analysis_index, band_index] = 20.0 * math.log10(max(magnitude, 1e-7))

    finite_values = decibels[np.isfinite(decibels)]
    reference_db = float(np.percentile(finite_values, 98)) if finite_values.size else -18.0
    ceiling_db = min(-6.0, max(-28.0, reference_db))
    floor_db = ceiling_db - 60.0
    normalized = np.clip((decibels - floor_db) / (ceiling_db - floor_db), 0.0, 1.0)
    normalized = np.power(normalized, 0.72).astype(np.float32)

    if band_count > 2:
        smoothed = normalized.copy()
        smoothed[:, 1:-1] = np.maximum(
            normalized[:, 1:-1],
            normalized[:, :-2] * 0.18
            + normalized[:, 1:-1] * 0.64
            + normalized[:, 2:] * 0.18,
        )
        normalized = smoothed

    return SpectrumAnalysis(
        frames=normalized,
        frame_interval=frame_interval,
        frequencies=tuple(float(value) for value in band_frequencies),
    )


def _build_band_slices(fft_frequencies, band_edges):
    slices = []
    last_bin = len(fft_frequencies) - 1

    for low, high in zip(band_edges[:-1], band_edges[1:]):
        left = min(last_bin, max(1, int(np.searchsorted(fft_frequencies, low, side="left"))))
        right = min(len(fft_frequencies), int(np.searchsorted(fft_frequencies, high, side="right")))
        slices.append((left, max(left + 1, right)))

    return slices


def _decode_mono_pcm(data, sample_width, channel_count):
    samples = _decode_pcm(data, sample_width)
    if channel_count > 1:
        usable = (samples.size // channel_count) * channel_count
        samples = samples[:usable].reshape(-1, channel_count).mean(axis=1)

    return samples.astype(np.float32, copy=False)


def _decode_pcm(data, sample_width):
    if sample_width == 1:
        return (np.frombuffer(data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0

    if sample_width == 2:
        return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0

    if sample_width == 3:
        raw = np.frombuffer(data, dtype=np.uint8)
        usable = (raw.size // 3) * 3
        triples = raw[:usable].reshape(-1, 3).astype(np.int32)
        values = triples[:, 0] | (triples[:, 1] << 8) | (triples[:, 2] << 16)
        values = np.where(values & 0x800000, values - 0x1000000, values)
        return values.astype(np.float32) / 8388608.0

    return np.frombuffer(data, dtype="<i4").astype(np.float32) / 2147483648.0
