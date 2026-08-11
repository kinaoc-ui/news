@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
if not exist ".local\logs" mkdir ".local\logs"
REM Polls Telegram every ~2 min for: run | more N
python scripts\tg_reply_more.py --poll >> .local\logs\tg_more.log 2>&1
