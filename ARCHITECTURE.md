# Architecture

```mermaid
flowchart TD
    user[User] --> ui[Tkinter Desktop UI<br/>audio_player.app.AudioPlayerApp]

    ui --> library[Library Manager<br/>audio_player.library.LibraryManager]
    ui --> playback[Playback Backend<br/>audio_player.playback.NSSoundBackend]
    ui --> waveform[Waveform Builder<br/>audio_player.waveform.build_waveform_peaks]
    ui --> bpm[BPM Analyzer<br/>audio_player.bpm.analyze_bpm]
    ui --> exporter[Playlist Exporter<br/>audio_player.exporter]

    library --> models[Data Models<br/>audio_player.models]
    library --> utils[Utilities<br/>audio_player.utils]
    exporter --> utils

    library --> appdata[(Application Support Data<br/>library.json<br/>playlists.json<br/>songs/)]
    exporter --> exportdir[(User-selected export folder)]

    playback --> nssound[macOS AppKit NSSound]
    waveform --> afconvert[macOS afconvert]
    bpm --> afconvert
    bpm --> numpy[NumPy]

    config[Path Configuration<br/>audio_player.config.build_paths] --> library
    config --> ui
    config --> appdata

    assets[App Assets<br/>assets/app_icon.*] --> ui

    main[Entry Point<br/>main.py] --> ui
```

## Runtime Flow

1. `main.py` starts the Tkinter desktop app.
2. `AudioPlayerApp` builds the interface and coordinates user actions.
3. `LibraryManager` loads and saves local library state under `~/Library/Application Support/AudioPlayer` unless `AUDIOPLAYER_DATA_DIR` is set.
4. Playback is delegated to macOS `NSSound` through `NSSoundBackend`.
5. Waveform and BPM helpers convert non-WAV audio with macOS `afconvert`; BPM estimation also uses NumPy.
6. Playlist exports copy selected audio files and write playlist metadata to a user-selected folder.
