@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto fail
".venv\Scripts\python.exe" build.py
if errorlevel 1 goto fail
echo Built dist\LocalDrop\LocalDrop.exe. Keep its _internal folder beside it.
pause
exit /b 0
:fail
echo Build failed. See the error above.
pause
exit /b 1
