@echo off
REM Point.ai — Run Backend Pytest
cd /d "%~dp0"
.venv\Scripts\python scripts\ensure_python_runtime_hygiene.py --quiet
set PYTHONDONTWRITEBYTECODE=1
for /f "delims=" %%i in ('.venv\Scripts\python -c "from backend.runtime_hygiene import default_pycache_root; print(default_pycache_root())"') do set PYTHONPYCACHEPREFIX=%%i
.venv\Scripts\python -m pytest %*
