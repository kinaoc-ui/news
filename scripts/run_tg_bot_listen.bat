@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
if not exist ".local\logs" mkdir ".local\logs"
title StockNews TG Listener
echo Listening for Telegram: run / more N
python scripts\tg_bot_listen.py >> .local\logs\tg_listen.log 2>&1
