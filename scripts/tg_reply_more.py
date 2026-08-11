from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_news_hot_topics.fs_digest import format_item_detail, load_last_digest_state
from stock_news_hot_topics.notify import send_telegram_text

# used by tg_bot_listen
__all__ = [
    "_RUN_RE",
    "_MORE_RE",
    "_run_digest",
    "_reply_n",
    "load_last_digest_state",
]

_MORE_RE = re.compile(r"^\s*more\s+(\d+)\s*$", re.IGNORECASE)
_RUN_RE = re.compile(r"^\s*run\s*$", re.IGNORECASE)
_LOCK = ROOT / ".local" / "fs_digest_run.lock"


def main() -> None:
    args = _parse_args()
    load_dotenv(ROOT / ".env")
    report_dir = Path(args.report_dir)
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    (ROOT / ".local" / "logs").mkdir(parents=True, exist_ok=True)

    if args.n is not None:
        state = load_last_digest_state(report_dir) or {}
        _reply_n(state, args.n)
        return

    if args.run_now:
        _run_digest()
        return

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing in .env")

    offset_path = report_dir / ".tg_updates_offset"
    offset = 0
    if offset_path.is_file():
        try:
            offset = int(offset_path.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            offset = 0

    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            f"https://api.telegram.org/bot{token}/getUpdates",
            params={"offset": offset, "timeout": 0},
        )
        resp.raise_for_status()
        data = resp.json()

    handled_more = 0
    handled_run = 0
    max_update_id = offset - 1
    for upd in data.get("result") or []:
        uid = int(upd.get("update_id", 0))
        max_update_id = max(max_update_id, uid)
        msg = upd.get("message") or {}
        from_chat = str((msg.get("chat") or {}).get("id", ""))
        if from_chat != str(chat_id):
            continue
        text = str(msg.get("text") or "")

        if _RUN_RE.match(text):
            # Advance offset first so a long run doesn't re-trigger the same message
            if max_update_id >= offset:
                offset_path.write_text(str(max_update_id + 1), encoding="utf-8")
            _run_digest()
            handled_run += 1
            continue

        m = _MORE_RE.match(text)
        if not m:
            continue
        state = load_last_digest_state(report_dir) or {}
        _reply_n(state, int(m.group(1)))
        handled_more += 1

    if max_update_id >= offset:
        offset_path.write_text(str(max_update_id + 1), encoding="utf-8")

    print(f"Handled run={handled_run} more={handled_more}")


def _run_digest() -> None:
    if _LOCK.is_file():
        age = time.time() - _LOCK.stat().st_mtime
        if age < 20 * 60:
            send_telegram_text("而家已經喺度跑緊摘要，稍等陣再試 run。")
            print("digest already running (lock)")
            return
        _LOCK.unlink(missing_ok=True)

    _LOCK.write_text(str(time.time()), encoding="utf-8")
    try:
        send_telegram_text("收到 run — 而家開始掃 First Screen 新聞＋X，完成會再推。")
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "run_fs_digest.py"),
            "--x-source",
            "browser",
            "--browser-headless",
            "--browser-channel",
            "msedge",
        ]
        log_path = ROOT / ".local" / "logs" / "fs_digest_on_demand.log"
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n===== on-demand run {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            proc = subprocess.run(
                cmd,
                cwd=str(ROOT),
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        if proc.returncode != 0:
            send_telegram_text(f"跑完但失敗（exit {proc.returncode}），睇 .local/logs/fs_digest_on_demand.log")
            print(f"digest failed rc={proc.returncode}")
        else:
            print("digest finished ok")
    finally:
        _LOCK.unlink(missing_ok=True)


def _reply_n(state: dict, n: int) -> None:
    items = {int(it["n"]): it for it in state.get("items") or []}
    item = items.get(n)
    if not item:
        send_telegram_text(f"冇第 {n} 項。而家只有 1–{max(items) if items else 0}。")
        print(f"missing item {n}")
        return
    send_telegram_text(format_item_detail(item))
    print(f"sent detail for #{n}")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Telegram bot: run / more N")
    p.add_argument("--report-dir", default="reports")
    p.add_argument("-n", type=int, default=None, help="Send detail for item N")
    p.add_argument("--run-now", action="store_true", help="Trigger digest immediately")
    p.add_argument("--poll", action="store_true", help="Poll Telegram (default if no -n/--run-now)")
    return p.parse_args()


if __name__ == "__main__":
    main()
