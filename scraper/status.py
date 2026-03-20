"""
status.py  —  real-time scraping progress monitor.

Usage:
    python -m scraper.status
    python -m scraper.status --target 10000
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

from scraper.checkpoint import INDEX_FILE, VISITED_FILE

DEFAULT_TARGET  = 5000
REFRESH_SECS    = 5


def _load(path: Path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _bar(pct: float, width: int = 30) -> str:
    filled = int(width * pct)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def main() -> None:
    parser = argparse.ArgumentParser(description="Scraper status monitor")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET)
    args   = parser.parse_args()
    target = args.target

    prev_count = 0
    prev_time  = time.time()
    rates: list[float] = []

    print(f"Monitoring scraper... target={target}  (Ctrl+C to exit)\n")

    while True:
        idx     = _load(INDEX_FILE, [])
        visited = _load(VISITED_FILE, [])
        total   = len(idx)
        pct     = total / target if target else 0

        now     = time.time()
        elapsed = now - prev_time
        if elapsed >= REFRESH_SECS and total > prev_count:
            rate = (total - prev_count) / elapsed * 60
            rates.append(rate)
            if len(rates) > 6:
                rates.pop(0)
            prev_count = total
            prev_time  = now

        avg_rate = sum(rates) / len(rates) if rates else 0
        eta_min  = (target - total) / avg_rate if avg_rate > 0 else None
        by_source = Counter(e.get("source", "?") for e in idx)

        print("\033[H\033[J", end="")
        print("  FLOOR PLAN SCRAPER STATUS")
        print(f"  {'=' * 48}")
        print(f"  Progress : {total:,} / {target:,}  {_bar(pct)}  {pct * 100:.1f}%")
        if avg_rate:
            print(f"  Speed    : {avg_rate:.1f} imgs/min")
        else:
            print("  Speed    : calculating...")
        if eta_min:
            h, m = divmod(int(eta_min), 60)
            print(f"  ETA      : ~{h}h {m}min")
        else:
            print("  ETA      : calculating...")
        print(f"  Pages visited: {len(visited):,}")
        print()
        print("  By source:")
        for src, cnt in by_source.most_common():
            src_pct = cnt / (target // max(len(by_source), 1)) if target else 0
            print(f"    {src:<28} {cnt:>5}  {_bar(min(src_pct, 1), 15)}")
        print()

        if total >= target:
            print(f"  DONE — {total} images downloaded!")
            break

        time.sleep(REFRESH_SECS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMonitor closed.")
