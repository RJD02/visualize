"""OpenAI client utilities with httpx>=0.28 compatibility."""
from __future__ import annotations

import atexit
from functools import lru_cache

import httpx
from openai import OpenAI

from src.utils.config import settings


def _build_httpx_client() -> httpx.Client:
    """Create an httpx client without deprecated proxy kwargs."""
    client = httpx.Client(
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=120.0, pool=120.0),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        follow_redirects=True,
    )
    atexit.register(client.close)
    return client


@lru_cache(maxsize=1)
def get_openai_client() -> OpenAI:
    """Return a shared OpenAI client wired to the compatible httpx client."""
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is not set")
    http_client = _build_httpx_client()
    client = OpenAI(api_key=settings.openai_api_key, http_client=http_client)
    atexit.register(client.close)
    return client
