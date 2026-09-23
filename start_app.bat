@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run install.bat first.
  pause
  exit /b 1
)

echo Starting Mojito RTC TWA Calculator...
echo.
rem The app prints the addresses to open, on this PC and from other devices.
call .venv\Scripts\python.exe app.py
pause
