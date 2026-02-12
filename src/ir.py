"""Shim for IR v2 and src.ir.* modules."""
from __future__ import annotations

import os as _os

from .ir_v2 import *  # noqa: F403

__path__ = [_os.path.join(_os.path.dirname(__file__), "ir")]
__all__: list[str] = []
