@echo off
rem Voice2Excel installer (run once, needs internet). Persian messages are printed by scripts\install.py
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set "PY="
py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
if not defined PY py -3.11 -c "import sys" >nul 2>&1 && set "PY=py -3.11"
if not defined PY py -3.13 -c "import sys" >nul 2>&1 && set "PY=py -3.13"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12),(3,13)) else 1)" >nul 2>&1 && set "PY=python"
if not defined PY (
  echo [ERROR] Python 3.12 was not found.
  echo Install Python 3.12 from python.org with "Add python.exe to PATH" enabled, then run install.bat again.
  pause
  exit /b 1
)
%PY% "%~dp0scripts\install.py" %*
set RC=%ERRORLEVEL%
pause
exit /b %RC%
