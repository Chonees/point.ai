"""Thin wrapper — logic moved to scraper/ module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraper.run import main

if __name__ == "__main__":
    main()
