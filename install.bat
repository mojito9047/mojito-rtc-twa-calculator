@echo off
setlocal
cd /d "%~dp0"

echo Mojito RTC TWA Calculator: install
echo.
echo Creating the Python environment...
py -3 -m venv .venv
if errorlevel 1 (
  echo Could not create the environment. Install Python 3.11 or later from python.org, then run this again.
  pause
  exit /b 1
)

rem The release zip carries Flask, Waitress and their dependencies in wheels\, so this
rem needs no internet. Without them (a git checkout), pip downloads them.
if not exist wheels\ goto online
echo Installing Flask and Waitress from the wheels folder (no internet needed)...
.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check --no-index --find-links wheels -r requirements.txt
if not errorlevel 1 goto installed
echo The wheels folder does not suit this Python; trying the internet instead.

:online
echo Installing Flask and Waitress from the internet...
.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo Could not install Flask and Waitress. Connect to the internet and run this again.
  pause
  exit /b 1
)

:installed
echo.
rem Offers to bring settings, marks and course across from the previous version's folder.
.venv\Scripts\python.exe copy_previous_install.py
echo.
rem Offers to start the app when you sign in to Windows; if it already does,
rem moves that to this version so the old one is never the one that starts.
.venv\Scripts\python.exe autostart.py --install
echo.
echo Install complete. Double-click start_app.bat to start the app.
pause
