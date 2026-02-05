"""File utilities."""
from __future__ import annotations

from pathlib import Path


def ensure_dir(path: str) -> Path:
    """Ensure directory exists and return Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


# Conservative binary extensions that we should not attempt to decode as UTF-8
BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".webp",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".pdf",
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".mp3",
    ".wav",
}


def _looks_binary(path: Path) -> bool:
    """Heuristic check whether a file is binary by extension and by inspecting bytes."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(512)
            if not chunk:
                return False
            if b"\x00" in chunk:
                return True
            if chunk.startswith(b"\x89PNG"):
                return True
            if chunk.startswith(b"\xff\xd8\xff"):
                return True
            if chunk.startswith(b"GIF8"):
                return True
            if chunk.startswith(b"PK\x03\x04"):
                return True
    except Exception:
        # If we can't read the file for some reason, treat as binary to avoid crashes
        return True
    return False


def read_text_file(path: str) -> str:
    """Safely read a file as UTF-8 with fallbacks.

    - If the file looks binary, raises a ValueError so callers can handle it.
    - Tries a strict UTF-8 read first, then falls back to UTF-8 with errors="ignore".
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    if _looks_binary(p):
        raise ValueError(f"Binary file: {p.name}")
    try:
        return p.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            raise ValueError(f"Unable to read text file: {p.name}")
