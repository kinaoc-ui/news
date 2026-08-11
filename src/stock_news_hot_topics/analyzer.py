from __future__ import annotations

import math
import re
from collections import defaultdict

from .models import AppConfig, AttentionItem, NewsItem, TickerConfig, XPost


def analyze_attention(config: AppConfig, news_items: list[NewsItem], x_posts: list[XPost]) -> list[AttentionItem]:
    items: dict[tuple[str, str], AttentionItem] = {}
    seen_news_by_item: dict[tuple[str, str], set[str]] = defaultdict(set)
    seen_posts_by_item: dict[tuple[str, str], set[str]] = defaultdict(set)

    for post in x_posts:
        tickers = match_tickers(config.tickers, post.text)
        event_tags = match_event_tags(config.event_keywords, post.text)

        for symbol in tickers:
            item = _item(items, symbol, "stock")
            _add_post(item, post, seen_posts_by_item)
            item.event_tags.update(event_tags)

        for tag in event_tags:
            item = _item(items, tag, "event")
            _add_post(item, post, seen_posts_by_item)
            item.related_tickers.update(tickers)
            item.event_tags.add(tag)

    for news in news_items:
        tickers = match_tickers(config.tickers, news.text)
        event_tags = match_event_tags(config.event_keywords, news.text)

        for symbol in tickers:
            item = _item(items, symbol, "stock")
            _add_news(item, news, seen_news_by_item)
            item.event_tags.update(event_tags)

        for tag in event_tags:
            item = _item(items, tag, "event")
            _add_news(item, news, seen_news_by_item)
            item.related_tickers.update(tickers)
            item.event_tags.add(tag)

    ranked = list(items.values())
    for item in ranked:
        item.representative_posts.sort(key=lambda post: post.engagement * post.account_weight, reverse=True)
        item.representative_news.sort(key=_news_sort_key, reverse=True)
        item.representative_posts = item.representative_posts[:5]
        item.representative_news = item.representative_news[:5]
        item.score = _score(item)

    return sorted(ranked, key=lambda item: item.score, reverse=True)


def match_tickers(tickers: list[TickerConfig], text: str) -> set[str]:
    lowered = text.lower()
    matches: set[str] = set()

    for ticker in tickers:
        # Short tickers (A, T, …) false-positive easily — require $TICKER or exchange:TICKER
        if len(ticker.symbol) <= 2:
            if (
                f"${ticker.symbol.lower()}" in lowered
                or f":{ticker.symbol.lower()}" in lowered
                or f"({ticker.symbol.lower()})" in lowered
                or f"nyse:{ticker.symbol.lower()}" in lowered
                or f"nasdaq:{ticker.symbol.lower()}" in lowered
            ):
                matches.add(ticker.symbol)
            continue

        # Job-title collision: COO/CEO/CFO as standalone words in headlines
        if ticker.symbol in {"COO", "CEO", "CFO"} and not (
            f"${ticker.symbol.lower()}" in lowered
            or f":{ticker.symbol.lower()}" in lowered
            or f"({ticker.symbol.lower()})" in lowered
        ):
            # still allow clear equity phrasing
            if not re.search(rf"\b{re.escape(ticker.symbol)}\b.*\b(stock|shares|nyse|nasdaq)\b", text, re.I):
                continue

        terms = [ticker.symbol, ticker.symbol.split(".")[0], *ticker.names, *ticker.aliases]
        for term in terms:
            clean = term.strip()
            if not clean:
                continue
            if clean.startswith("$"):
                if clean.lower() in lowered:
                    matches.add(ticker.symbol)
                    break
            elif _wordish_match(clean, text):
                matches.add(ticker.symbol)
                break

    return matches


def match_event_tags(event_keywords: dict[str, list[str]], text: str) -> set[str]:
    tags: set[str] = set()

    for tag, keywords in event_keywords.items():
        for keyword in keywords:
            if _wordish_match(keyword, text):
                tags.add(tag)
                break

    return tags


def _item(items: dict[tuple[str, str], AttentionItem], key: str, kind: str) -> AttentionItem:
    item_key = (kind, key)
    if item_key not in items:
        items[item_key] = AttentionItem(key=key, kind=kind)
    return items[item_key]


def _add_post(
    item: AttentionItem,
    post: XPost,
    seen_posts_by_item: dict[tuple[str, str], set[str]],
) -> None:
    item_key = (item.kind, item.key)
    if post.id in seen_posts_by_item[item_key]:
        return

    seen_posts_by_item[item_key].add(post.id)
    item.mentions += 1
    item.x_post_count += 1
    item.engagement += post.engagement
    item.unique_accounts.add(post.author_username)
    item.representative_posts.append(post)


def _add_news(
    item: AttentionItem,
    news: NewsItem,
    seen_news_by_item: dict[tuple[str, str], set[str]],
) -> None:
    item_key = (item.kind, item.key)
    if news.url in seen_news_by_item[item_key]:
        return

    seen_news_by_item[item_key].add(news.url)
    item.mentions += 1
    item.news_count += 1
    item.representative_news.append(news)


def _score(item: AttentionItem) -> float:
    weighted_engagement = sum(post.engagement * post.account_weight for post in item.representative_posts)
    return (
        item.x_post_count * 5
        + item.news_count * 2
        + len(item.unique_accounts) * 6
        + math.log1p(item.engagement) * 8
        + math.log1p(weighted_engagement) * 6
    )


def _news_sort_key(news: NewsItem) -> float:
    if not news.published_at:
        return 0.0
    return news.published_at.timestamp()


def _wordish_match(term: str, text: str) -> bool:
    escaped = re.escape(term)
    if re.search(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", text, flags=re.IGNORECASE):
        return True
    return term.lower() in text.lower() if any(ord(char) > 127 for char in term) else False
