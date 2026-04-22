#!/bin/bash
# Point.ai — Start Backend
cd "$(dirname "$0")"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="${XDG_CACHE_HOME:-$HOME/.cache}/PointAI/pycache"
.venv/Scripts/python scripts/ensure_python_runtime_hygiene.py --quiet
.venv/Scripts/python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
