from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass
class Song:
    id: str
    filename: str
    title: str
    artist: str = ""
    album: str = ""
    play_count: int = 0

    @classmethod
    def from_dict(cls, payload):
        filename = str(payload.get("filename") or "")
        try:
            play_count = max(0, int(payload.get("play_count") or 0))
        except (TypeError, ValueError):
            play_count = 0

        return cls(
            id=str(payload.get("id") or uuid4().hex),
            filename=filename,
            title=str(payload.get("title") or Path(filename).stem),
            artist=str(payload.get("artist") or ""),
            album=str(payload.get("album") or ""),
            play_count=play_count,
        )

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "play_count": self.play_count,
        }


@dataclass(frozen=True)
class AlbumSummary:
    key: str
    title: str
    artist_label: str
    song_count: int
