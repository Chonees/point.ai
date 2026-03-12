#!/bin/bash
# Point.ai — Start Backend
cd "$(dirname "$0")"
.venv/Scripts/uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
