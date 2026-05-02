import json
import shutil
from pathlib import Path
from uuid import uuid4

from .config import SUPPORTED_EXTENSIONS
from .exporter import export_playlist_bundle
from .models import AlbumSummary, Song
from .utils import sanitize_name, unique_path


class LibraryManager:
    def __init__(self, paths):
        self.paths = paths
        self.library = []
        self.playlists = {}
        self.ensure_storage_directories()
        self.load_state()

    def ensure_storage_directories(self):
        self.paths.app_support_dir.mkdir(parents=True, exist_ok=True)
        self.paths.songs_dir.mkdir(parents=True, exist_ok=True)

    def read_json(self, path, default):
        if not path.exists():
            return default

        try:
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            return default

    def write_json(self, path, payload):
        with open(path, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

    def import_legacy_songs_if_needed(self):
        if any(self.paths.songs_dir.iterdir()):
            return 0

        if not self.paths.legacy_songs_dir.exists():
            return 0

        copied_count = 0
        for path in sorted(self.paths.legacy_songs_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            target = unique_path(self.paths.songs_dir, sanitize_name(path.stem), path.suffix.lower())
            shutil.copy2(path, target)
            copied_count += 1

        return copied_count

    def load_state(self):
        self.import_legacy_songs_if_needed()
        self.reload_state()

    def reload_state(self):
        self.load_library()
        self.sync_library_with_folder()
        self.load_playlists()
        self.prune_playlists()
        self.save_library()
        self.save_playlists()

    def load_library(self):
        payload = self.read_json(self.paths.library_db, [])
        self.library = []

        if not isinstance(payload, list):
            return

        for item in payload:
            if not isinstance(item, dict):
                continue

            filename = item.get("filename")
            if not isinstance(filename, str) or not filename:
                continue

            self.library.append(Song.from_dict(item))

    def sync_library_with_folder(self):
        songs_on_disk = {}
        for path in sorted(self.paths.songs_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                songs_on_disk[path.name] = path

        existing_by_filename = {song.filename: song for song in self.library}
        synced_library = []

        for filename in sorted(songs_on_disk):
            existing = existing_by_filename.get(filename)
            if existing:
                existing.title = existing.title.strip() or Path(filename).stem
                existing.artist = existing.artist.strip()
                existing.album = existing.album.strip()
                synced_library.append(existing)
                continue

            synced_library.append(
                Song(
                    id=uuid4().hex,
                    filename=filename,
                    title=Path(filename).stem,
                    artist="",
                    album="",
                )
            )

        self.library = synced_library

    def load_playlists(self):
        payload = self.read_json(self.paths.playlist_db, None)
        self.playlists = {}

        if isinstance(payload, dict):
            for name, song_ids in payload.items():
                if not isinstance(name, str) or not isinstance(song_ids, list):
                    continue

                clean_name = name.strip()
                if not clean_name:
                    continue

                self.playlists[clean_name] = [str(song_id) for song_id in song_ids if song_id]
            return

        self.load_legacy_playlists()

    def load_legacy_playlists(self):
        if not self.paths.legacy_playlists_dir.exists():
            return

        songs_by_filename = {song.filename: song.id for song in self.library}
        for path in sorted(self.paths.legacy_playlists_dir.glob("*.json")):
            payload = self.read_json(path, [])
            song_ids = []

            if isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, str):
                        continue

                    song_id = songs_by_filename.get(Path(item).name)
                    if song_id and song_id not in song_ids:
                        song_ids.append(song_id)

            if song_ids:
                self.playlists[path.stem] = song_ids

    def prune_playlists(self):
        valid_song_ids = {song.id for song in self.library}
        for name in list(self.playlists):
            self.playlists[name] = [song_id for song_id in self.playlists[name] if song_id in valid_song_ids]

    def save_library(self):
        self.write_json(self.paths.library_db, [song.to_dict() for song in self.library])

    def save_playlists(self):
        self.write_json(self.paths.playlist_db, self.playlists)

    def song_path(self, song):
        return self.paths.songs_dir / song.filename

    def get_song(self, song_id):
        for song in self.library:
            if song.id == song_id:
                return song
        return None

    def increment_play_count(self, song_id):
        song = self.get_song(song_id)
        if song is None:
            return None

        song.play_count += 1
        self.save_library()
        return song

    def sorted_songs(self):
        return sorted(
            self.library,
            key=lambda song: (
                song.title.lower(),
                song.artist.lower(),
                song.album.lower(),
                song.filename.lower(),
            ),
        )

    def album_groups(self):
        grouped = {}
        for song in self.library:
            key = song.album.strip()
            grouped.setdefault(key, []).append(song)

        summaries = []
        for key, songs in grouped.items():
            artists = {song.artist.strip() for song in songs if song.artist.strip()}
            if len(artists) == 1:
                artist_label = next(iter(artists))
            elif len(artists) > 1:
                artist_label = "Various Artists"
            else:
                artist_label = ""

            summaries.append(
                AlbumSummary(
                    key=key,
                    title=key or "Singles / Unassigned",
                    artist_label=artist_label or "Unknown Artist",
                    song_count=len(songs),
                )
            )

        return sorted(
            summaries,
            key=lambda album: (album.key == "", album.title.lower(), album.artist_label.lower()),
        )

    def album_songs(self, album_key):
        key = album_key.strip()
        return sorted(
            [song for song in self.library if song.album.strip() == key],
            key=lambda song: (song.artist.lower(), song.title.lower(), song.filename.lower()),
        )

    def album_queue(self, album_key):
        return [song.id for song in self.album_songs(album_key)]

    def import_files(self, file_paths):
        imported_count = 0

        for raw_path in file_paths:
            source = Path(raw_path)
            suffix = source.suffix.lower()
            if suffix not in SUPPORTED_EXTENSIONS:
                continue

            target = unique_path(self.paths.songs_dir, sanitize_name(source.stem), suffix)
            shutil.copy2(source, target)
            imported_count += 1

        self.sync_library_with_folder()
        self.save_library()
        return imported_count

    def import_album(self, directory, album_name, artist=""):
        source_dir = Path(directory)
        if not source_dir.is_dir():
            raise ValueError("Choose a valid album folder.")

        imported_filenames = []
        for source in sorted(source_dir.rglob("*")):
            if not source.is_file() or source.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            target = unique_path(self.paths.songs_dir, sanitize_name(source.stem), source.suffix.lower())
            shutil.copy2(source, target)
            imported_filenames.append(target.name)

        if not imported_filenames:
            raise ValueError("No supported audio files were found in that folder.")

        album_name = album_name.strip()
        artist = artist.strip()
        imported_filename_set = set(imported_filenames)

        self.sync_library_with_folder()
        imported_songs = []
        for song in self.library:
            if song.filename not in imported_filename_set:
                continue

            song.album = album_name
            if artist:
                song.artist = artist
            imported_songs.append(song)

        self.save_library()
        return imported_songs

    def remove_songs(self, song_ids):
        removed_songs = []
        failures = []
        song_id_set = set(song_ids)

        for song in [song for song in self.library if song.id in song_id_set]:
            path = self.song_path(song)
            try:
                if path.exists():
                    path.unlink()
            except OSError as exc:
                failures.append(f"{song.title}: {exc}")
                continue

            removed_songs.append(song)

        removed_ids = {song.id for song in removed_songs}
        if removed_ids:
            self.library = [song for song in self.library if song.id not in removed_ids]
            for name in self.playlists:
                self.playlists[name] = [song_id for song_id in self.playlists[name] if song_id not in removed_ids]
            self.save_library()
            self.save_playlists()

        return removed_songs, failures

    def rename_song(self, song_id, new_title):
        song = self.get_song(song_id)
        if song is None:
            raise ValueError("Song not found.")

        current_path = self.song_path(song)
        if not current_path.exists():
            raise FileNotFoundError(f"{song.title}: source file is missing")

        clean_title = sanitize_name(new_title)
        new_path = unique_path(self.paths.songs_dir, clean_title, current_path.suffix.lower(), current_path=current_path)
        if current_path != new_path:
            current_path.rename(new_path)

        song.title = clean_title
        song.filename = new_path.name
        self.save_library()
        return song

    def batch_rename(self, song_ids, base_title):
        renamed_songs = []
        failures = []
        songs = [song for song in self.sorted_songs() if song.id in set(song_ids)]
        width = max(2, len(str(len(songs))))
        clean_base = sanitize_name(base_title)

        for index, song in enumerate(songs, start=1):
            new_title = f"{clean_base} {index:0{width}d}"
            current_path = self.song_path(song)
            if not current_path.exists():
                failures.append(f"{song.title}: source file is missing")
                continue

            new_path = unique_path(self.paths.songs_dir, new_title, current_path.suffix.lower(), current_path=current_path)
            try:
                if current_path != new_path:
                    current_path.rename(new_path)
            except OSError as exc:
                failures.append(f"{song.title}: {exc}")
                continue

            song.title = new_title
            song.filename = new_path.name
            renamed_songs.append(song)

        if renamed_songs:
            self.save_library()

        return renamed_songs, failures

    def update_artist(self, song_ids, artist):
        updated_songs = []
        artist = artist.strip()
        song_id_set = set(song_ids)

        for song in self.library:
            if song.id in song_id_set:
                song.artist = artist
                updated_songs.append(song)

        if updated_songs:
            self.save_library()

        return updated_songs

    def update_album(self, song_ids, album):
        updated_songs = []
        album = album.strip()
        song_id_set = set(song_ids)

        for song in self.library:
            if song.id in song_id_set:
                song.album = album
                updated_songs.append(song)

        if updated_songs:
            self.save_library()

        return updated_songs

    def create_playlist(self, name):
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Playlist name cannot be empty.")

        existing = {playlist_name.casefold() for playlist_name in self.playlists}
        if clean_name.casefold() in existing:
            raise ValueError("A playlist with that name already exists.")

        self.playlists[clean_name] = []
        self.save_playlists()
        return clean_name

    def delete_playlist(self, name):
        if name not in self.playlists:
            raise KeyError(name)

        del self.playlists[name]
        self.save_playlists()

    def rename_playlist(self, old_name, new_name):
        if old_name not in self.playlists:
            raise KeyError(old_name)

        clean_name = new_name.strip()
        if not clean_name:
            raise ValueError("Playlist name cannot be empty.")

        if clean_name.casefold() != old_name.casefold():
            existing = {playlist_name.casefold() for playlist_name in self.playlists}
            if clean_name.casefold() in existing:
                raise ValueError("A playlist with that name already exists.")

        song_ids = self.playlists.pop(old_name)
        self.playlists[clean_name] = song_ids
        self.save_playlists()
        return clean_name

    def playlist_songs(self, name):
        songs = []
        for song_id in self.playlists.get(name, []):
            song = self.get_song(song_id)
            if song:
                songs.append(song)
        return songs

    def add_songs_to_playlist(self, playlist_name, song_ids):
        if playlist_name not in self.playlists:
            raise KeyError(playlist_name)

        playlist = self.playlists[playlist_name]
        added_count = 0
        for song_id in song_ids:
            if song_id in playlist:
                continue

            if self.get_song(song_id) is None:
                continue

            playlist.append(song_id)
            added_count += 1

        if added_count:
            self.save_playlists()

        return added_count

    def remove_song_from_playlist(self, playlist_name, song_id):
        if playlist_name not in self.playlists:
            raise KeyError(playlist_name)

        self.playlists[playlist_name] = [item for item in self.playlists[playlist_name] if item != song_id]
        self.save_playlists()
        return self.get_song(song_id)

    def export_playlist(self, playlist_name, destination):
        songs = self.playlist_songs(playlist_name)
        if not songs:
            raise ValueError("Add songs to the playlist before exporting it.")

        return export_playlist_bundle(playlist_name, songs, destination, self.paths.songs_dir)
