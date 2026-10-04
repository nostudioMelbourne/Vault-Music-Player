from pathlib import Path


def move_to_trash(path):
    try:
        from Foundation import NSFileManager, NSURL
    except ImportError as exc:
        raise OSError("macOS Trash support is unavailable.") from exc

    file_url = NSURL.fileURLWithPath_(str(Path(path).resolve()))
    succeeded, _resulting_url, error = (
        NSFileManager.defaultManager().trashItemAtURL_resultingItemURL_error_(file_url, None, None)
    )
    if not succeeded:
        message = error.localizedDescription() if error else "The file could not be moved to Trash."
        raise OSError(str(message))
