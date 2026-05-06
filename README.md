# Vault Music

Vault Music is a small macOS desktop music-library app for local audio files. It imports songs, groups albums, manages playlists, shows waveform progress, estimates BPM when NumPy is available, and exports playlists as portable bundles.

## Requirements

- macOS
- Python 3.13 or later
- Tkinter support in the Python build
- `afconvert`, included with macOS, for waveform/BPM analysis of non-WAV files

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run From Source

```sh
python main.py
```

By default, user data is stored in `~/Library/Application Support/AudioPlayer`. For development or testing, set `AUDIOPLAYER_DATA_DIR`:

```sh
AUDIOPLAYER_DATA_DIR=.appdata python main.py
```

## Build The macOS App

```sh
pyinstaller "Vault Music.spec"
```

Generated app bundles, archives, build directories, local songs, and local app data are intentionally ignored by git.
