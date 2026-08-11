from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..models import AppConfig, XAccountConfig, XPost


def collect_x_with_browser(
    config: AppConfig,
    headless: bool = False,
    profile_dir: str | Path = ".browser-profile/x",
    posts_per_account: int = 5,
    browser_channel: str = "msedge",
) -> list[XPost]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Run: pip install -r requirements.txt") from exc

    posts: dict[str, XPost] = {}
    accounts = config.x_accounts[: max(0, config.max_browser_accounts)]
    profile_path = Path(profile_dir)
    profile_path.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        try:
            channel = None if browser_channel == "chromium" else browser_channel
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                headless=headless,
                viewport={"width": 1280, "height": 900},
                channel=channel,
            )
        except Exception as exc:
            raise RuntimeError(
                "Browser launch failed. Try installing browser runtime with "
                "'python -m playwright install chromium' or switch --browser-channel."
            ) from exc
        page = context.new_page()

        for account in accounts:
            try:
                account_posts = _collect_account_posts(page, account, posts_per_account, PlaywrightTimeoutError)
                account_posts = _filter_posts(account_posts, config)
                print(f"@{account.username}: collected {len(account_posts)} posts")
                for post in account_posts:
                    posts[post.id] = post
            except Exception as exc:
                print(f"Browser X collection failed for @{account.username}: {exc}")

        context.close()

    return sorted(posts.values(), key=lambda post: post.engagement, reverse=True)


def _collect_account_posts(
    page: Any,
    account: XAccountConfig,
    posts_per_account: int,
    timeout_error: type[Exception],
) -> list[XPost]:
    username = account.username.lstrip("@")
    page.goto(f"https://x.com/{username}", wait_until="domcontentloaded", timeout=45_000)
    page_text = page.inner_text("body")
    if "Nothing to see here" in page_text:
        print(f"Handle @{username} returned 'Nothing to see here' (likely invalid or unavailable).")
        return []

    try:
        page.wait_for_selector("article", timeout=15_000)
    except timeout_error:
        print(f"No visible X posts found for @{username}. You may need to log in in the opened browser.")
        return []

    page.mouse.wheel(0, 1200)
    page.wait_for_timeout(1500)

    raw_posts = page.evaluate(
        """
        ({ username, limit }) => {
          const articles = Array.from(document.querySelectorAll('article'));
          const posts = [];

          for (const article of articles) {
            const statusAnchor = Array.from(article.querySelectorAll('a[href*="/status/"]'))
              .map((anchor) => anchor.href)
              .find((href) => href.includes(`/${username}/status/`) || href.includes('/status/'));

            if (!statusAnchor) continue;

            let text = Array.from(article.querySelectorAll('[data-testid="tweetText"]'))
              .map((node) => node.innerText)
              .join('\\n')
              .trim();
            if (!text) {
              text = Array.from(article.querySelectorAll('div[lang]'))
                .map((node) => node.innerText)
                .join('\\n')
                .trim();
            }
            if (!text) {
              text = (article.innerText || '').trim();
            }

            if (!text) continue;

            const time = article.querySelector('time')?.getAttribute('datetime') || null;
            const groupLabel = article.querySelector('[role="group"]')?.getAttribute('aria-label') || '';
            const socialContext = article.querySelector('[data-testid="socialContext"]')?.innerText || '';
            const articleText = (article.innerText || '').trim();
            const isPinned = /pinned|已釘選|置頂|置顶/i.test(socialContext) || /pinned|已釘選|置頂|置顶/i.test(articleText);

            posts.push({
              id: statusAnchor.split('/status/')[1]?.split(/[?#]/)[0] || statusAnchor,
              text,
              url: statusAnchor,
              created_at: time,
              metrics_label: groupLabel,
              is_pinned: isPinned,
            });

            if (posts.length >= limit) break;
          }

          return posts;
        }
        """,
        {"username": username, "limit": posts_per_account},
    )

    return [
        _browser_item_to_post(item, account)
        for item in raw_posts
        if isinstance(item, dict) and item.get("id") and item.get("text") and not bool(item.get("is_pinned", False))
    ]


def _browser_item_to_post(item: dict[str, Any], account: XAccountConfig) -> XPost:
    metrics = _parse_metrics_label(str(item.get("metrics_label", "")))
    post_id = str(item["id"])
    created_at = _parse_datetime(item.get("created_at")) or _datetime_from_tweet_id(post_id)

    return XPost(
        id=post_id,
        text=_clean_tweet_text(str(item.get("text", "")), account.username),
        author_username=account.username,
        created_at=created_at,
        url=str(item.get("url", "")),
        like_count=metrics.get("likes", 0),
        reply_count=metrics.get("replies", 0),
        repost_count=metrics.get("reposts", 0),
        quote_count=metrics.get("quotes", 0),
        account_weight=account.weight,
    )


def _parse_metrics_label(label: str) -> dict[str, int]:
    metrics = {"replies": 0, "reposts": 0, "quotes": 0, "likes": 0}
    lowered = label.lower()

    patterns = {
        "replies": r"([\d.,]+[kmb]?)\s*(?:repl|replies|reply|則回覆|条回复|回覆|回复)",
        "reposts": r"([\d.,]+[kmb]?)\s*(?:repost|reposts|retweet|retweets|轉發|转发|次轉發|次转发)",
        "quotes": r"([\d.,]+[kmb]?)\s*(?:quote|quotes|引用)",
        "likes": r"([\d.,]+[kmb]?)\s*(?:like|likes|喜歡|喜欢)",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, lowered)
        if match:
            metrics[key] = _parse_compact_number(match.group(1))

    return metrics


def _parse_compact_number(value: str) -> int:
    cleaned = value.strip().lower().replace(",", "")
    multiplier = 1
    if cleaned.endswith("k"):
        multiplier = 1_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("m"):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("b"):
        multiplier = 1_000_000_000
        cleaned = cleaned[:-1]

    try:
        return int(float(cleaned) * multiplier)
    except ValueError:
        return 0


def _parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _filter_posts(posts: list[XPost], config: AppConfig) -> list[XPost]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=config.lookback_hours)
    filtered: list[XPost] = []
    for post in posts:
        created_at = _normalize_datetime(post.created_at) or _datetime_from_tweet_id(post.id)
        if created_at is None or created_at < cutoff:
            continue
        if not _looks_stock_related(post.text, config):
            continue
        filtered.append(post)
    return filtered


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _datetime_from_tweet_id(tweet_id: str) -> datetime | None:
    try:
        value = int(tweet_id)
    except ValueError:
        return None
    timestamp_ms = (value >> 22) + 1288834974657
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


def _clean_tweet_text(text: str, username: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    cleaned_lines: list[str] = []
    handle = username.lstrip("@").lower()
    metadata_pattern = re.compile(
        rf"^.*@{re.escape(handle)}\b.*(\d{{4}}年|\d{{1,2}}h\b|\b\d{{4}}-\d{{2}}-\d{{2}})",
        re.IGNORECASE,
    )

    for line in lines:
        if metadata_pattern.match(line):
            stripped = re.sub(rf"^.*@{re.escape(handle)}\s*", "", line, flags=re.IGNORECASE)
            stripped = re.sub(r"^\d{4}年\d{1,2}月\d{1,2}日\s*", "", stripped)
            stripped = re.sub(r"^\d{1,2}h\s*", "", stripped)
            if stripped:
                cleaned_lines.append(stripped)
            continue
        if line.lower().startswith(f"@{handle}"):
            continue
        cleaned_lines.append(line)

    return cleaned_lines[0] if cleaned_lines else text.strip()


def _looks_stock_related(text: str, config: AppConfig) -> bool:
    lowered = text.lower()
    market_terms = (
        "$",
        "stock",
        "stocks",
        "share",
        "shares",
        "earnings",
        "guidance",
        "valuation",
        "fed",
        "rate",
        "inflation",
        "market",
        "ai",
    )
    if any(term in lowered for term in market_terms):
        return True

    for ticker in config.tickers:
        candidates = [ticker.symbol, ticker.symbol.split(".")[0], *ticker.names, *ticker.aliases]
        for candidate in candidates:
            token = candidate.strip().lower()
            if token and token in lowered:
                return True
    return False
