"""GitHub repository ingestion and lightweight analysis."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import urlparse, urlunparse

EXCLUDE_DIRS = {
    ".git",
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".venv",
    "__pycache__",
    ".pytest_cache",
}

KEY_FILES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "kustomization.yaml",
    "kustomization.yml",
    "Chart.yaml",
    "values.yaml",
}

LANGUAGE_EXT = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".php": "PHP",
    ".cs": "C#",
}


def _run(cmd: List[str], cwd: str | None = None) -> str:
    result = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, text=True)
    return result.stdout.strip()


def _normalize_repo_url(repo_url: str) -> str:
    parsed = urlparse(repo_url.strip())
    cleaned = parsed._replace(fragment="", query="")
    normalized = urlunparse(cleaned).rstrip("/")
    return normalized


def clone_repo(repo_url: str) -> Tuple[str, str]:
    temp_dir = tempfile.mkdtemp(prefix="archviz_repo_")
    safe_url = _normalize_repo_url(repo_url)
    _run(["git", "clone", "--depth", "1", safe_url, temp_dir])
    commit = _run(["git", "rev-parse", "HEAD"], cwd=temp_dir)
    return temp_dir, commit


def analyze_repo(repo_path: str, repo_url: str, commit: str) -> Dict[str, object]:
    root = Path(repo_path)
    repo_name = re.sub(r"\.git$", "", repo_url.rstrip("/").split("/")[-1])

    top_dirs = [p.name for p in root.iterdir() if p.is_dir() and p.name not in EXCLUDE_DIRS]
    key_files: List[str] = []
    language_counts: Counter[str] = Counter()
    services: List[str] = []
    entrypoints: List[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for filename in filenames:
            rel = Path(dirpath, filename).relative_to(root).as_posix()
            if filename in KEY_FILES:
                key_files.append(rel)
            ext = Path(filename).suffix
            if ext in LANGUAGE_EXT:
                language_counts[LANGUAGE_EXT[ext]] += 1
            if filename in {"main.py", "app.py", "server.py", "index.js", "index.ts", "main.go"}:
                entrypoints.append(rel)

        if "package.json" in filenames or "pyproject.toml" in filenames:
            services.append(Path(dirpath).relative_to(root).as_posix())

    services = sorted(set([s for s in services if s and s != "."]))

    summary = {
        "repo_url": repo_url,
        "repo_name": repo_name,
        "commit": commit,
        "top_level_dirs": sorted(top_dirs),
        "key_files": sorted(key_files),
        "languages": dict(language_counts.most_common(8)),
        "services": services,
        "entrypoints": sorted(set(entrypoints)),
    }

    content_lines = [
        f"Repository: {repo_name}",
        f"URL: {repo_url}",
        f"Commit: {commit}",
        f"Top-level directories: {', '.join(summary['top_level_dirs']) or 'none'}",
        f"Key files: {', '.join(summary['key_files']) or 'none'}",
        f"Languages: {', '.join([f"{k}({v})" for k, v in summary['languages'].items()]) or 'unknown'}",
        f"Services (monorepo roots): {', '.join(summary['services']) or 'none'}",
        f"Entrypoints: {', '.join(summary['entrypoints']) or 'none'}",
    ]

    return {"summary": summary, "content": "\n".join(content_lines)}


def ingest_github_repo(repo_url: str) -> Dict[str, object]:
    repo_path = None
    normalized = _normalize_repo_url(repo_url)
    try:
        repo_path, commit = clone_repo(normalized)
        analysis = analyze_repo(repo_path, normalized, commit)
        return {
            "repo_url": normalized,
            "commit": commit,
            "summary": analysis["summary"],
            "content": analysis["content"],
        }
    finally:
        if repo_path and Path(repo_path).exists():
            shutil.rmtree(repo_path, ignore_errors=True)
