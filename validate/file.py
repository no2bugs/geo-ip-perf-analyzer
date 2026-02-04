"""File utility helpers."""

from pathlib import Path


def exists(fle):
    """Return True if a path exists and is a file."""
    return Path(fle).is_file()
