import subprocess
import tempfile
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None


def analyze_bpm(path, min_bpm=70, max_bpm=200, max_seconds=420):
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
            if temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
            return None

    try:
        windows = _read_analysis_windows(wav_path, max_seconds)
        estimates = []
        for sample_rate, samples, weight in windows:
            estimate = _estimate_bpm(sample_rate, samples, min_bpm, max_bpm)
            if estimate is not None:
                estimates.append((estimate, weight))

        return _consensus_bpm(estimates, min_bpm, max_bpm)
    except (OSError, EOFError, ValueError, wave.Error):
        return None
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def _read_analysis_windows(path, max_seconds):
    with wave.open(str(path), "rb") as audio:
        sample_rate = audio.getframerate()
        channel_count = max(1, audio.getnchannels())
        sample_width = audio.getsampwidth()
        frame_count = audio.getnframes()
        duration = frame_count / sample_rate if sample_rate > 0 else 0

        if duration <= 0 or sample_width not in (1, 2, 3, 4):
            raise ValueError("Unsupported or empty audio file.")

        windows = []
        for start_frame, frames_to_read, weight in _analysis_window_plan(sample_rate, frame_count, max_seconds):
            audio.setpos(start_frame)
            data = audio.readframes(frames_to_read)
            samples = _decode_mono_pcm(data, sample_width, channel_count)
            if samples.size >= sample_rate * 4:
                windows.append((sample_rate, samples.astype(np.float32, copy=False), weight))

    return windows


def _analysis_window_plan(sample_rate, frame_count, max_seconds):
    duration = frame_count / sample_rate
    if duration <= 100:
        return [(0, frame_count, 1.0)]

    window_seconds = min(90.0, max(45.0, duration * 0.22))
    max_total_seconds = max(window_seconds, float(max_seconds or 0))
    max_windows = max(1, int(max_total_seconds // window_seconds))
    max_windows = min(5, max_windows)
    latest_start = max(0.0, duration - window_seconds)
    starts = [
        min(latest_start, max(12.0, duration * 0.08)),
        latest_start * 0.32,
        latest_start * 0.52,
        latest_start * 0.72,
        min(latest_start, max(0.0, duration - window_seconds - 18.0)),
    ]

    unique_starts = []
    for start in starts:
        start = max(0.0, min(latest_start, start))
        if all(abs(start - existing) > window_seconds * 0.35 for existing in unique_starts):
            unique_starts.append(start)

    if len(unique_starts) > max_windows:
        step = (len(unique_starts) - 1) / max(1, max_windows - 1)
        unique_starts = [unique_starts[round(index * step)] for index in range(max_windows)]

    windows = []
    for start in unique_starts:
        start_frame = int(start * sample_rate)
        frames_to_read = min(frame_count - start_frame, int(window_seconds * sample_rate))
        if frames_to_read > 0:
            position_ratio = start / max(latest_start, 1.0)
            middle_weight = 1.0 - abs(position_ratio - 0.52) * 0.35
            windows.append((start_frame, frames_to_read, max(0.82, middle_weight)))

    return windows or [(0, min(frame_count, int(window_seconds * sample_rate)), 1.0)]


def _read_mono_samples(path, max_seconds):
    with wave.open(str(path), "rb") as audio:
        sample_rate = audio.getframerate()
        channel_count = max(1, audio.getnchannels())
        sample_width = audio.getsampwidth()
        frame_count = audio.getnframes()
        frames_to_read = min(frame_count, int(sample_rate * max_seconds))

        if frames_to_read <= 0 or sample_width not in (1, 2, 3, 4):
            raise ValueError("Unsupported or empty audio file.")

        data = audio.readframes(frames_to_read)

    samples = _decode_mono_pcm(data, sample_width, channel_count)
    return sample_rate, samples.astype(np.float32, copy=False)


def _decode_mono_pcm(data, sample_width, channel_count):
    samples = _decode_pcm(data, sample_width)
    if channel_count > 1:
        usable = (samples.size // channel_count) * channel_count
        samples = samples[:usable].reshape(-1, channel_count).mean(axis=1)

    return samples


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


def _estimate_bpm(sample_rate, samples, min_bpm, max_bpm):
    if samples.size < sample_rate * 4:
        return None

    samples = samples - float(samples.mean())
    peak = float(np.max(np.abs(samples), initial=0.0))
    if peak <= 0.0001:
        return None
    samples = samples / peak

    envelope, frames_per_second = _onset_envelope(sample_rate, samples)
    if envelope is None:
        return None

    autocorrelation = _normalized_autocorrelation(envelope)
    candidates = _tempo_candidates(autocorrelation, frames_per_second, min_bpm, max_bpm)
    candidates.extend(_interval_candidates(envelope, frames_per_second, min_bpm, max_bpm))
    if not candidates:
        return None

    best_bpm = _choose_tempo(candidates, autocorrelation, frames_per_second, min_bpm, max_bpm)
    if best_bpm is None:
        return None

    return int(round(best_bpm))


def _consensus_bpm(estimates, min_bpm, max_bpm):
    if not estimates:
        return None

    groups = []
    for bpm, weight in estimates:
        bpm = _normalize_bpm(float(bpm), min_bpm, max_bpm)
        if bpm is None:
            continue

        for group in groups:
            if _tempo_distance(group["bpm"], bpm) <= 0.025:
                group["score"] += weight
                group["weighted_bpm"] += bpm * weight
                group["weight"] += weight
                group["bpm"] = group["weighted_bpm"] / max(group["weight"], 0.0001)
                group["count"] += 1
                break
        else:
            groups.append(
                {
                    "bpm": bpm,
                    "score": weight,
                    "weighted_bpm": bpm * weight,
                    "weight": weight,
                    "count": 1,
                }
            )

    if not groups:
        return None

    for group in groups:
        group["score"] += max(0, group["count"] - 1) * 0.45
        group["score"] += 0.12 if 90 <= group["bpm"] <= 170 else 0.0

    groups.sort(key=lambda item: item["score"], reverse=True)
    return int(round(groups[0]["bpm"]))


def _tempo_distance(first_bpm, second_bpm):
    return abs(np.log2(first_bpm / second_bpm))


def _onset_envelope(sample_rate, samples):
    frame_length = max(512, int(sample_rate * 0.046))
    hop_length = max(128, int(sample_rate * 0.0116))
    frame_count = 1 + (samples.size - frame_length) // hop_length
    if frame_count < 32:
        return None, None

    usable_length = frame_length + (frame_count - 1) * hop_length
    frames = np.lib.stride_tricks.sliding_window_view(samples[:usable_length], frame_length)[::hop_length]
    window = np.hanning(frame_length).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1))
    magnitudes = np.log1p(spectrum)

    frequency_count = magnitudes.shape[1]
    weights = np.linspace(1.0, 1.7, frequency_count, dtype=np.float32)
    flux = np.maximum(np.diff(magnitudes, axis=0, prepend=magnitudes[:1]), 0.0)
    spectral_flux = np.mean(flux * weights, axis=1)

    energy = np.sqrt(np.mean(np.square(frames), axis=1))
    energy_flux = np.maximum(np.diff(np.log1p(energy * 50.0), prepend=0.0), 0.0)
    envelope = (spectral_flux * 0.75) + (energy_flux * 0.25)

    envelope = _local_normalize(envelope, sample_rate / hop_length)
    if envelope is None:
        return None, None

    return envelope, sample_rate / hop_length


def _local_normalize(envelope, frames_per_second):
    if envelope.max(initial=0.0) <= 0.0001:
        return None

    smoothing_window = max(3, int(frames_per_second * 0.25))
    baseline = np.convolve(envelope, np.ones(smoothing_window) / smoothing_window, mode="same")
    envelope = np.maximum(envelope - baseline, 0.0)
    envelope = np.maximum(envelope - np.percentile(envelope, 35), 0.0)

    if envelope.max(initial=0.0) <= 0.0001:
        return None

    envelope = envelope / envelope.max()
    envelope -= envelope.mean()
    standard_deviation = envelope.std()
    if standard_deviation <= 0.0001:
        return None

    return envelope / standard_deviation


def _normalized_autocorrelation(envelope):
    size = int(2 ** np.ceil(np.log2(max(1, envelope.size * 2 - 1))))
    spectrum = np.fft.rfft(envelope, size)
    autocorrelation = np.fft.irfft(spectrum * np.conj(spectrum), size)[: envelope.size]
    normalization = np.arange(envelope.size, 0, -1, dtype=np.float32)
    autocorrelation = autocorrelation / normalization
    if autocorrelation[0] > 0:
        autocorrelation = autocorrelation / autocorrelation[0]
    return autocorrelation


def _tempo_candidates(autocorrelation, frames_per_second, min_bpm, max_bpm):
    min_lag = max(1, int(frames_per_second * 60.0 / max_bpm))
    max_lag = min(len(autocorrelation) - 1, int(frames_per_second * 60.0 / min_bpm))
    if max_lag <= min_lag:
        return []

    candidates = []
    for lag in range(min_lag, max_lag + 1):
        bpm = 60.0 * frames_per_second / lag
        score = _periodicity_score(autocorrelation, lag)
        if score > 0:
            candidates.append((bpm, score, "autocorrelation"))

    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[:24]


def _interval_candidates(envelope, frames_per_second, min_bpm, max_bpm):
    peaks = _onset_peaks(envelope, frames_per_second)
    if peaks.size < 4:
        return []

    min_interval = 60.0 / max_bpm
    max_interval = 60.0 / min_bpm
    intervals = []
    peak_count = min(peaks.size, 220)

    for index in range(peak_count):
        for next_index in range(index + 1, min(index + 9, peak_count)):
            interval = (peaks[next_index] - peaks[index]) / frames_per_second
            if min_interval <= interval <= max_interval:
                intervals.append(interval)

    if not intervals:
        return []

    bpms = 60.0 / np.asarray(intervals)
    histogram, edges = np.histogram(bpms, bins=np.arange(min_bpm, max_bpm + 2, 1))
    candidates = []
    for index in np.argsort(histogram)[-12:]:
        count = int(histogram[index])
        if count <= 0:
            continue
        bpm = (edges[index] + edges[index + 1]) / 2.0
        candidates.append((bpm, count / max(1, peak_count), "intervals"))

    return candidates


def _onset_peaks(envelope, frames_per_second):
    threshold = max(0.35, float(np.percentile(envelope, 78)))
    min_spacing = max(1, int(frames_per_second * 0.11))
    peaks = []
    last_peak = -min_spacing

    for index in range(1, envelope.size - 1):
        if index - last_peak < min_spacing:
            continue

        value = envelope[index]
        if value < threshold or value < envelope[index - 1] or value < envelope[index + 1]:
            continue

        peaks.append(index)
        last_peak = index

    return np.asarray(peaks, dtype=np.int32)


def _choose_tempo(candidates, autocorrelation, frames_per_second, min_bpm, max_bpm):
    grouped = []
    for bpm, score, source in candidates:
        normalized_bpm = _normalize_bpm(float(bpm), min_bpm, max_bpm)
        if normalized_bpm is None:
            continue

        source_weight = 1.0 if source == "autocorrelation" else 0.75
        weighted_score = score * source_weight
        for group in grouped:
            if abs(group["bpm"] - normalized_bpm) <= 3.0:
                group["score"] += weighted_score
                group["weighted_bpm"] += normalized_bpm * weighted_score
                group["weight"] += weighted_score
                group["bpm"] = group["weighted_bpm"] / max(group["weight"], 0.0001)
                break
        else:
            grouped.append(
                {
                    "bpm": normalized_bpm,
                    "score": weighted_score,
                    "weighted_bpm": normalized_bpm * weighted_score,
                    "weight": weighted_score,
                }
            )

    if not grouped:
        return None

    rescored = []
    for group in grouped:
        bpm = group["bpm"]
        score = group["score"]
        lag = frames_per_second * 60.0 / bpm
        agreement = _periodicity_score(autocorrelation, lag)
        prior = np.exp(-0.5 * (np.log2(bpm / 120.0) / 1.15) ** 2)
        dance_range_bias = 0.12 if 90 <= bpm <= 170 else 0.0
        rescored.append((bpm, score + agreement * 2.5 + prior * 0.08 + dance_range_bias))

    rescored.sort(key=lambda item: item[1], reverse=True)
    best_bpm, best_score = rescored[0]
    best_agreement = _periodicity_score(autocorrelation, frames_per_second * 60.0 / best_bpm)

    if best_bpm < 100:
        for multiplier in (1.5, 2.0):
            alternate_bpm = best_bpm * multiplier
            if alternate_bpm > max_bpm or not 100 <= alternate_bpm <= 180:
                continue

            alternate_agreement = _periodicity_score(autocorrelation, frames_per_second * 60.0 / alternate_bpm)
            nearby_score = max(
                (score for bpm, score in rescored if abs(bpm - alternate_bpm) <= 4.0),
                default=0.0,
            )
            if alternate_agreement >= best_agreement * 0.92 or nearby_score >= best_score * 0.9:
                return alternate_bpm

    for bpm, score in rescored[1:8]:
        if abs(bpm - best_bpm * 2) <= 3 and score >= best_score * 0.82 and 84 <= bpm <= 172:
            return bpm
        if abs(bpm * 2 - best_bpm) <= 3 and score >= best_score * 1.05 and 84 <= bpm <= 172:
            return bpm

    return best_bpm


def _normalize_bpm(bpm, min_bpm, max_bpm):
    while bpm < min_bpm:
        bpm *= 2.0
    while bpm > max_bpm:
        bpm /= 2.0

    if min_bpm <= bpm <= max_bpm:
        return bpm

    return None


def _periodicity_score(autocorrelation, lag):
    if lag <= 0 or lag >= len(autocorrelation):
        return 0.0

    score = _interpolated_value(autocorrelation, lag)
    score += 0.55 * _interpolated_value(autocorrelation, lag * 2)
    score += 0.30 * _interpolated_value(autocorrelation, lag * 3)
    score += 0.18 * _interpolated_value(autocorrelation, lag / 2)
    return max(0.0, float(score))


def _interpolated_value(values, position):
    if position < 1 or position >= len(values) - 1:
        return 0.0

    low = int(position)
    high = low + 1
    fraction = position - low
    return float(values[low] * (1.0 - fraction) + values[high] * fraction)
