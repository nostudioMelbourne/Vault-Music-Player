import shutil
from pathlib import Path

from .utils import describe_song, sanitize_name


def export_playlist_bundle(playlist_name, songs, destination_root, songs_dir):
    export_root = Path(destination_root) / sanitize_name(playlist_name)
    export_root.mkdir(parents=True, exist_ok=True)

    copied_entries = []
    missing_titles = []

    for song in songs:
        source = songs_dir / song.filename
        if not source.exists():
            missing_titles.append(describe_song(song))
            continue

        target = export_root / source.name
        shutil.copy2(source, target)
        copied_entries.append((song, target.name))

    if not copied_entries:
        raise FileNotFoundError("None of the playlist files could be exported because the source audio files were missing.")

    playlist_file = export_root / f"{sanitize_name(playlist_name)}.m3u8"
    with open(playlist_file, "w", encoding="utf-8") as file:
        file.write("#EXTM3U\n")
        for song, relative_name in copied_entries:
            file.write(f"#EXTINF:-1,{describe_song(song)}\n")
            file.write(f"{relative_name}\n")

    return export_root, playlist_file, missing_titles, len(copied_entries)
