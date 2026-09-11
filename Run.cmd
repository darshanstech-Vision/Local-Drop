@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run Setup.cmd first, or use the portable Windows package.
  pause
  exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "run.py"
