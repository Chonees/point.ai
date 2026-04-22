@echo off
REM Point.ai — Start Backend
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
if defined LOCALAPPDATA (
  set PYTHONPYCACHEPREFIX=%LOCALAPPDATA%\PointAI\pycache
) else (
  set PYTHONPYCACHEPREFIX=%USERPROFILE%\AppData\Local\PointAI\pycache
)
.venv\Scripts\python scripts\ensure_python_runtime_hygiene.py --quiet
.venv\Scripts\python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
