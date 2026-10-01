@echo off
cd /d "%~dp0"
echo Starting Plex Duplicate Finder Server...
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" server.py
) else (
    python server.py
)
pause
