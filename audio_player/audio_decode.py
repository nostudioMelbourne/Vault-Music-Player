import subprocess
import tempfile
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

try:
    import soundfile as sf
except Exception:
    sf = None


def read_mono_samples(path, max_seconds=None):
    if np is None:
        return None

    source_path = Path(path)

    if sf is not None:
        try:
            return _read_with_soundfile(source_path, max_seconds)
        except Exception:
            pass

    return _read_with_wave_or_afconvert(source_path, max_seconds)


def _read_with_soundfile(path, max_seconds):
    info = sf.info(str(path))
    sample_rate = int(info.samplerate)
    if sample_rate <= 0 or info.frames <= 0:
        raise ValueError("Unsupported or empty audio file.")

    frames = -1
    if max_seconds is not None:
        frames = max(1, min(info.frames, int(float(max_seconds) * sample_rate)))

    data, sample_rate = sf.read(str(path), frames=frames, dtype="float32", always_2d=True)
    if data.size == 0:
        raise ValueError("Unsupported or empty audio file.")

    samples = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
    return int(sample_rate), samples.astype(np.float32, copy=False)


def _read_with_wave_or_afconvert(path, max_seconds):
    wav_path = path
    temporary_path = None

    if path.suffix.lower() != ".wav":
        temporary = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temporary_path = Path(temporary.name)
        temporary.close()

        try:
            subprocess.run(
                [
                    "/usr/bin/afconvert",
                    str(path),
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
        return _read_wav_mono_samples(wav_path, max_seconds)
    except (OSError, EOFError, ValueError, wave.Error):
        return None
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def _read_wav_mono_samples(path, max_seconds):
    with wave.open(str(path), "rb") as audio:
        sample_rate = audio.getframerate()
        channel_count = max(1, audio.getnchannels())
        sample_width = audio.getsampwidth()
        frame_count = audio.getnframes()

        if sample_rate <= 0 or frame_count <= 0 or sample_width not in (1, 2, 3, 4):
            raise ValueError("Unsupported or empty audio file.")

        frames_to_read = frame_count
        if max_seconds is not None:
            frames_to_read = min(frame_count, int(sample_rate * float(max_seconds)))

        data = audio.readframes(max(1, frames_to_read))

    samples = _decode_pcm(data, sample_width)
    if channel_count > 1:
        usable = (samples.size // channel_count) * channel_count
        samples = samples[:usable].reshape(-1, channel_count).mean(axis=1)

    return sample_rate, samples.astype(np.float32, copy=False)


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
