"""Input parsing and text extraction."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from docx import Document
from pypdf import PdfReader

# Common binary file extensions to skip
BINARY_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.webp', '.svg',  # images (svg is text but often in assets)
    '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',  # archives
    '.exe', '.dll', '.so', '.dylib', '.bin',  # executables/libraries
    '.pdf',  # handled separately
    '.docx', '.xlsx', '.pptx',  # Office docs (handled separately)
    '.mp4', '.avi', '.mov', '.mkv', '.webm',  # video
    '.mp3', '.wav', '.ogg', '.flac',  # audio
    '.pyc', '.pyo', '.class',  # compiled code
    '.ttf', '.otf', '.woff', '.woff2', '.eot',  # fonts
}


def _is_binary_file(path: Path) -> bool:
    """Check if a file is binary by examining its extension and content."""
    # Check extension first
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    
    # For unknown extensions, try reading first few bytes
    try:
        with open(path, 'rb') as f:
            chunk = f.read(512)
            # If there are null bytes or high ratio of non-text bytes, it's binary
            if b'\x00' in chunk:
                return True
            # Check for common binary signatures
            if chunk.startswith(b'\x89PNG'):  # PNG
                return True
            if chunk.startswith(b'\xff\xd8\xff'):  # JPEG
                return True
            if chunk.startswith(b'GIF8'):  # GIF
                return True
            if chunk.startswith(b'PK\x03\x04'):  # ZIP
                return True
    except Exception:
        return True  # If we can't read it, assume binary
    
    return False


def _read_docx(path: Path) -> str:
    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # If UTF-8 fails, try with error handling
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return f"[Binary file or unreadable content: {path.name}]"


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            parts.append(text)
    return "\n".join(parts)


def parse_files(file_paths: Iterable[str]) -> str:
    """Parse multiple files (.py/.js/.docx/etc.) into a single text blob."""
    parts = []
    for fp in file_paths:
        path = Path(fp)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {fp}")
        
        # Skip binary files that we can't process
        if _is_binary_file(path):
            # Skip silently or add a note
            continue
        
        header = f"\n# File: {path.name}\n"
        suffix = path.suffix.lower()
        if suffix == ".docx":
            content = _read_docx(path)
        elif suffix == ".pdf":
            content = _read_pdf(path)
        else:
            content = _read_text(path)
        parts.append(header + content)
    return "\n".join(parts)
