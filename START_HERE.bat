@echo off
REM Double-click this on Windows. It keeps the window open so you can read it.
cd /d "%~dp0"
python START_HERE.py
if errorlevel 9009 (
  echo.
  echo Python does not seem to be installed.
  echo Get it from python.org/downloads and tick "Add Python to PATH".
  echo.
  pause
)
