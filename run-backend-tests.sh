#!/bin/bash
# Point.ai — Run Backend Pytest
cd "$(dirname "$0")"
.venv/Scripts/python scripts/ensure_python_runtime_hygiene.py --quiet
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$(.venv/Scripts/python -c 'from backend.runtime_hygiene import default_pycache_root; print(default_pycache_root())')"
.venv/Scripts/python -m pytest "$@"
