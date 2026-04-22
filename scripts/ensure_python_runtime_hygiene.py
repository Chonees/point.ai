import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.runtime_hygiene import default_pycache_root, install_runtime_hygiene


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install Point.ai Python runtime hygiene hooks into the active environment.")
    parser.add_argument("--site-packages-dir", type=Path, help="Override the target site-packages directory.")
    parser.add_argument("--pycache-prefix", type=Path, help="Override the external pycache root.")
    parser.add_argument("--quiet", action="store_true", help="Suppress success output.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    pth_path = install_runtime_hygiene(args.site_packages_dir, args.pycache_prefix)

    if not args.quiet:
        pycache_root = args.pycache_prefix or default_pycache_root()
        print(f"Installed runtime hygiene: {pth_path}")
        print(f"Pycache redirect: {pycache_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
