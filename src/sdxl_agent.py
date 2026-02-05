"""SDXL prompt generation and rendering via Hugging Face Inference API."""
from __future__ import annotations

import time
from pathlib import Path

import requests
from src.utils.config import settings
from src.utils.file_utils import ensure_dir


HF_SDXL_MODEL = "stabilityai/stable-diffusion-xl-base-1.0"
HF_ENDPOINT = f"https://api-inference.huggingface.co/models/{HF_SDXL_MODEL}"


def render_sdxl_image(prompt: str, output_name: str, retries: int = 3) -> str:
    if not settings.hf_api_token:
        raise ValueError("HF_API_TOKEN is not set")
    headers = {"Authorization": f"Bearer {settings.hf_api_token}"}
    payload = {"inputs": prompt}

    for attempt in range(retries):
        response = requests.post(HF_ENDPOINT, headers=headers, json=payload, timeout=120)
        if response.status_code == 503:
            data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            wait_time = float(data.get("estimated_time", 10))
            time.sleep(min(wait_time, 20))
            continue
        if response.status_code == 410:
            raise RuntimeError("SDXL model unavailable (410). Ensure your HF account has access and accepted model terms.")
        response.raise_for_status()
        image_bytes = response.content
        output_dir = ensure_dir(settings.output_dir)
        output_path = Path(output_dir) / f"{output_name}.png"
        output_path.write_bytes(image_bytes)
        return str(output_path)

    raise RuntimeError("SDXL model is still loading; please retry")
