@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] 需要 Node.js / npm。去 https://nodejs.org 安裝後再跑。
  exit /b 1
)

echo [1/4] Install wrangler...
call npm install --no-fund --no-audit wrangler@4

echo [2/4] Cloudflare login（瀏覽器會開）...
call npx wrangler login
if errorlevel 1 exit /b 1

echo [3/4] Put secrets（跟住提示貼上，唔會顯示）...
echo TELEGRAM_BOT_TOKEN:
call npx wrangler secret put TELEGRAM_BOT_TOKEN
echo TELEGRAM_CHAT_ID:
call npx wrangler secret put TELEGRAM_CHAT_ID
echo GITHUB_TOKEN ^(需要 actions:write 嘅 PAT^):
call npx wrangler secret put GITHUB_TOKEN
echo WEBHOOK_SECRET ^(自訂一串密碼，稍後 setWebhook 會用^):
call npx wrangler secret put WEBHOOK_SECRET

echo [4/4] Deploy...
call npx wrangler deploy
if errorlevel 1 exit /b 1

echo.
echo Deploy 完會顯示 workers.dev URL。
echo 然後跑: python ..\..\scripts\setup_telegram_webhook.py
exit /b 0
