from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .analyzer import match_event_tags, match_tickers
from .models import AppConfig, AttentionItem, NewsItem, XPost, utc_now


def write_markdown_report(
    config: AppConfig,
    items: list[AttentionItem],
    news_items: list[NewsItem],
    x_posts: list[XPost],
    output_dir: str | Path | None = None,
) -> Path:
    report_dir = Path(output_dir or config.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{utc_now().date().isoformat()}.md"

    stocks = [item for item in items if item.kind == "stock"][:10]
    events = [item for item in items if item.kind == "event"][:10]
    recent_news = _recent_news(news_items, config.lookback_hours)[:12]
    recent_x_posts = _recent_x_posts(x_posts, config.lookback_hours)
    top_signal_posts = _pick_top_signal_posts(config, recent_x_posts, limit=8)

    sections: list[str] = [
        f"# Stock Hot Topics - {utc_now().date().isoformat()}",
        "",
        "## Quick Snapshot",
        f"- Lookback window: {config.lookback_hours} hours",
        f"- Fresh news items: {len(recent_news)}",
        f"- Fresh X posts: {len(recent_x_posts)}",
        f"- Ranked hot items: {len(items)}",
        "",
        "Read top to bottom: latest news first, then hot stocks/events. X signals only appear when posts are within the lookback window.",
        "",
        "## Most Useful Right Now",
        "### 1) Latest Market News",
        *_format_top_news(recent_news),
        "",
        "### 2) Hot Stocks",
        *_format_topline_items(stocks[:5]),
        "",
        "### 3) Hot Market Themes",
        *_format_topline_items(events[:5]),
        "",
    ]

    if top_signal_posts:
        sections.extend(
            [
                "### 4) Fresh X Signals (last "
                f"{config.lookback_hours}h only)",
                *_format_signal_posts(top_signal_posts),
                "",
            ]
        )
    else:
        sections.extend(
            [
                "### 4) Fresh X Signals",
                f"No stock-relevant X posts found in the last {config.lookback_hours} hours.",
                "This usually means X login is required, or monitored accounts had no recent market posts.",
                "",
            ]
        )

    sections.extend(
        [
            "## Details",
            "### Stock Breakdown",
            *_format_items(stocks[:5]),
            "",
            "### Theme Breakdown",
            *_format_items(events[:5]),
            "",
            "## Data Sources",
            *_format_sources(config),
            "",
            "## Disclaimer",
            "This is an automated market-attention report for research only. It is not financial advice.",
            "",
        ]
    )

    report_path.write_text("\n".join(sections), encoding="utf-8")
    return report_path


def _recent_news(news_items: list[NewsItem], lookback_hours: int) -> list[NewsItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    recent: list[NewsItem] = []
    for item in news_items:
        published = _normalize_datetime(item.published_at)
        if published and published < cutoff:
            continue
        recent.append(item)
    return sorted(recent, key=lambda item: _normalize_datetime(item.published_at) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def _recent_x_posts(posts: list[XPost], lookback_hours: int) -> list[XPost]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    recent: list[XPost] = []
    for post in posts:
        created = _normalize_datetime(post.created_at)
        if created is None or created < cutoff:
            continue
        recent.append(post)
    return recent


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_items(items: list[AttentionItem]) -> list[str]:
    if not items:
        return ["No matching items found.", ""]

    lines: list[str] = []
    for rank, item in enumerate(items, start=1):
        lines.extend(
            [
                f"### {rank}. {item.key} ({item.kind})",
                f"- Attention score: {item.score:.2f}",
                f"- X posts: {item.x_post_count}",
                f"- X engagement: {item.engagement}",
                f"- News items: {item.news_count}",
                f"- Accounts: {len(item.unique_accounts)} ({', '.join('@' + account for account in sorted(item.unique_accounts)[:6]) or 'n/a'})",
                f"- Related tickers: {', '.join(sorted(item.related_tickers)) or item.key}",
                f"- Event tags: {', '.join(sorted(item.event_tags)) or 'n/a'}",
                "",
                "**Representative X posts**",
                *_format_posts(item.representative_posts[:3]),
                "",
                "**Representative news**",
                *_format_news(item.representative_news[:3]),
                "",
            ]
        )

    return lines


def _format_posts(posts: list[XPost]) -> list[str]:
    if not posts:
        return ["- n/a"]

    lines: list[str] = []
    for post in posts:
        text = _compact(post.text, 220)
        when = _format_date(post.created_at)
        metrics = f"{post.engagement} engagement"
        link = f" [{post.url}]({post.url})" if post.url else ""
        lines.append(f"- @{post.author_username} ({when}): {text} ({metrics}){link}")
    return lines


def _format_top_news(news_items: list[NewsItem]) -> list[str]:
    if not news_items:
        return ["- No fresh news in this lookback window.", ""]

    lines: list[str] = []
    for rank, news in enumerate(news_items, start=1):
        date = _format_date(news.published_at)
        lines.append(f"- {rank}. [{news.title}]({news.url}) — {news.source}, {date}")
    lines.append("")
    return lines


def _format_signal_posts(posts: list[tuple[XPost, set[str], set[str]]]) -> list[str]:
    if not posts:
        return ["No fresh X signals in this lookback window.", ""]

    lines: list[str] = []
    for rank, (post, tickers_set, events_set) in enumerate(posts, start=1):
        tickers = ", ".join(sorted(tickers_set)) if tickers_set else "n/a"
        events = ", ".join(sorted(events_set)) if events_set else "n/a"
        when = _format_date(post.created_at)
        lines.append(
            f"- {rank}. @{post.author_username} ({when}) | engagement {post.engagement} | tickers {tickers} | events {events} | [link]({post.url})"
        )
        lines.append(f"  - {_compact(post.text, 180)}")
    lines.append("")
    return lines


def _format_topline_items(items: list[AttentionItem]) -> list[str]:
    if not items:
        return ["- n/a"]

    lines: list[str] = []
    for rank, item in enumerate(items, start=1):
        lines.append(
            f"- {rank}. {item.key}: score {item.score:.2f}, x_posts {item.x_post_count}, engagement {item.engagement}, news {item.news_count}"
        )
    return lines


def _format_news(news_items: list[NewsItem]) -> list[str]:
    if not news_items:
        return ["- n/a"]

    lines: list[str] = []
    for news in news_items:
        date = _format_date(news.published_at)
        lines.append(f"- {news.source} ({date}): [{news.title}]({news.url})")
    return lines


def _format_sources(config: AppConfig) -> list[str]:
    lines = ["**News feeds**"]
    lines.extend(f"- {feed.name}: {feed.url}" for feed in config.news_feeds)
    lines.append("")
    lines.append("**X accounts**")
    for account in config.x_accounts:
        name = f"{account.name} " if account.name else ""
        category = f", {account.category}" if account.category else ""
        profile = f" - {account.signal_profile}" if account.signal_profile else ""
        lines.append(f"- {name}@{account.username} (weight {account.weight:g}{category}){profile}")
    return lines


def _compact(text: str, limit: int) -> str:
    compacted = " ".join(text.split())
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 3].rstrip() + "..."


def _pick_top_signal_posts(config: AppConfig, posts: list[XPost], limit: int) -> list[tuple[XPost, set[str], set[str]]]:
    ranked = sorted(posts, key=lambda post: (post.engagement * post.account_weight, post.engagement), reverse=True)
    selected: list[tuple[XPost, set[str], set[str]]] = []
    seen_ids: set[str] = set()

    for post in ranked:
        if post.id in seen_ids:
            continue
        seen_ids.add(post.id)
        tickers = match_tickers(config.tickers, post.text)
        events = match_event_tags(config.event_keywords, post.text)
        if not tickers and not events:
            continue
        selected.append((post, tickers, events))
        if len(selected) >= limit:
            break

    return selected


def _format_date(value: datetime | None) -> str:
    if not value:
        return "unknown time"
    return value.strftime("%Y-%m-%d %H:%M UTC")
