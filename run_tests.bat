@echo off
setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run install.bat first.
  pause
  exit /b 1
)

rem Runs every test in tests\. Extra arguments are passed to unittest,
rem e.g.  run_tests.bat -v   or   run_tests.bat -k shortening
.venv\Scripts\python.exe -m unittest discover -s tests -t . %*
set RESULT=%ERRORLEVEL%

rem Keep the window open when double-clicked.
if "%~1"=="" pause
exit /b %RESULT%
