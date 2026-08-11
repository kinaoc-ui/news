@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

if not exist ".local\logs" mkdir ".local\logs"
set "LOG=.local\logs\fs_digest.log"

echo.>> "%LOG%"
echo ==================================================>> "%LOG%"
echo [%date% %time%] FS digest start>> "%LOG%"
echo ==================================================>> "%LOG%"

python scripts\run_fs_digest.py --x-source browser --browser-headless --browser-channel msedge >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

REM If browser X failed (e.g. login wall), still keep news-only digest next run;
REM check .local\logs\fs_digest.log for X warnings.

echo [%date% %time%] FS digest exit code: %RC%>> "%LOG%"
exit /b %RC%
