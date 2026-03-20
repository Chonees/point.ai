"""
downloader.py  —  image URL detection and download with retry/backoff.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
MIN_IMG_BYTES = 8_000
RETRY_DELAYS  = [2, 5, 10]

_session = requests.Session()
_session.headers.update({"User-Agent": UA})

# ---------------------------------------------------------------------------
# URL classifiers
# ---------------------------------------------------------------------------
_PLAN_SIGNALS = re.compile(
    r"(/plan[s]?/|/house-plan[s]?/|/home-plan[s]?/|/floor-plan[s]?/"
    r"|/model[s]?/|chp-|dhs-|thd-|/\d{4,}/|plan-\d|plan_\d)",
    re.I,
)
_SKIP_EXTS = re.compile(r"\.(css|js|xml|pdf|zip|svg|ico|woff|ttf|eot)$", re.I)
_IMG_EXTS  = re.compile(r"\.(jpg|jpeg|png)(\?.*)?$", re.I)
_FLOOR_URL = re.compile(
    r"floor.?plan|floorplan|fp[-_]|[-_]fp\.|main[-_]floor|first[-_]floor", re.I
)


def is_plan_link(href: str, base_netloc: str) -> bool:
    if not href or href.startswith("data:"):
        return False
    p = urlparse(href)
    if p.netloc and p.netloc != base_netloc:
        return False
    if _SKIP_EXTS.search(p.path):
        return False
    return bool(_PLAN_SIGNALS.search(p.path))


def is_floor_img(src: str, alt: str, alt_re: str) -> bool:
    if not src or src.startswith("data:") or not _IMG_EXTS.search(src):
        return False
    if re.search(alt_re, alt, re.I):
        return True
    return bool(_FLOOR_URL.search(src))


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def download(url: str, dest: Path) -> bool:
    """Download url to dest. Returns True on success, False otherwise."""
    if dest.exists() and dest.stat().st_size >= MIN_IMG_BYTES:
        return True
    for attempt, wait in enumerate([0] + RETRY_DELAYS):
        if wait:
            time.sleep(wait)
        try:
            r = _session.get(url, timeout=20, stream=True)
            if r.status_code == 404:
                return False
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if "image" not in ct and not _IMG_EXTS.search(url):
                return False
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            if tmp.stat().st_size < MIN_IMG_BYTES:
                tmp.unlink(missing_ok=True)
                return False
            tmp.replace(dest)
            return True
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (403, 410):
                return False
            print(f"    [retry {attempt + 1}] {e}")
        except Exception as e:
            print(f"    [retry {attempt + 1}] {e}")
    return False
