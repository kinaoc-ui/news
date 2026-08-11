from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class TickerConfig:
    symbol: str
    names: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class XAccountConfig:
    username: str
    weight: float = 1.0
    name: str = ""
    category: str = ""
    signal_profile: str = ""


@dataclass(frozen=True)
class NewsFeedConfig:
    name: str
    url: str


@dataclass(frozen=True)
class AppConfig:
    lookback_hours: int
    max_results_per_query: int
    max_browser_accounts: int
    report_dir: str
    tickers: list[TickerConfig]
    x_accounts: list[XAccountConfig]
    news_feeds: list[NewsFeedConfig]
    event_keywords: dict[str, list[str]]


@dataclass(frozen=True)
class NewsItem:
    source: str
    title: str
    url: str
    published_at: datetime | None = None
    summary: str = ""

    @property
    def text(self) -> str:
        return f"{self.title} {self.summary}".strip()


@dataclass(frozen=True)
class XPost:
    id: str
    text: str
    author_username: str
    created_at: datetime | None = None
    url: str = ""
    like_count: int = 0
    reply_count: int = 0
    repost_count: int = 0
    quote_count: int = 0
    account_weight: float = 1.0

    @property
    def engagement(self) -> int:
        return self.like_count + self.reply_count + self.repost_count + self.quote_count


@dataclass
class AttentionItem:
    key: str
    kind: str
    score: float = 0.0
    mentions: int = 0
    x_post_count: int = 0
    news_count: int = 0
    engagement: int = 0
    unique_accounts: set[str] = field(default_factory=set)
    related_tickers: set[str] = field(default_factory=set)
    event_tags: set[str] = field(default_factory=set)
    representative_posts: list[XPost] = field(default_factory=list)
    representative_news: list[NewsItem] = field(default_factory=list)

    def as_report_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "kind": self.kind,
            "score": round(self.score, 2),
            "mentions": self.mentions,
            "x_post_count": self.x_post_count,
            "news_count": self.news_count,
            "engagement": self.engagement,
            "unique_accounts": sorted(self.unique_accounts),
            "related_tickers": sorted(self.related_tickers),
            "event_tags": sorted(self.event_tags),
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
