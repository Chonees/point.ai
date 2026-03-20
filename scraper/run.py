"""
run.py  —  CLI entry point for the floor plan scraper.

Usage:
    python -m scraper                             # all sources, target=5000
    python -m scraper --sources houseplans        # one source
    python -m scraper --target 10000              # custom target
    python -m scraper --reset-visited             # clear checkpoint
"""
from __future__ import annotations

import argparse

from scraper.browser import scrape_source
from scraper.checkpoint import (
    OUTPUT_DIR,
    load_index,
    load_visited,
    save_visited,
)
from scraper.sources import SOURCES


def main() -> None:
    parser = argparse.ArgumentParser(description="Floor plan image scraper")
    parser.add_argument(
        "--sources", nargs="+",
        choices=list(SOURCES) + ["all"], default=["all"],
        help="Sources to scrape (default: all)",
    )
    parser.add_argument(
        "--target", type=int, default=5000,
        help="Total images to collect across all sources (default: 5000)",
    )
    parser.add_argument(
        "--reset-visited", action="store_true",
        help="Clear the visited-pages checkpoint and start fresh",
    )
    args = parser.parse_args()

    targets = list(SOURCES) if "all" in args.sources else args.sources

    # houseplans.com gets half the total target; rest split among other sources
    half = args.target // 2
    rest = args.target - half
    per_source_map: dict[str, int] = {"houseplans": half}
    others = [s for s in targets if s != "houseplans"]
    per_other = max(100, rest // len(others)) if others else 0
    for s in others:
        per_source_map[s] = per_other

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index         = load_index()
    existing_urls = {e.get("source_url", "") for e in index}
    visited_pages = set() if args.reset_visited else load_visited()

    print(f"Resuming: {len(index)} images already collected, "
          f"{len(visited_pages)} pages already visited")

    total_new = 0
    for sid in targets:
        per_source = per_source_map.get(sid, 100)
        already    = sum(1 for e in index if e.get("source") == sid)
        remaining  = per_source - already
        if remaining <= 0:
            print(f"\n[{SOURCES[sid]['label']}] already has {already} images, skipping")
            continue

        print(f"\n[{SOURCES[sid]['label']}] target={per_source} | have={already} | remaining={remaining}")
        try:
            n = scrape_source(sid, SOURCES[sid], remaining, index, existing_urls, visited_pages)
        except Exception as e:
            print(f"  [source failed] {e} — continuing with next source")
            n = 0

        total_new += n
        print(f"  Done: {n} new images from {SOURCES[sid]['label']}")

    print(f"\nFinished. {total_new} new images. Total: {len(index)}")


if __name__ == "__main__":
    main()
