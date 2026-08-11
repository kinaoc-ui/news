from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import feedparser

from .models import NewsItem

_NOTEWORTHY = (
    "earnings",
    "guidance",
    "raises",
    "cuts",
    "downgrade",
    "upgrade",
    "acquire",
    "acquisition",
    "merger",
    "buyout",
    "lawsuit",
    "sec ",
    "fda",
    "approve",
    "approval",
    "short seller",
    "investigation",
    "bankruptcy",
    "dividend",
    "buyback",
    "offering",
    "partnership",
    "contract",
    "beat",
    "miss",
    "outlook",
    "ceo",
    "cfo",
)


def yahoo_headline_feed(symbol: str) -> str:
    return f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote_plus(symbol)}&region=US&lang=en-US"


def google_news_feed(symbol: str) -> str:
    q = quote_plus(f"{symbol} stock")
    return f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


def collect_symbol_news(
    symbols: list[str],
    lookback_hours: int,
    *,
    max_workers: int = 8,
    per_symbol_limit: int = 8,
) -> list[NewsItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    items: list[NewsItem] = []
    seen: set[str] = set()

    def _one(symbol: str) -> list[NewsItem]:
        found: list[NewsItem] = []
        for source_name, url in (
            ("Yahoo Finance", yahoo_headline_feed(symbol)),
            ("Google News", google_news_feed(symbol)),
        ):
            parsed = feedparser.parse(url)
            for entry in parsed.entries[:per_symbol_limit]:
                link = str(entry.get("link", "")).strip()
                if not link or link in seen:
                    continue
                published = _entry_datetime(entry)
                if published and published < cutoff:
                    continue
                title = str(entry.get("title", "")).strip()
                if not title:
                    continue
                seen.add(link)
                found.append(
                    NewsItem(
                        source=f"{source_name}:{symbol}",
                        title=title,
                        url=link,
                        published_at=published,
                        summary=str(entry.get("summary", "")).strip(),
                    )
                )
        return found

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_one, symbol): symbol for symbol in symbols}
        for fut in as_completed(futures):
            try:
                items.extend(fut.result())
            except Exception as exc:  # noqa: BLE001 — keep digest running
                symbol = futures[fut]
                print(f"Warning: symbol news failed for {symbol}: {exc}")

    return sorted(
        items,
        key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


_SKIP_NOISE = (
    "has $",
    "stake in",
    "buys shares of",
    "acquires shares of",
    "sells shares of",
    "insider selling",
    "issues positive forecast",
    "price target",
)


def is_noteworthy(text: str) -> bool:
    lowered = text.lower()
    if any(noise in lowered for noise in _SKIP_NOISE):
        return False
    return any(keyword in lowered for keyword in _NOTEWORTHY)


def _entry_datetime(entry: object) -> datetime | None:
    for key in ("published", "updated", "created"):
        value = entry.get(key) if hasattr(entry, "get") else None
        if not value:
            continue
        try:
            parsed = parsedate_to_datetime(str(value))
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None
