import re
from pathlib import Path


def sanitize_name(value):
    cleaned = re.sub(r'[<>:"/\\|?*]+', "", value).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Untitled"


def unique_path(directory, stem, suffix, current_path=None):
    candidate = directory / f"{stem}{suffix}"
    counter = 2

    while candidate.exists() and candidate != current_path:
        candidate = directory / f"{stem} {counter}{suffix}"
        counter += 1

    return candidate


def describe_song(song):
    artist = song.artist.strip()
    return f"{song.title} - {artist}" if artist else song.title


def format_seconds(seconds):
    total_seconds = max(0, int(seconds or 0))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes}:{seconds:02d}"
