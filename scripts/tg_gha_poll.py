from __future__ import annotations

"""
GitHub Actions Telegram poller: detect `run` / `more N` without a local listener.
Writes GitHub Actions outputs: run=true|false, more_n=<int or empty>
"""

import json
import os
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_news_hot_topics.fs_digest import format_item_detail, load_last_digest_state
from stock_news_hot_topics.notify import send_telegram_text

_MORE_RE = re.compile(r"^\s*more\s+(\d+)\s*$", re.IGNORECASE)
_RUN_RE = re.compile(r"^\s*run\s*$", re.IGNORECASE)


def _out(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    line = f"{name}={value}\n"
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
    print(f"output {name}={value}")


def main() -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing")

    report_dir = Path(os.getenv("REPORT_DIR", str(ROOT / "reports")))
    report_dir.mkdir(parents=True, exist_ok=True)
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
        updates = resp.json().get("result") or []

    want_run = False
    more_ns: list[int] = []
    max_id = offset - 1

    for upd in updates:
        uid = int(upd.get("update_id", 0))
        max_id = max(max_id, uid)
        msg = upd.get("message") or {}
        from_chat = str((msg.get("chat") or {}).get("id", ""))
        if from_chat != str(chat_id):
            continue
        text = str(msg.get("text") or "")
        if _RUN_RE.match(text):
            want_run = True
            print(f"got run (update {uid})")
        else:
            m = _MORE_RE.match(text)
            if m:
                more_ns.append(int(m.group(1)))
                print(f"got more {m.group(1)} (update {uid})")

    if max_id >= offset:
        offset_path.write_text(str(max_id + 1), encoding="utf-8")

    # Handle more N immediately (needs last_fs_digest.json in reports/)
    state = load_last_digest_state(report_dir) or {}
    items = {int(it["n"]): it for it in state.get("items") or []}
    for n in more_ns:
        item = items.get(n)
        if not item:
            send_telegram_text(f"冇第 {n} 項。而家只有 1–{max(items) if items else 0}。")
        else:
            send_telegram_text(format_item_detail(item))

    if want_run:
        send_telegram_text("收到 run — GitHub 而家開始掃，完成會再推（可能要一兩分鐘）。")

    _out("run", "true" if want_run else "false")
    _out("more_count", str(len(more_ns)))
    # debug
    print(json.dumps({"updates": len(updates), "run": want_run, "more": more_ns}))


if __name__ == "__main__":
    main()
