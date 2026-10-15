import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from .utils import sanitize_name


@dataclass(frozen=True)
class ConversionFormat:
    label: str
    suffix: str
    file_format: str
    data_format: str
    options: tuple[str, ...] = ()


CONVERSION_FORMATS = (
    ConversionFormat("WAV (16-bit PCM)", ".wav", "WAVE", "LEI16"),
    ConversionFormat("WAV (24-bit PCM)", ".wav", "WAVE", "LEI24"),
    ConversionFormat("AIFF (16-bit PCM)", ".aiff", "AIFF", "BEI16"),
    ConversionFormat("AIFF (24-bit PCM)", ".aiff", "AIFF", "BEI24"),
    ConversionFormat("FLAC (lossless)", ".flac", "flac", "flac"),
    ConversionFormat("M4A (AAC, 256 kbps)", ".m4a", "m4af", "aac", ("-b", "256000")),
    ConversionFormat("M4A (Apple Lossless)", ".m4a", "m4af", "alac"),
)


class ConversionCancelled(Exception):
    pass


def check_cancelled(cancel):
    if cancel.is_set():
        raise ConversionCancelled("Conversion cancelled")


def run_encoder(command, cancel):
    check_cancelled(cancel)
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True) as process:
        try:
            while True:
                check_cancelled(cancel)
                try:
                    _, error = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
        check_cancelled(cancel)
        if process.returncode != 0:
            raise ValueError(error.strip() or "macOS could not convert this audio file")


def publish_copy(staged, destination, stem, suffix, cancel):
    counter = 1
    while True:
        check_cancelled(cancel)
        name = stem if counter == 1 else f"{stem} {counter}"
        target = destination / f"{name}{suffix}"
        try:
            output = target.open("xb")
        except FileExistsError:
            counter += 1
            continue
        try:
            with output, staged.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    check_cancelled(cancel)
                    output.write(chunk)
                check_cancelled(cancel)
                output.flush()
                os.fsync(output.fileno())
            return target
        except BaseException:
            target.unlink(missing_ok=True)
            raise


def convert_audio_file(source, destination, output_format, cancel=None):
    if output_format not in CONVERSION_FORMATS:
        raise ValueError("Choose a supported conversion format")
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Audio file not found: {source.name}")
    if not destination.is_dir():
        raise NotADirectoryError("Choose an existing output folder")
    cancel = cancel if cancel is not None else Event()
    check_cancelled(cancel)
    with tempfile.TemporaryDirectory(dir=destination, prefix=".vault-convert-") as directory:
        staged = Path(directory) / f"converted{output_format.suffix}"
        run_encoder([
            "/usr/bin/afconvert", str(source), str(staged),
            "-f", output_format.file_format, "-d", output_format.data_format,
            *output_format.options,
        ], cancel)
        if not staged.is_file() or staged.stat().st_size == 0:
            raise ValueError("macOS did not produce an audio file")
        return publish_copy(staged, destination, sanitize_name(source.stem), output_format.suffix, cancel)
