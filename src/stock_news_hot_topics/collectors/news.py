from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

from ..models import NewsFeedConfig, NewsItem


def collect_news(feeds: list[NewsFeedConfig], lookback_hours: int) -> list[NewsItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    items: list[NewsItem] = []
    seen_urls: set[str] = set()

    for feed in feeds:
        parsed = feedparser.parse(feed.url)
        for entry in parsed.entries:
            url = str(entry.get("link", "")).strip()
            if not url or url in seen_urls:
                continue

            published_at = _entry_datetime(entry)
            if published_at and published_at < cutoff:
                continue

            seen_urls.add(url)
            items.append(
                NewsItem(
                    source=feed.name,
                    title=str(entry.get("title", "")).strip(),
                    url=url,
                    published_at=published_at,
                    summary=str(entry.get("summary", "")).strip(),
                )
            )

    return sorted(items, key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


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
