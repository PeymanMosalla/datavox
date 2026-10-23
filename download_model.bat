@echo off
rem Downloads a speech model once (needs internet). Usage: download_model.bat [large-v3-turbo^|small]
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set MODEL=%1
if "%MODEL%"=="" set MODEL=large-v3-turbo
".venv\Scripts\python.exe" -m voice2excel.model_download %MODEL%
pause
