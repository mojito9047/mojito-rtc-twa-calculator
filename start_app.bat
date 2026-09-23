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
echo Open this on the Expedition PC:
echo   http://localhost:8765
echo.
echo From another device on the same network, use:
echo   http://THIS-PC-IP-ADDRESS:8765
echo.
call .venv\Scripts\python.exe app.py
pause
