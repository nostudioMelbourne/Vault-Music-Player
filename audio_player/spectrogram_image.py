"""Build nearest-neighbor spectrogram RGB images without disk I/O."""

import operator

try:
    import numpy as np
except ImportError:
    np = None


def build_spectrogram_ppm(values, palette, width, height):
    """Return binary PPM pixels with the lowest frequency at the bottom."""
    if np is None:
        raise ValueError("NumPy is required to render a spectrogram image.")

    try:
        width = operator.index(width)
        height = operator.index(height)
    except TypeError as exc:
        raise ValueError("Image dimensions must be positive integers.") from exc
    if width < 1 or height < 1:
        raise ValueError("Image dimensions must be positive integers.")

    source = np.asarray(values)
    if source.ndim != 2 or source.size == 0:
        raise ValueError("Spectrogram values must be a non-empty two-dimensional grid.")
    if not np.issubdtype(source.dtype, np.integer) or source.min() < 0 or source.max() > 255:
        raise ValueError("Spectrogram intensities must be integers between 0 and 255.")
    if len(palette) != 256 or any(len(color) != 3 for color in palette):
        raise ValueError("The spectrogram palette must contain 256 RGB colors.")

    colors = np.frombuffer(b"".join(palette), dtype=np.uint8).reshape(256, 3)
    source_height, source_width = source.shape
    rows = source_height - 1 - (np.arange(height, dtype=np.int64) * source_height // height)
    columns = np.arange(width, dtype=np.int64) * source_width // width
    pixels = colors[source[rows[:, None], columns[None, :]]]
    return f"P6\n{width} {height}\n255\n".encode("ascii") + pixels.tobytes()
