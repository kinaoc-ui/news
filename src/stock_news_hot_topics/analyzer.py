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


# Common English / phrase collisions (GAP up, a bill, …) — never bare-word match.
_AMBIGUOUS_TICKERS = frozenset(
    {
        "GAP",
        "BILL",
        "REAL",
        "LOVE",
        "CARE",
        "OPEN",
        "FAST",
        "FISH",
        "PLAY",
        "MOVE",
        "SAFE",
        "GAIN",
        "FOLD",
        "SHOP",
        "COST",
        "BEST",
        "NEXT",
        "WELL",
        "GOOD",
        "TRUE",
        "FREE",
        "LIVE",
        "PACK",
        "POST",
        "UNIT",
        "SPOT",
        "ROCK",
        "GOLD",
        "IRON",
        "AIR",
        "RUN",
        "APP",
        "ANY",
        "ALL",
        "ARE",
        "CAN",
        "FOR",
        "HAS",
        "HER",
        "HIS",
        "HOW",
        "MAN",
        "NEW",
        "NOW",
        "OLD",
        "ONE",
        "OUR",
        "OUT",
        "OWN",
        "SEE",
        "TWO",
        "WAY",
        "WHO",
        "YOU",
        "BIG",
        "LOW",
        "KEY",
        "NET",
        "AGO",
        "CUBE",
        "TREE",
        "LEAF",
        "SNOW",
        "WIND",
        "FIRE",
        "LAND",
        "MAIN",
        "MARK",
        "MASS",
        "PLUS",
        "STAY",
        "TURN",
        "VIEW",
        "FORM",
        "FUND",
        "DATA",
        "EDIT",
        "TECH",
        "TEAM",
        "HOME",
        "HOPE",
        "JOBS",
        "LIFE",
        "LONG",
        "MAKE",
        "CEO",
        "CFO",
        "COO",
    }
)


def has_clear_ticker_ref(symbol: str, text: str) -> bool:
    """True only when the ticker is marked as an equity, not a common word."""
    s = re.escape(symbol.upper())
    patterns = (
        rf"\${s}\b",
        rf"\b(?:NYSE|NASDAQ|AMEX|OTC|NYSEARCA)\s*:\s*{s}\b",
        rf"\(\s*(?:NYSE|NASDAQ|AMEX|OTC)?\s*:?\s*{s}\s*\)",
        rf"\b{s}\s+(?:stock|shares|equity|inc\.?|corp\.?|ltd\.?)\b",
    )
    return any(re.search(p, text, flags=re.IGNORECASE) for p in patterns)


def extract_clear_tickers(text: str) -> set[str]:
    found: set[str] = set()
    for match in re.finditer(
        r"\$([A-Za-z]{1,5})\b"
        r"|\b(?:NYSE|NASDAQ|AMEX|OTC|NYSEARCA)\s*:\s*([A-Za-z]{1,5})\b"
        r"|\(\s*(?:NYSE|NASDAQ|AMEX|OTC)?\s*:?\s*([A-Za-z]{1,5})\s*\)",
        text,
        flags=re.IGNORECASE,
    ):
        sym = next((g for g in match.groups() if g), None)
        if sym:
            found.add(sym.upper())
    return found


def is_ambiguous_ticker(symbol: str) -> bool:
    return len(symbol) <= 2 or symbol.upper() in _AMBIGUOUS_TICKERS


def news_belongs_to_symbol(symbol: str, text: str, *, source: str = "") -> bool:
    """Decide whether a headline/body is actually about this ticker."""
    sym = symbol.upper()
    if has_clear_ticker_ref(sym, text):
        return True

    others = extract_clear_tickers(text) - {sym}
    if others:
        return False

    source_sym = ""
    if ":" in source:
        source_sym = source.rsplit(":", 1)[-1].upper()

    # Cross-article word matches (BILL in "a bill", GAP in "gap up") are rejected.
    if source_sym != sym:
        return False

    if is_ambiguous_ticker(sym):
        return False

    # Non-ambiguous symbol-specific feed: require the ticker token somewhere.
    return _wordish_match(sym, text)


def match_tickers(tickers: list[TickerConfig], text: str) -> set[str]:
    lowered = text.lower()
    matches: set[str] = set()

    for ticker in tickers:
        symbol = ticker.symbol.upper()

        # Short / English-word tickers: only clear equity refs
        if is_ambiguous_ticker(symbol):
            if has_clear_ticker_ref(symbol, text):
                matches.add(ticker.symbol)
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
