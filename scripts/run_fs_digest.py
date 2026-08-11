from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_news_hot_topics.collectors.news import collect_news
from stock_news_hot_topics.collectors.x_api import XApiClient
from stock_news_hot_topics.collectors.x_browser import collect_x_with_browser
from stock_news_hot_topics.config import load_config
from stock_news_hot_topics.fs_digest import (
    build_fs_digest,
    save_last_digest_state,
    write_digest_file,
)
from stock_news_hot_topics.notify import send_notifications


def main() -> None:
    args = _parse_args()
    load_dotenv(ROOT / ".env")

    config_path = _resolve_config_path(args.config)
    config = load_config(config_path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    fs_cfg = raw.get("first_screen") or {}
    notify_cfg = raw.get("notify") or {}

    first_screen_dir = Path(
        args.first_screen_dir
        or fs_cfg.get("reports_dir")
        or (ROOT.parent / "screening" / "reports" / "first_screen")
    )
    if not first_screen_dir.is_absolute():
        first_screen_dir = (ROOT / first_screen_dir).resolve()

    lookback = int(args.lookback_hours or fs_cfg.get("lookback_hours") or config.lookback_hours)
    channels = args.notify or list(notify_cfg.get("channels") or [])

    print(f"Config: {config_path}")
    print(f"First Screen dir: {first_screen_dir}")
    print(f"Lookback hours: {lookback}")

    print("Collecting general RSS news...")
    general_news = collect_news(config.news_feeds, lookback)

    x_posts = []
    x_source = "none" if args.skip_x else args.x_source
    bearer_token = os.getenv("X_BEARER_TOKEN", "").strip()
    x_attempted = False
    if x_source == "none":
        print("Skipping X collection.")
    elif x_source == "browser":
        print("Collecting X posts with browser...")
        x_attempted = True
        x_posts = collect_x_with_browser(
            config,
            headless=args.browser_headless,
            profile_dir=args.browser_profile,
            posts_per_account=args.posts_per_account,
            browser_channel=args.browser_channel,
        )
        print(f"X posts: {len(x_posts)}")
    elif not bearer_token:
        print("Skipping X collection because X_BEARER_TOKEN is missing.")
    else:
        print("Collecting X posts with API...")
        x_attempted = True
        with XApiClient(bearer_token, config.max_results_per_query) as client:
            x_posts = client.collect_posts(config)
        print(f"X posts: {len(x_posts)}")

    print("Building First Screen digest + per-symbol news...")
    digest = build_fs_digest(
        config,
        first_screen_dir=first_screen_dir,
        lookback_hours=lookback,
        general_news=general_news,
        x_posts=x_posts,
        max_bullets=args.max_bullets,
        x_attempted=x_attempted,
    )
    print(f"List: {digest.list_path.name} ({len(digest.symbols)} symbols)")

    out_dir = Path(args.output_dir or config.report_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    report_path = write_digest_file(out_dir, digest.title, digest.body)
    state_path = save_last_digest_state(
        out_dir,
        title=digest.title,
        list_name=digest.list_path.name,
        items=digest.items,
        x_note=digest.x_note,
    )
    print(f"Report: {report_path}")
    print(f"State: {state_path}")
    print("---")
    print(digest.body)
    print("---")

    if args.dry_run:
        print("Dry run: notifications skipped.")
        return

    if not channels:
        print("No notify channels configured (notify.channels / --notify). Report saved only.")
        return

    print(f"Sending via: {', '.join(channels)}")
    for line in send_notifications("", digest.body, channels):
        print(line)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Local First Screen news digest + notify.")
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--first-screen-dir", default=None, help="Folder with FirstScreen_*_comma.txt")
    p.add_argument("--lookback-hours", type=int, default=None)
    p.add_argument("--output-dir", default=None)
    p.add_argument("--max-bullets", type=int, default=12)
    p.add_argument("--skip-x", action="store_true")
    p.add_argument("--x-source", choices=("api", "browser", "none"), default="none")
    p.add_argument("--browser-profile", default=".browser-profile/x")
    p.add_argument("--browser-headless", action="store_true")
    p.add_argument("--posts-per-account", type=int, default=5)
    p.add_argument("--browser-channel", choices=("msedge", "chrome", "chromium"), default="msedge")
    p.add_argument(
        "--notify",
        nargs="*",
        default=None,
        help="Channels: telegram ntfy email sms whatsapp",
    )
    p.add_argument("--dry-run", action="store_true", help="Write report only, do not notify.")
    return p.parse_args()


def _resolve_config_path(path: str) -> Path:
    requested = Path(path)
    if not requested.is_absolute():
        requested = ROOT / requested
    if requested.exists():
        return requested
    fallback = ROOT / "config.example.yaml"
    if fallback.exists():
        print(f"Config {requested} missing; using {fallback}")
        return fallback
    raise FileNotFoundError(path)


if __name__ == "__main__":
    main()
