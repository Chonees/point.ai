import json
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

from backend.runtime_hygiene import (
    PTH_FILENAME,
    build_runtime_hygiene_pth,
    write_runtime_hygiene_pth,
)


def test_pytest_disables_cacheprovider(pytestconfig):
    assert not pytestconfig.pluginmanager.hasplugin("cacheprovider")


def test_pytest_uses_plain_assert_mode(pytestconfig):
    assert pytestconfig.getoption("assertmode") == "plain"


def test_build_runtime_hygiene_pth_sets_bytecode_guards(tmp_path):
    pycache_root = tmp_path / "pycache"

    payload = build_runtime_hygiene_pth(pycache_root)

    assert payload.startswith("import ")
    assert "sys.dont_write_bytecode = True" in payload
    assert "PYTHONDONTWRITEBYTECODE" in payload
    assert json.dumps(str(pycache_root)) in payload


def test_write_runtime_hygiene_pth_is_idempotent(tmp_path):
    pycache_root = tmp_path / "pycache"

    written = write_runtime_hygiene_pth(tmp_path, pycache_root)
    first_mtime = written.stat().st_mtime_ns
    rewritten = write_runtime_hygiene_pth(tmp_path, pycache_root)

    assert rewritten == written
    assert rewritten.stat().st_mtime_ns == first_mtime


def test_cli_installs_runtime_hygiene_into_requested_site_packages(tmp_path):
    site_packages = tmp_path / "site-packages"
    pycache_root = tmp_path / "pycache"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/ensure_python_runtime_hygiene.py",
            "--site-packages-dir",
            str(site_packages),
            "--pycache-prefix",
            str(pycache_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    written = site_packages / PTH_FILENAME
    assert written.exists()
    assert written.read_text(encoding="utf-8") == build_runtime_hygiene_pth(pycache_root)


@pytest.mark.skipif(not hasattr(sys, "base_prefix"), reason="requires venv-style interpreter")
def test_installed_runtime_hygiene_hardens_python_startup(tmp_path):
    site_packages = Path(sysconfig.get_paths()["purelib"])
    pycache_root = tmp_path / "pycache"
    pth_path = site_packages / PTH_FILENAME
    original = pth_path.read_text(encoding="utf-8") if pth_path.exists() else None

    try:
        write_runtime_hygiene_pth(site_packages, pycache_root)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json,sys; print(json.dumps({'dont_write_bytecode': sys.dont_write_bytecode, 'pycache_prefix': sys.pycache_prefix}))",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout.strip())
        assert data == {
            "dont_write_bytecode": True,
            "pycache_prefix": str(pycache_root),
        }
    finally:
        if original is None:
            pth_path.unlink(missing_ok=True)
        else:
            pth_path.write_text(original, encoding="utf-8")
