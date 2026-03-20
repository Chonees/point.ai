"""
browser.py  —  Playwright browser automation for scraping plan pages.

Handles:
- Headless Chromium launch
- AJAX pagination (click "Next", detect URL/content change)
- Image harvesting from individual plan pages
- Auto-restart on browser crash
"""
from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

from scraper.checkpoint import OUTPUT_DIR, save_index, save_visited
from scraper.downloader import UA, download, is_floor_img, is_plan_link

PAGE_DELAY = 1.0  # seconds between page navigations


def scrape_source(
    source_id: str,
    cfg: dict,
    target: int,
    index: list[dict],
    existing_urls: set[str],
    visited_pages: set[str],
) -> int:
    """
    Scrape one source until `target` new images are collected.
    Mutates index, existing_urls, and visited_pages in-place.
    Returns number of new images collected.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout, Error as PWError

    label   = cfg["label"]
    out_dir = OUTPUT_DIR / source_id
    out_dir.mkdir(parents=True, exist_ok=True)
    alt_re    = cfg["img_alt_re"]
    collected = 0

    # ------------------------------------------------------------------
    def _make_fname(url: str) -> str:
        ext = Path(urlparse(url).path).suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png"):
            ext = ".jpg"
        return f"{source_id}_{len(existing_urls):07d}{ext}"

    def _harvest(page, page_url: str) -> int:
        nonlocal collected
        added = 0
        try:
            items = page.evaluate("""() =>
                Array.from(document.querySelectorAll('img')).map(i => ({
                    src: i.src || i.getAttribute('data-src') || i.getAttribute('data-lazy') || '',
                    alt: i.alt || ''
                }))
            """)
        except Exception:
            return 0

        scheme_host = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
        for item in items:
            if collected >= target:
                break
            src = item.get("src", "").strip()
            alt = item.get("alt", "").strip()
            if not is_floor_img(src, alt, alt_re):
                continue
            full = urljoin(scheme_host, src)
            if full in existing_urls:
                continue
            fname = _make_fname(full)
            dest  = out_dir / fname
            print(f"    >> {fname}  [{alt[:55]}]")
            if download(full, dest):
                index.append({
                    "source":       source_id,
                    "source_label": label,
                    "filename":     str(dest.relative_to(OUTPUT_DIR)),
                    "source_url":   full,
                    "page_url":     page_url,
                    "alt":          alt,
                })
                existing_urls.add(full)
                save_index(index)
                collected += 1
                added += 1
        return added

    def _nav(page, url: str, retries: int = 2) -> bool:
        for attempt in range(retries + 1):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=6_000)
                except PWTimeout:
                    pass
                time.sleep(PAGE_DELAY)
                return True
            except PWTimeout:
                return True
            except PWError as e:
                print(f"  [nav err attempt {attempt + 1}] {e}")
                if attempt < retries:
                    time.sleep(3)
        return False

    def _run_with_browser() -> None:
        nonlocal collected

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, args=["--disable-dev-shm-usage"])
            try:
                ctx  = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
                page = ctx.new_page()

                for base_search_url in cfg["search_urls"]:
                    if collected >= target:
                        break

                    current_search = base_search_url
                    page_num = 1

                    while current_search and collected < target:
                        # Skip styles already fully processed (only on page 1)
                        if current_search in visited_pages and page_num == 1:
                            current_search = None
                            break

                        print(f"  Search p{page_num}: {current_search}")
                        base_netloc = urlparse(current_search).netloc

                        if not _nav(page, current_search):
                            visited_pages.add(current_search)
                            save_visited(visited_pages)
                            break

                        # Collect plan page links from search results
                        try:
                            all_hrefs = page.evaluate("""() =>
                                Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
                            """)
                        except Exception:
                            all_hrefs = []

                        plan_links = list(dict.fromkeys(
                            h for h in all_hrefs if is_plan_link(h, base_netloc)
                        ))[:80]
                        print(f"  Found {len(plan_links)} plan pages")

                        visited_pages.add(current_search)
                        save_visited(visited_pages)

                        for plan_url in plan_links:
                            if collected >= target:
                                break
                            print(f"  Plan: {plan_url}")
                            if _nav(page, plan_url):
                                _harvest(page, plan_url)

                        # AJAX "Next" button pagination
                        try:
                            first_link = page.evaluate("""() => {
                                const a = document.querySelector('a[href*="/plan/"]');
                                return a ? a.href : null;
                            }""")
                            page.click('a:has-text("Next")', timeout=3000)
                            time.sleep(2)
                            new_first = page.evaluate("""() => {
                                const a = document.querySelector('a[href*="/plan/"]');
                                return a ? a.href : null;
                            }""")
                            if new_first and new_first != first_link:
                                page_num += 1
                                current_search = page.url
                            else:
                                current_search = None
                        except Exception:
                            current_search = None

            except PWError as e:
                print(f"  [browser crash] {e}")
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

    # Run; restart once on crash if nothing collected yet
    _run_with_browser()
    if collected == 0 and target > 0:
        print(f"  [restart] retrying {source_id} after browser crash")
        _run_with_browser()

    return collected
