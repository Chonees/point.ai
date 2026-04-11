"""
Quarantined training tests.

These tests depend on training modules (convert_resplan, convert_cubicasa,
export_lmdb) that have been removed from the codebase. They are kept here
for reference and will be re-enabled when the training pipeline is rebuilt.

Run explicitly: python -m pytest tests/training/
"""
import importlib

import pytest

_REQUIRED_MODULES = [
    "training.convert_resplan",
    "training.convert_cubicasa",
    "training.export_lmdb",
]


def _training_modules_available() -> bool:
    for mod in _REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
        except ImportError:
            return False
    return True


if not _training_modules_available():
    collect_ignore_glob = ["test_*.py"]
