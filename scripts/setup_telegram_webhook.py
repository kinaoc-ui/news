from __future__ import annotations

"""Set Telegram webhook to the Cloudflare Worker URL."""

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN missing in .env")

    worker = (os.getenv("TG_BRIDGE_URL") or "").strip().rstrip("/")
    secret = (os.getenv("WEBHOOK_SECRET") or "").strip()
    if not worker:
        worker = input("Cloudflare Worker base URL (https://....workers.dev): ").strip().rstrip("/")
    if not worker:
        raise SystemExit("需要 Worker URL")
    if not secret:
        secret = input("WEBHOOK_SECRET (同 wrangler secret 一樣): ").strip()

    hook = f"{worker}/telegram?key={secret}"
    with httpx.Client(timeout=30.0) as client:
        # Drop any old webhook first
        client.get(f"https://api.telegram.org/bot{token}/deleteWebhook")
        resp = client.get(
            f"https://api.telegram.org/bot{token}/setWebhook",
            params={"url": hook, "allowed_updates": '["message"]'},
        )
        data = resp.json()
        print(data)
        if not data.get("ok"):
            raise SystemExit("setWebhook failed")
        info = client.get(f"https://api.telegram.org/bot{token}/getWebhookInfo").json()
        print(info)


if __name__ == "__main__":
    main()
