import argparse
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audio_player.cdj_probe import create_probe_export


def main():
    parser = argparse.ArgumentParser(description="Create a synthetic Device Library export for XDJ-700 testing.")
    parser.add_argument("output_directory", type=Path, help="A new folder in an existing parent; existing paths are refused.")
    arguments = parser.parse_args()
    try:
        manifest = create_probe_export(arguments.output_directory)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Export failed: {error}\n")
    print(f"Created {len(manifest['tracks'])} synthetic tracks in {arguments.output_directory.absolute()}")
    print("Experimental Device Library proof: hardware compatibility is UNVERIFIED; OneLibrary is not included.")
    print("Copy Contents and PIONEER to the root of a spare FAT32/MBR USB with no existing Pioneer library.")
    print("Expected BPM: 120, 127.50, and 90; the 90 BPM track starts after two seconds of silence.")
    print("On the XDJ-700, check playlist order, playback, waveforms, seeking, and quantized four-beat loops.")


if __name__ == "__main__":
    main()
