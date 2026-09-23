@echo off
setlocal
cd /d "%~dp0"

rem Shows whether the app starts automatically when you sign in to Windows,
rem and turns it on (for this version) or off. See autostart.py.

if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run install.bat first.
  pause
  exit /b 1
)

.venv\Scripts\python.exe autostart.py
pause
