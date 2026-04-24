import json
import os
import sys
import sysconfig
from pathlib import Path

PTH_FILENAME = "pointai_runtime_hygiene.pth"


def default_pycache_root() -> Path:
    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA")
        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
    else:
        xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
        base = Path(xdg_cache_home) if xdg_cache_home else Path.home() / ".cache"
    return base / "PointAI" / "pycache"


def build_runtime_hygiene_pth(pycache_root: Path) -> str:
    root_literal = json.dumps(str(Path(pycache_root)))
    return (
        "import os, pathlib, sys; "
        "sys.dont_write_bytecode = True; "
        "os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1'); "
        f"_pointai_pycache = pathlib.Path({root_literal}); "
        "_pointai_pycache.mkdir(parents=True, exist_ok=True); "
        "sys.pycache_prefix = str(_pointai_pycache)\n"
    )


def write_runtime_hygiene_pth(site_packages_dir: Path, pycache_root: Path) -> Path:
    site_packages_dir = Path(site_packages_dir)
    site_packages_dir.mkdir(parents=True, exist_ok=True)
    pth_path = site_packages_dir / PTH_FILENAME
    payload = build_runtime_hygiene_pth(pycache_root)
    if not pth_path.exists() or pth_path.read_text(encoding="utf-8") != payload:
        pth_path.write_text(payload, encoding="utf-8")
    return pth_path


def install_runtime_hygiene(site_packages_dir: Path | None = None, pycache_root: Path | None = None) -> Path:
    resolved_site_packages = Path(site_packages_dir) if site_packages_dir else Path(sysconfig.get_paths()["purelib"])
    resolved_pycache_root = Path(pycache_root) if pycache_root else default_pycache_root()
    return write_runtime_hygiene_pth(resolved_site_packages, resolved_pycache_root)
