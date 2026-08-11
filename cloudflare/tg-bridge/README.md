# Free Telegram webhook bridge (Cloudflare Workers)
#
# 1. Create free Cloudflare account: https://dash.cloudflare.com/sign-up
# 2. Create a GitHub PAT (classic) with scopes: repo, workflow
#    https://github.com/settings/tokens
# 3. Run: cloudflare\tg-bridge\deploy.bat
# 4. Copy the workers.dev URL, then:
#      set TG_BRIDGE_URL=https://stock-news-tg-bridge.<you>.workers.dev
#      set WEBHOOK_SECRET=你設嘅密碼
#      python scripts\setup_telegram_webhook.py
# 5. Extra secret (after first deploy):
#      npx wrangler secret put CURSOR_AUTOMATION_WEBHOOK_URL
#    paste the Automations webhook URL
# 6. Telegram 打 run → Cursor agent 版（中文）+ GitHub 版背景對照

See deploy.bat in this folder.
