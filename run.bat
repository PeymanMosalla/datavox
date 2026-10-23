@echo off
rem Starts Voice2Excel locally (offline). Keep this window open while working.
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set HF_HUB_OFFLINE=1
set HF_HUB_DISABLE_TELEMETRY=1
if not exist ".venv\Scripts\python.exe" (
  echo The program is not installed yet. Run install.bat first.
  pause
  exit /b 1
)
title Voice2Excel - keep this window open
".venv\Scripts\python.exe" -m voice2excel %*
if errorlevel 1 pause
