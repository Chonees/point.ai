"""
scraper  —  floor plan image scraper package

Usage:
    python -m scraper                          # scrape all sources
    python -m scraper --sources houseplans     # one source
    python -m scraper --target 10000           # custom target
"""
from scraper.sources import SOURCES
from scraper.browser import scrape_source
from scraper.checkpoint import load_index, save_index, load_visited, save_visited, OUTPUT_DIR
