"""PlantUML text encoding for server requests."""
from __future__ import annotations

import base64
import zlib


PLANTUML_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"


def _encode_6bit(b: int) -> str:
    if b < 0 or b > 63:
        raise ValueError("6-bit value out of range")
    return PLANTUML_ALPHABET[b]


def _append_3bytes(b1: int, b2: int, b3: int) -> str:
    c1 = b1 >> 2
    c2 = ((b1 & 0x3) << 4) | (b2 >> 4)
    c3 = ((b2 & 0xF) << 2) | (b3 >> 6)
    c4 = b3 & 0x3F
    return (
        _encode_6bit(c1)
        + _encode_6bit(c2)
        + _encode_6bit(c3)
        + _encode_6bit(c4)
    )


def plantuml_encode(text: str) -> str:
    """Encode PlantUML text for the server URL."""
    compressed = zlib.compress(text.encode("utf-8"))
    # Remove zlib header and checksum for PlantUML compatibility
    data = compressed[2:-4]
    res = []
    for i in range(0, len(data), 3):
        b1 = data[i]
        b2 = data[i + 1] if i + 1 < len(data) else 0
        b3 = data[i + 2] if i + 2 < len(data) else 0
        res.append(_append_3bytes(b1, b2, b3))
    return "".join(res)
