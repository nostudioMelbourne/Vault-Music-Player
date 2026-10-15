# Vault Music

Vault Music is a small macOS desktop music-library app for local audio files. It imports songs, supports Finder drag-and-drop for songs and album folders, groups albums, manages playlists, shows switchable spectrogram/transient progress, estimates BPM when NumPy is available, and exports playlists as portable bundles.

Supported audio files are MP3, WAV, FLAC, and AIFF (`.aif` and `.aiff`).

## Requirements

- macOS
- Python 3.13 or later
- Tkinter support in the Python build
- `afconvert`, included with macOS, for analyzer/BPM processing of non-WAV files

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

## Tests

Run the automated tests with `python -m unittest discover -s tests -v`.
On macOS, include the native dialog checks with:

```sh
VAULT_TEST_GUI=1 python -m unittest discover -s tests -v
```

The native checks briefly open test dialogs and exercise their themed buttons, keyboard controls, and input validation.

To verify native AIFF playback on macOS, run:

```sh
VAULT_TEST_AUDIO=1 python -m unittest discover -s tests -p test_aiff.py -v
```

The playback check uses silent AIFF files and confirms that macOS playback starts and advances.

## Convert Audio

Select songs, then choose **Edit > Convert Audio...**, or right-click a song in the songs, album tracks, or playlist view. Choose an output format and an existing destination folder (including a mounted USB).

Conversion uses macOS `afconvert` in the background with progress and cancellation. Output formats are 16-bit/24-bit WAV or AIFF, FLAC, AAC M4A (256 kbps), and Apple Lossless M4A. The encoder retains the source sample rate when supported; unsupported inputs or encoder settings are reported per file. MP3 encoding is not offered.

Originals and existing destination files are never overwritten. Completed copies are kept if you cancel; incomplete outputs are removed. Copies are not automatically imported, and library-only metadata (such as manually entered BPM) is not embedded. This is audio conversion, not a Pioneer device database or waveform export.

## Build The macOS App

```sh
pyinstaller "Vault Music.spec"
```

Generated app bundles, archives, build directories, local songs, and local app data are intentionally ignored by git.
