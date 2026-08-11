from __future__ import annotations

"""
Long-poll Telegram: idle until a message arrives, then handle run / more N.
Much lighter than Task Scheduler every 2 minutes.
"""

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Reuse handlers from tg_reply_more
sys.path.insert(0, str(ROOT / "scripts"))
import tg_reply_more as bot  # noqa: E402


def main() -> None:
    load_dotenv(ROOT / ".env")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing")

    report_dir = ROOT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (ROOT / ".local" / "logs").mkdir(parents=True, exist_ok=True)
    offset_path = report_dir / ".tg_updates_offset"
    offset = 0
    if offset_path.is_file():
        try:
            offset = int(offset_path.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            offset = 0

    print(f"TG long-poll listening (chat={chat_id}). Waiting for: run | more N", flush=True)

    with httpx.Client(timeout=90.0) as client:
        while True:
            try:
                resp = client.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    params={"offset": offset, "timeout": 50},
                )
                resp.raise_for_status()
                updates = resp.json().get("result") or []
            except Exception as exc:  # noqa: BLE001
                print(f"poll error: {exc}", flush=True)
                time.sleep(5)
                continue

            for upd in updates:
                uid = int(upd.get("update_id", 0))
                offset = max(offset, uid + 1)
                offset_path.write_text(str(offset), encoding="utf-8")

                msg = upd.get("message") or {}
                from_chat = str((msg.get("chat") or {}).get("id", ""))
                if from_chat != str(chat_id):
                    continue
                text = str(msg.get("text") or "")
                print(f"got: {text!r}", flush=True)

                if bot._RUN_RE.match(text):
                    bot._run_digest()
                else:
                    m = bot._MORE_RE.match(text)
                    if m:
                        state = bot.load_last_digest_state(report_dir) or {}
                        bot._reply_n(state, int(m.group(1)))


if __name__ == "__main__":
    main()
