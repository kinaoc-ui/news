#!/usr/bin/env python3
"""Send data/agent_last_fs_digest.json short body to Telegram."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dotenv import load_dotenv

from stock_news_hot_topics.notify import send_telegram_text


def format_short(data: dict) -> str:
    title = str(data.get("title") or "FS新聞")
    list_name = str(data.get("list_name") or "")
    items = data.get("items") or []
    lines = [title]
    if list_name:
        lines.append(f"列表: {list_name}")
    lines.append("")
    if items:
        for item in items:
            n = item.get("n")
            short = item.get("short") or ""
            lines.append(f"{n}. {short}")
    else:
        lines.append("今輪 First Screen list 冇特別值得留意嘅新聞。")
    x_note = str(data.get("x_note") or "").strip()
    if x_note:
        lines.extend(["", x_note])
    lines.extend(["", "回覆 more 1 可睇詳情"])
    return "\n".join(lines)


def main() -> None:
    load_dotenv(ROOT / ".env")
    path = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "data" / "agent_last_fs_digest.json")
    if not path.is_file():
        raise SystemExit(f"missing digest file: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    body = format_short(data)
    print(body)
    print("---")
    if os.getenv("DRY_RUN") == "1":
        print("DRY_RUN: telegram skipped")
        return
    print(send_telegram_text(body))


if __name__ == "__main__":
    main()
