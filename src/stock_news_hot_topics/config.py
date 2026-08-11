from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import AppConfig, NewsFeedConfig, TickerConfig, XAccountConfig


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    return AppConfig(
        lookback_hours=int(raw.get("lookback_hours", 24)),
        max_results_per_query=int(raw.get("max_results_per_query", 25)),
        max_browser_accounts=int(raw.get("max_browser_accounts", 10)),
        report_dir=str(raw.get("report_dir", "reports")),
        tickers=[_ticker(item) for item in raw.get("tickers", [])],
        x_accounts=[_x_account(item) for item in raw.get("x_accounts", [])],
        news_feeds=[_news_feed(item) for item in raw.get("news_feeds", [])],
        event_keywords={
            str(name): [str(keyword) for keyword in keywords]
            for name, keywords in (raw.get("event_keywords", {}) or {}).items()
        },
    )


def _ticker(raw: dict[str, Any]) -> TickerConfig:
    return TickerConfig(
        symbol=str(raw["symbol"]).upper(),
        names=[str(item) for item in raw.get("names", [])],
        aliases=[str(item) for item in raw.get("aliases", [])],
    )


def _x_account(raw: dict[str, Any]) -> XAccountConfig:
    return XAccountConfig(
        username=str(raw["username"]).lstrip("@"),
        weight=float(raw.get("weight", 1.0)),
        name=str(raw.get("name", "")),
        category=str(raw.get("category", "")),
        signal_profile=str(raw.get("signal_profile", "")),
    )


def _news_feed(raw: dict[str, Any]) -> NewsFeedConfig:
    return NewsFeedConfig(name=str(raw["name"]), url=str(raw["url"]))
