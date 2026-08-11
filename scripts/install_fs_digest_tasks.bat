@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

REM Install 3 daily Task Scheduler jobs (08:30 / 13:00 / 18:00 local time).
REM Run this bat once as your normal user (not necessarily Admin if tasks are for current user).

set "BAT=%~dp0run_fs_digest.bat"
set "TASK_BASE=StockNewsFSDigest"

schtasks /Create /TN "%TASK_BASE%_0830" /TR "\"%BAT%\"" /SC DAILY /ST 08:30 /F
if errorlevel 1 goto :fail
schtasks /Create /TN "%TASK_BASE%_1300" /TR "\"%BAT%\"" /SC DAILY /ST 13:00 /F
if errorlevel 1 goto :fail
schtasks /Create /TN "%TASK_BASE%_1800" /TR "\"%BAT%\"" /SC DAILY /ST 18:00 /F
if errorlevel 1 goto :fail

echo.
echo Installed:
echo   %TASK_BASE%_0830  @ 08:30
echo   %TASK_BASE%_1300  @ 13:00
echo   %TASK_BASE%_1800  @ 18:00
echo.
echo Edit config.yaml notify.channels + .env before relying on delivery.
echo Test now:  python scripts\run_fs_digest.py --dry-run
exit /b 0

:fail
echo Failed to create scheduled tasks.
exit /b 1
