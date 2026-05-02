import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "AudioPlayer"
SUPPORTED_EXTENSIONS = {".flac", ".mp3", ".wav"}


@dataclass(frozen=True)
class AppPaths:
    script_dir: Path
    app_support_dir: Path
    songs_dir: Path
    library_db: Path
    playlist_db: Path
    legacy_songs_dir: Path
    legacy_playlists_dir: Path
    icon_candidates: tuple[Path, ...]


def build_paths():
    script_dir = Path(__file__).resolve().parent.parent
    default_data_dir = Path.home() / "Library" / "Application Support" / APP_NAME
    app_support_dir = Path(os.environ.get("AUDIOPLAYER_DATA_DIR", default_data_dir))

    return AppPaths(
        script_dir=script_dir,
        app_support_dir=app_support_dir,
        songs_dir=app_support_dir / "songs",
        library_db=app_support_dir / "library.json",
        playlist_db=app_support_dir / "playlists.json",
        legacy_songs_dir=script_dir / "songs",
        legacy_playlists_dir=script_dir / "playlists",
        icon_candidates=(
            script_dir / "app_icon.png",
            script_dir / "assets" / "app_icon.png",
            script_dir / "Pixelated musical note in retro style.png",
            script_dir / "app_icon.icns",
            script_dir / "assets" / "app_icon.icns",
        ),
    )
