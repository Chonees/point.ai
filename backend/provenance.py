from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_git(args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        value = completed.stdout.strip()
        return value or None
    except Exception:
        return None


@lru_cache(maxsize=1)
def build_code_provenance() -> dict[str, Any]:
    commit_sha = _safe_git(["rev-parse", "HEAD"])
    branch = _safe_git(["rev-parse", "--abbrev-ref", "HEAD"])
    return {
        "repo_root": str(ROOT_DIR),
        "git_commit_sha": commit_sha,
        "git_commit_short": commit_sha[:12] if commit_sha else None,
        "git_branch": branch,
    }


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=64)
def _file_provenance_cached(path_str: str) -> dict[str, Any]:
    path = Path(path_str)
    exists = path.exists()
    info: dict[str, Any] = {
        "path": str(path),
        "exists": exists,
        "file_name": path.name,
    }
    if not exists:
        info.update(
            {
                "size_bytes": None,
                "modified_at_utc": None,
                "sha256": None,
            }
        )
        return info

    stat = path.stat()
    info.update(
        {
            "size_bytes": int(stat.st_size),
            "modified_at_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "sha256": _file_sha256(path),
        }
    )
    return info


def build_file_provenance(path: Path | str) -> dict[str, Any]:
    return dict(_file_provenance_cached(str(Path(path).resolve())))
