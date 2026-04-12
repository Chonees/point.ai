@echo off
REM Point.ai — Start Backend
cd /d "%~dp0"
.venv\Scripts\python -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
