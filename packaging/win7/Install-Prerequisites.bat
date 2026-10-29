@echo off
rem DataVox - Windows 7 prerequisites. Run once (double-click), then restart the computer.
setlocal EnableExtensions
title DataVox - Windows 7 prerequisites

net session >nul 2>&1
if errorlevel 1 (
  echo Asking for administrator permission...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
cd /d "%~dp0"

ver | findstr /c:"6.1."  >nul
if errorlevel 1 (
  echo These prerequisites are only needed on Windows 7. Nothing to do on this Windows version.
  pause
  exit /b 0
)
if /i not "%PROCESSOR_ARCHITECTURE%"=="AMD64" if /i not "%PROCESSOR_ARCHITEW6432%"=="AMD64" (
  echo DataVox needs 64-bit Windows 7 SP1. This computer runs 32-bit Windows.
  pause
  exit /b 1
)
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion" /v CSDVersion 2>nul | findstr /c:"Service Pack 1" >nul
if errorlevel 1 (
  echo Windows 7 Service Pack 1 is required. Please install SP1 first, then run this file again.
  pause
  exit /b 1
)

rem wusa needs the Windows Update service; enable it temporarily if it is disabled
set "WU_DISABLED="
sc qc wuauserv | findstr /c:"DISABLED" >nul && set "WU_DISABLED=1"
if defined WU_DISABLED sc config wuauserv start= demand >nul
net start wuauserv >nul 2>&1

echo.
echo [1/3] Windows update KB3063858 (DLL loading support)...
wusa.exe "%~dp0Windows6.1-KB3063858-x64.msu" /quiet /norestart
call :result %errorlevel%

echo [2/3] Windows update KB2999226 (Universal C Runtime)...
wusa.exe "%~dp0Windows6.1-KB2999226-x64.msu" /quiet /norestart
call :result %errorlevel%

if defined WU_DISABLED (
  net stop wuauserv >nul 2>&1
  sc config wuauserv start= disabled >nul
)

echo [3/3] .NET Framework 4.8...
set "NETREL=0"
for /f "tokens=3" %%a in ('reg query "HKLM\SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full" /v Release 2^>nul ^| findstr /c:"Release"') do set /a NETREL=%%a
if %NETREL% GEQ 394802 (
  echo       already installed.
) else (
  echo       installing, this can take several minutes...
  "%~dp0ndp48-x86-x64-allos-enu.exe" /q /norestart
  call :result %errorlevel%
)

echo.
echo Done. Please RESTART the computer, then open DataVox.exe.
pause
exit /b 0

:result
if "%1"=="0" (echo       installed.& exit /b)
if "%1"=="3010" (echo       installed; restart required.& exit /b)
if "%1"=="1641" (echo       installed; restart required.& exit /b)
if "%1"=="2359302" (echo       already installed.& exit /b)
if "%1"=="-2145124329" (echo       not needed on this computer.& exit /b)
echo       finished with code %1. If DataVox does not start, see Windows7-Guide.html.
exit /b
