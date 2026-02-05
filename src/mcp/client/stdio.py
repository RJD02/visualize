"""Minimal stdio client shim."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel


class StdioServerParameters(BaseModel):
    # minimal Pydantic-compatible placeholder
    pass


def stdio_client(*args: Any, **kwargs: Any) -> None:
    # placeholder - no-op
    return None
