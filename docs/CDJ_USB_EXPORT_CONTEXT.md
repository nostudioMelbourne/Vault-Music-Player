# CDJ USB export: implementation and handoff context

## Agreed goal

Vault should export selected playlists and audio directly to a USB, with BPM,
beatgrids, and player-readable waveforms prepared in advance. Rekordbox must not
be required to create the finished export. The eventual target is all players
that read Rekordbox USB libraries, limited by each player's actual capabilities.
The user can currently test on an XDJ-700, not a OneLibrary player.

User decisions:

- Start with a USB without an existing Pioneer library. Update only Vault-managed
  exports later; do not merge another application's device library.
- Preserve compatible source audio and convert incompatible export copies to
  broadly supported PCM WAV. Never change the library originals.
- Analyse automatically, with decimal BPM, half/double tempo, and first-beat
  alignment controls for correcting the result before export.
- Require hardware acceptance tests. Parser success alone is not proof of playback.
- Work on one focused branch and PR at a time.

## Delivery stages

1. **Export proof** (`feature/cdj-export-proof`): a standalone, synthetic playlist
   with known audio, tempo, beat times, traditional `export.pdb`, and `.DAT`/`.EXT`
   analysis. Validate generated files, then test on the XDJ-700. No app UI changes.
2. **Track preparation**: real library tracks, compatible export copies, persistent
   analysis, decimal BPM, and beatgrid review. Cache against actual exported audio.
3. **Complete exporter**: OneLibrary and its waveform variants, multiple playlists,
   stable IDs, Vault-managed updates, staging, recovery, and source-change handling.
4. **App integration**: USB selection/preflight, progress, cancellation, and accurate
   success/failure reporting in the existing Tkinter interface.

Do not jump to the next stage before the current stage is reviewed and its
acceptance gate passes. The all-player objective is not complete when the proof
works on one XDJ-700.

## Starting checkout and ownership

This worktree starts from merged main `d2602fd` (AIFF PR #28 is merged; dialog PR
#26 is also merged). The primary checkout remains on `feature/safer-song-removal`
with unrelated changes to `Vault Music.spec`, `scripts/`, and `website/`. Do not
reset, stash, stage, or overwrite those changes. Confirm status and worktree
ownership before any branch, commit, push, or PR operation.

## Current proof contract

- `create_probe_export(output_directory)` creates a new standalone export folder.
  It must refuse an existing output path; it does not write to a mounted USB root,
  format a drive, read the user's music, or modify an existing library.
- `scripts/export_cdj_probe.py OUTPUT_DIRECTORY` is the developer/manual test entry.
  Copy the generated `Contents` and `PIONEER` folders to the root of a spare,
  appropriately formatted USB for testing. Do not replace existing folders.
- The probe uses 44.1 kHz stereo 16-bit PCM WAV, known 4/4 beats, and includes
  fractional-tempo and leading-silence cases. Its grid is derived from the fixture
  definition, not from Vault's current BPM estimator.
- A manifest records expected tracks, tempos, beats, file checksums, and explicitly
  marks hardware compatibility as unverified. No OneLibrary is emitted in stage 1.

## Format notes and verification boundaries

The traditional database is a page-based DeviceSQL binary file. Track metadata,
playlist membership, audio paths, and analysis paths must agree. Analysis files
are big-endian PMAI containers. Their PPTH audio path includes a UTF-16BE NUL
terminator. PQTZ encodes each beat's bar position, BPM multiplied by 100, and time
in milliseconds. Compact and scrolling waveforms are separate representations.

Hardware-specific reference notes and independent parsers disagree on some
undocumented fields, including history-table expectations and page counters.
Record parser results and hardware observations separately. Do not fabricate
played-track history or copy another person's database to make a header pass.
If the player rejects the proof, retain its error and generated files for a
focused follow-up on this same milestone.

Vault currently stores integer BPM and builds display waveforms transiently.
Neither is sufficient for a reviewed, persistent DJ beatgrid. The later model
migration must read old integer values without truncating new decimal values.
Tempo-varying or uncertain tracks must be flagged for review rather than silently
exported with an invented constant grid. Initial editing targets steady-tempo 4/4.

Later production export should validate FAT32/MBR for broad legacy compatibility,
space, file-size limits, source availability, and export ownership. It must stage
and validate before publishing, preserve unrelated files, and recover from drive
disconnects or incomplete updates. Bundled native OneLibrary support must work
without an installed Rekordbox or a user's Homebrew installation.

## Verification commands

Use the existing development interpreter, or an equivalent environment with
`requirements.txt` installed:

```sh
python -m unittest discover -s tests -p 'test_cdj_*.py' -v
python -m unittest discover -s tests -v
git diff --check
python scripts/export_cdj_probe.py /tmp/vault-cdj-probe
```

An independent database parser is available as the MIT-licensed
`fragmede/rekordbox-pdb` repository. The research revision is
`ee3bac2f22ca11a5ce61eea35f8cb951c246eaef`. Its advertised PyPI name was unavailable
during this work; install that exact Git revision into a temporary tools directory
for validation, not into Vault's application requirements.

For independent analysis validation, also install `pyrekordbox==0.4.4` and
`construct==2.10.70` with `--no-deps` into that tools directory. The tests load only
pyrekordbox's standalone ANLZ structures; they do not initialize its desktop
database/configuration modules or require SQLCipher. Application requirements
are unchanged. Without the tools, the three independent-reader tests skip.

```sh
python -m pip install --no-deps --target /tmp/vault-cdj-proof-validation \
  git+https://github.com/fragmede/rekordbox-pdb.git@ee3bac2f22ca11a5ce61eea35f8cb951c246eaef
python -m pip install --no-deps --target /tmp/vault-cdj-proof-validation \
  pyrekordbox==0.4.4 construct==2.10.70
PYTHONPATH=/tmp/vault-cdj-proof-validation python -m unittest discover -s tests -p 'test_cdj_*.py' -v
```

## Hardware acceptance checklist

Record model, firmware, USB filesystem/partition scheme, and the tested commit.
On the XDJ-700: browse the playlist; check titles and order; load every probe;
confirm expected BPM; check overview and scrolling waveforms; play, seek, and
test quantized 4-beat loops across several bars. Check the fractional-tempo and
leading-silence fixtures for drift or offsets. Preserve any new analysis files
the player writes: they can reveal rejection/re-analysis of the supplied files.

An XDJ-700 pass establishes only that tested Device Library path. OneLibrary
requires a separate compatible player and acceptance record. Older/smaller
players cannot display features their hardware does not implement.

## Scope exclusions

Hot cues, key analysis, merging Rekordbox libraries, automatic formatting,
network/PRO DJ LINK export, and universal compatibility claims are out of scope
for the proof. Keep the current M3U8/portable audio export working.

## References

- Official library formats and compatibility: https://rekordbox.com/en/support/usb-export/
- USB guide: https://cdn.rekordbox.com/files/20251021171528/USB_export_guide_en_251007.pdf
- DeviceSQL database: https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/exports.html
- Analysis files: https://djl-analysis.deepsymmetry.org/rekordbox-export-analysis/anlz.html
- Independent format specifications: https://github.com/Deep-Symmetry/crate-digger/tree/main/src/main/kaitai
- Hardware observations (not universal guarantees): https://github.com/morizkraemer/fourfour/blob/master/pioneer-usb-writer/reference-code/PIONEER.md
- Independent database reader: https://github.com/fragmede/rekordbox-pdb
- pyrekordbox ANLZ reader (not a turnkey exporter): https://github.com/dylanljones/pyrekordbox
- Independent hash cross-check: https://github.com/M-Igashi/baken/issues/115

## Evidence and next action

Implemented the standalone proof writer, CLI, and tests. All 18 proof tests pass
with the independent readers installed. The full suite runs 66 tests: 59 pass and
seven opt-in native GUI/audio tests skip. `git diff --check` passes. No application
UI, runtime dependencies, or existing portable export behavior changed.

Generated manual-test artifact: `/private/tmp/vault-cdj-usb-proof`. It contains
three stereo 16-bit WAVs, six analysis files, `export.pdb`, and a manifest recording
checksums and expected grids. Hardware results remain pending; no USB has been
modified. The next action is the XDJ-700 acceptance test, not stage 2 development.

The third Huerta hash vector in the fourfour reference is inconsistent with its
algorithm: the stated input computes `P028/0000F098`, not `P012/0000530C`. The
independent baken research reports this same source error and agreement with 586
real exported track paths. Tests use the corrected value; no special-case path
mapping was added to make the incorrect vector pass.

The proof deliberately has empty index-only columns/history tables and no player
settings export. The parser checks do not settle whether a given firmware needs
additional catalog/history initialization. It emits only the blue/monochrome
waveforms used by the initial legacy probe; RGB/three-band variants are later
work. Retain any XDJ-700 rejection or re-analysis evidence before changing these
unknowns. Do not describe this as a production-ready or universal USB exporter.
