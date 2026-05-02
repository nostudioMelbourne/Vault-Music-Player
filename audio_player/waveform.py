import subprocess
import tempfile
import wave
from pathlib import Path


def build_waveform_peaks(path, target_bars=256):
    source_path = Path(path)
    wav_path = source_path
    temporary_path = None
    target_bars = max(1, int(target_bars or 1))

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
            return []

    try:
        return _read_waveform_peaks(wav_path, target_bars)
    except (OSError, EOFError, wave.Error):
        return []
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def _read_waveform_peaks(path, target_bars):
    with wave.open(str(path), "rb") as audio:
        frame_count = audio.getnframes()
        channel_count = max(1, audio.getnchannels())
        sample_width = audio.getsampwidth()
        frame_width = channel_count * sample_width

        if frame_count <= 0 or sample_width not in (1, 2, 3, 4):
            return []

        peaks = []
        for bar_index in range(max(1, target_bars)):
            start_frame = int(bar_index * frame_count / target_bars)
            end_frame = int((bar_index + 1) * frame_count / target_bars)
            segment_frames = max(1, end_frame - start_frame)
            stride = max(1, segment_frames // 900)

            audio.setpos(start_frame)
            data = audio.readframes(segment_frames)
            peak = _segment_peak(data, frame_width, sample_width, channel_count, stride)
            peaks.append(peak)

    highest_peak = max(peaks, default=0.0)
    if highest_peak <= 0:
        return []

    return [min(1.0, peak / highest_peak) for peak in peaks]


def _segment_peak(data, frame_width, sample_width, channel_count, stride):
    peak = 0.0
    max_value = float((1 << (sample_width * 8 - 1)) - 1)
    frame_step = frame_width * stride

    for frame_offset in range(0, len(data), frame_step):
        frame = data[frame_offset : frame_offset + frame_width]
        if len(frame) < frame_width:
            break

        for channel in range(channel_count):
            sample_offset = channel * sample_width
            sample = frame[sample_offset : sample_offset + sample_width]

            if sample_width == 1:
                value = sample[0] - 128
                channel_peak = abs(value) / 128.0
            else:
                value = int.from_bytes(sample, byteorder="little", signed=True)
                channel_peak = abs(value) / max_value

            if channel_peak > peak:
                peak = channel_peak

    return peak
