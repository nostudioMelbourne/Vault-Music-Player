from .audio_decode import np, read_mono_samples


def build_waveform_peaks(path, target_bars=256):
    if np is None:
        return []

    target_bars = max(1, int(target_bars or 1))
    decoded = read_mono_samples(path)
    if decoded is None:
        return []

    _sample_rate, samples = decoded
    if samples.size == 0:
        return []

    boundaries = np.linspace(0, samples.size, target_bars + 1, dtype=np.int64)
    peaks = []
    for bar_index in range(target_bars):
        start = int(boundaries[bar_index])
        end = int(boundaries[bar_index + 1])
        if end <= start:
            peaks.append(0.0)
            continue

        segment = samples[start:end]
        peaks.append(float(np.max(np.abs(segment), initial=0.0)))

    highest_peak = max(peaks, default=0.0)
    if highest_peak <= 0:
        return []

    return [min(1.0, peak / highest_peak) for peak in peaks]
