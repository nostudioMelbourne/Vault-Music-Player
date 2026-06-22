# Vault Music System Architecture

Vault Music is a local-first macOS desktop audio-library app. The application is a single Python process with a Tkinter UI, a local JSON-backed library, copied audio files in Application Support, and macOS-native playback through `NSSound`.

## System Context

```mermaid
flowchart LR
    user[User] --> app[Vault Music Desktop App]
    finder[macOS Finder / File Dialogs] --> app

    app --> appkit[macOS AppKit NSSound]
    app --> afconvert[macOS afconvert]
    app --> localdata[(Application Support Data)]
    app --> exportfolder[(User-selected Export Folder)]

    localdata --> libraryjson[library.json]
    localdata --> playlistsjson[playlists.json]
    localdata --> songsdir[songs/ copied audio files]

    app --> assets[Bundled app assets]
```

## Component Architecture

```mermaid
flowchart TD
    main[main.py<br/>Process entry point] --> ui[AudioPlayerApp<br/>audio_player.app]

    subgraph UI["Tkinter Desktop UI"]
        ui --> songsview[Songs view]
        ui --> albumsview[Albums view]
        ui --> playlistview[Playlist sidebar]
        ui --> transport[Transport controls]
        ui --> waveformcanvas[Waveform canvas]
        ui --> spectrumcanvas[Spectrum analyser canvas]
    end

    subgraph Domain["Application Domain"]
        library[LibraryManager<br/>audio_player.library]
        models[Song and AlbumSummary<br/>audio_player.models]
        exporter[Playlist bundle exporter<br/>audio_player.exporter]
        utils[Formatting and path helpers<br/>audio_player.utils]
    end

    subgraph Services["Platform / Analysis Services"]
        playback[NSSoundBackend<br/>audio_player.playback]
        waveform[Waveform peak builder<br/>audio_player.waveform]
        spectral[Spectrum FFT builder<br/>audio_player.spectral]
        bpm[BPM analyzer<br/>audio_player.bpm]
        config[Path builder<br/>audio_player.config]
    end

    subgraph Storage["Local Storage"]
        appdata[(~/Library/Application Support/AudioPlayer<br/>or AUDIOPLAYER_DATA_DIR)]
        songs[(songs/)]
        librarydb[(library.json)]
        playlistdb[(playlists.json)]
        legacy[(legacy songs/ and playlists/)]
    end

    subgraph External["External Dependencies"]
        nssound[macOS AppKit NSSound]
        afconvert[/usr/bin/afconvert]
        numpy[NumPy]
        pyobjc[PyObjC Cocoa bridge]
    end

    ui --> library
    ui --> playback
    ui --> waveform
    ui --> spectral
    ui --> bpm
    ui --> config
    ui --> assets[assets/app_icon.*]

    library --> models
    library --> exporter
    library --> utils
    library --> appdata
    library --> songs
    library --> librarydb
    library --> playlistdb
    library --> legacy

    exporter --> utils
    exporter --> songs
    exporter --> exportdir[(Export playlist folder)]

    config --> appdata
    playback --> nssound
    playback --> pyobjc
    waveform --> afconvert
    spectral --> afconvert
    spectral --> numpy
    bpm --> afconvert
    bpm --> numpy
```

## Runtime Flows

### Startup And State Sync

```mermaid
sequenceDiagram
    actor User
    participant Main as main.py
    participant App as AudioPlayerApp
    participant Config as build_paths()
    participant Library as LibraryManager
    participant Disk as Application Support

    User->>Main: Launch app
    Main->>App: Create Tk root and app
    App->>Config: Resolve paths
    Config-->>App: AppPaths
    App->>Library: Initialize with paths
    Library->>Disk: Ensure app data and songs folders
    Library->>Disk: Import legacy songs if needed
    Library->>Disk: Read library.json and playlists.json
    Library->>Disk: Sync JSON library with songs/
    Library-->>App: Loaded library and playlists
    App->>App: Build UI and refresh views
```

### Import Songs Or Albums

```mermaid
sequenceDiagram
    actor User
    participant App as AudioPlayerApp
    participant Library as LibraryManager
    participant Disk as songs/ and JSON state

    User->>App: Choose audio files or album folder
    App->>Library: import_files() or import_album()
    Library->>Disk: Copy supported .mp3, .wav, .flac files
    Library->>Disk: Generate unique safe filenames
    Library->>Library: Sync Song records with copied files
    Library->>Disk: Save library.json
    Library-->>App: Imported song records
    App->>App: Refresh Songs, Albums, and Playlist views
```

### Playback And Waveform

```mermaid
sequenceDiagram
    actor User
    participant App as AudioPlayerApp
    participant Library as LibraryManager
    participant Player as NSSoundBackend
    participant Analysis as audio analysis worker thread
    participant AppKit as macOS NSSound
    participant Disk as songs/

    User->>App: Play selected song
    App->>Library: Resolve Song and file path
    Library-->>App: Song path under songs/
    App->>Player: play(path)
    Player->>AppKit: Load and play with NSSound
    App->>Analysis: Start daemon thread
    Analysis->>Disk: Read WAV or convert with afconvert
    Analysis-->>App: Schedule waveform peaks on Tk event loop
    Analysis->>Analysis: Calculate log-frequency FFT frames
    Analysis-->>App: Schedule synchronized spectrum data
    App->>Library: increment_play_count()
    Library->>Disk: Save library.json
    App->>App: Poll playback every 250 ms and advance queue on finish
```

### BPM Analysis

```mermaid
sequenceDiagram
    actor User
    participant App as AudioPlayerApp
    participant Worker as BPM worker thread
    participant Analyzer as audio_player.bpm
    participant Library as LibraryManager
    participant Disk as songs/ and library.json

    User->>App: Analyze BPM for selected songs
    App->>Worker: Start daemon thread
    loop Each selected song
        Worker->>Analyzer: analyze_bpm(path)
        Analyzer->>Analyzer: Convert non-WAV with afconvert
        Analyzer->>Analyzer: Estimate tempo with NumPy
    end
    Worker-->>App: Schedule results on Tk event loop
    App->>Library: update_bpm(song_id, bpm)
    Library->>Disk: Save library.json
    App->>App: Refresh visible song rows
```

### Playlist Export

```mermaid
sequenceDiagram
    actor User
    participant App as AudioPlayerApp
    participant Library as LibraryManager
    participant Exporter as export_playlist_bundle()
    participant Source as songs/
    participant Target as Export folder

    User->>App: Export selected playlist
    App->>Library: export_playlist(name, destination)
    Library->>Library: Resolve playlist song ids to Song records
    Library->>Exporter: Build bundle
    Exporter->>Source: Read source audio files
    Exporter->>Target: Copy songs into playlist folder
    Exporter->>Target: Write .m3u8 playlist file
    Exporter-->>App: Export path, playlist file, missing files
```

## Data Model

```mermaid
erDiagram
    SONG {
        string id
        string filename
        string title
        string artist
        string album
        int play_count
        int bpm
    }

    PLAYLIST {
        string name
        string song_ids
    }

    ALBUM_SUMMARY {
        string key
        string title
        string artist_label
        int song_count
    }

    PLAYLIST }o--o{ SONG : contains
    ALBUM_SUMMARY ||--o{ SONG : groups_by_album
```

## Storage Layout

```text
~/Library/Application Support/AudioPlayer/
  library.json       # serialized Song records
  playlists.json     # playlist name -> ordered song id list
  songs/             # copied local audio files used by the app
```

`AUDIOPLAYER_DATA_DIR` can override the Application Support directory for development and testing.

## Key Responsibilities

| Module | Responsibility |
| --- | --- |
| `main.py` | Starts the Tkinter application. |
| `audio_player.app` | Owns UI state, event handling, queue behavior, playback polling, drag/drop interactions, and worker-thread result dispatch. |
| `audio_player.config` | Resolves app data paths, supported file extensions, legacy paths, and icon candidates. |
| `audio_player.library` | Imports files, synchronizes disk state, manages songs/albums/playlists, persists JSON, and delegates playlist export. |
| `audio_player.models` | Defines `Song` and `AlbumSummary` data structures. |
| `audio_player.playback` | Wraps macOS `NSSound` playback, pause/resume, stop, seek, duration, and completion detection. |
| `audio_player.waveform` | Produces normalized waveform peaks from WAV data and converts non-WAV files with `afconvert`. |
| `audio_player.spectral` | Produces normalized log-frequency FFT frames for the synchronized spectrum analyser. |
| `audio_player.bpm` | Estimates BPM using PCM analysis and NumPy, with `afconvert` conversion for non-WAV files. |
| `audio_player.exporter` | Copies playlist audio files and writes portable `.m3u8` playlist bundles. |
| `audio_player.utils` | Provides sanitization, unique path generation, song labels, and time formatting. |

## Deployment Shape

The app runs from source with `python main.py` or can be packaged as a macOS app bundle using `pyinstaller "Vault Music.spec"`. Runtime data remains outside the bundle in the configured Application Support directory.
