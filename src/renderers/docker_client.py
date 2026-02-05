"""Docker-based renderer client utilities."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List


def run_docker_renderer(image: str, workdir: Path, command: List[str]) -> None:
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{workdir}:/data",
        "-w",
        "/data",
        image,
    ] + command
    subprocess.run(cmd, check=True)
