#!/bin/bash
# Point.ai — Run Backend Pytest
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="${XDG_CACHE_HOME:-$HOME/.cache}/PointAI/pycache"
.venv/Scripts/python scripts/ensure_python_runtime_hygiene.py --quiet
.venv/Scripts/python -m pytest "$@"
