@echo off
setlocal
cd /d "%~dp0"

rem Builds dist\mojito_rtc_twa_calculator_vNN.zip from the tagged version, then
rem offers to publish it on GitHub. Developer tool, not in the release zip.
rem See docs\RELEASING.md.

if not exist .venv\Scripts\python.exe (
  echo Virtual environment not found. Run install.bat first.
  pause
  exit /b 1
)

.venv\Scripts\python.exe tools\release.py build %*
if errorlevel 1 (
  pause
  exit /b 1
)

echo.
set PUBLISH=
set /p PUBLISH=Publish this release on GitHub now? [y/N]
if /i "%PUBLISH%"=="y" .venv\Scripts\python.exe tools\release.py publish
pause
