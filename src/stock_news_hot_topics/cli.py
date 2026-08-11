from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .analyzer import analyze_attention
from .collectors.news import collect_news
from .collectors.x_api import XApiClient
from .collectors.x_browser import collect_x_with_browser
from .config import load_config
from .report import write_markdown_report


def main() -> None:
    args = _parse_args()
    load_dotenv()

    config_path = _resolve_config_path(args.config)
    config = load_config(config_path)

    print(f"Using config: {config_path}")
    print("Collecting news...")
    news_items = collect_news(config.news_feeds, config.lookback_hours)

    x_posts = []
    x_source = "none" if args.skip_x else args.x_source
    bearer_token = os.getenv("X_BEARER_TOKEN", "").strip()
    if x_source == "none":
        print("Skipping X collection.")
    elif x_source == "browser":
        print("Collecting X posts with browser...")
        x_posts = collect_x_with_browser(
            config,
            headless=args.browser_headless,
            profile_dir=args.browser_profile,
            posts_per_account=args.posts_per_account,
            browser_channel=args.browser_channel,
        )
        if not x_posts:
            print(
                f"No fresh X posts in the last {config.lookback_hours}h. "
                "Report will focus on news. X login may be required for live posts."
            )
        else:
            print(f"Fresh X posts collected: {len(x_posts)}")
    elif not bearer_token:
        print("Skipping X collection because X_BEARER_TOKEN is missing.")
    else:
        print("Collecting X posts with API...")
        with XApiClient(bearer_token, config.max_results_per_query) as client:
            x_posts = client.collect_posts(config)

    print("Analyzing attention...")
    items = analyze_attention(config, news_items, x_posts)

    print("Writing report...")
    report_path = write_markdown_report(config, items, news_items, x_posts, args.output_dir)
    print(f"Report written: {report_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Find stock hot topics from news and X attention.")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config YAML. Defaults to config.yaml, then falls back to config.example.yaml.",
    )
    parser.add_argument("--output-dir", default=None, help="Override report output directory.")
    parser.add_argument("--skip-x", action="store_true", help="Run with news only, without calling the X API.")
    parser.add_argument(
        "--x-source",
        choices=("api", "browser", "none"),
        default="api",
        help="Choose how to collect X posts. Use browser to avoid the paid X API.",
    )
    parser.add_argument(
        "--browser-profile",
        default=".browser-profile/x",
        help="Persistent browser profile path for X browser mode.",
    )
    parser.add_argument(
        "--browser-headless",
        action="store_true",
        help="Run browser mode hidden. Leave this off if you need to log in manually.",
    )
    parser.add_argument(
        "--posts-per-account",
        type=int,
        default=5,
        help="Maximum visible posts to read per configured X account in browser mode.",
    )
    parser.add_argument(
        "--browser-channel",
        choices=("msedge", "chrome", "chromium"),
        default="msedge",
        help="Browser engine for X browser mode. msedge is recommended on Windows for login compatibility.",
    )
    return parser.parse_args()


def _resolve_config_path(path: str) -> Path:
    requested = Path(path)
    if requested.exists():
        return requested

    fallback = Path("config.example.yaml")
    if fallback.exists():
        print(f"Config file {requested} not found; using {fallback}.")
        return fallback

    raise FileNotFoundError(f"Config file not found: {requested}")


if __name__ == "__main__":
    main()
