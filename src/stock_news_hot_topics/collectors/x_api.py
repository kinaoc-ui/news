from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..models import AppConfig, XAccountConfig, XPost


class XApiClient:
    base_url = "https://api.x.com/2"

    def __init__(self, bearer_token: str, max_results: int = 25) -> None:
        if not bearer_token:
            raise ValueError("X_BEARER_TOKEN is required for X API collection.")

        self.max_results = max(10, min(max_results, 100))
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=30,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "XApiClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def collect_posts(self, config: AppConfig) -> list[XPost]:
        posts: dict[str, XPost] = {}
        account_weights = {account.username.lower(): account.weight for account in config.x_accounts}
        start_time = _format_rfc3339(datetime.now(timezone.utc) - timedelta(hours=config.lookback_hours))

        users = self._lookup_users(config.x_accounts)

        for account in config.x_accounts:
            user = users.get(account.username.lower())
            if user:
                for post in self._user_tweets(user["id"], account, start_time):
                    posts[post.id] = post

        for query in _ticker_queries(config):
            for post in self._recent_search(query, start_time, account_weights):
                posts[post.id] = post

        return sorted(posts.values(), key=lambda post: post.engagement, reverse=True)

    def _lookup_users(self, accounts: list[XAccountConfig]) -> dict[str, dict[str, str]]:
        if not accounts:
            return {}

        usernames = ",".join(account.username for account in accounts)
        response = self._get(
            "/users/by",
            params={"usernames": usernames, "user.fields": "username"},
        )
        data = response.get("data", []) if response else []
        return {str(user["username"]).lower(): {"id": str(user["id"]), "username": str(user["username"])} for user in data}

    def _user_tweets(self, user_id: str, account: XAccountConfig, start_time: str) -> list[XPost]:
        response = self._get(
            f"/users/{user_id}/tweets",
            params={
                "max_results": self.max_results,
                "start_time": start_time,
                "tweet.fields": "created_at,public_metrics",
                "exclude": "replies",
            },
        )
        tweets = response.get("data", []) if response else []
        return [
            _tweet_to_post(tweet, account.username, account.weight)
            for tweet in tweets
            if _looks_market_related(str(tweet.get("text", "")))
        ]

    def _recent_search(self, query: str, start_time: str, account_weights: dict[str, float]) -> list[XPost]:
        response = self._get(
            "/tweets/search/recent",
            params={
                "query": query,
                "max_results": self.max_results,
                "start_time": start_time,
                "tweet.fields": "created_at,public_metrics,author_id",
                "expansions": "author_id",
                "user.fields": "username",
            },
        )
        if not response:
            return []

        users_by_id = {
            str(user["id"]): str(user["username"])
            for user in response.get("includes", {}).get("users", [])
        }
        posts: list[XPost] = []

        for tweet in response.get("data", []):
            username = users_by_id.get(str(tweet.get("author_id")), "unknown")
            posts.append(_tweet_to_post(tweet, username, account_weights.get(username.lower(), 1.0)))

        return posts

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self.client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            print(f"X API request failed: {exc.response.status_code} {exc.response.text[:200]}")
            return {}
        except httpx.HTTPError as exc:
            print(f"X API request failed: {exc}")
            return {}
        return response.json()


def _tweet_to_post(tweet: dict[str, Any], username: str, account_weight: float) -> XPost:
    metrics = tweet.get("public_metrics", {}) or {}
    post_id = str(tweet["id"])
    return XPost(
        id=post_id,
        text=str(tweet.get("text", "")),
        author_username=username,
        created_at=_parse_x_datetime(tweet.get("created_at")),
        url=f"https://x.com/{username}/status/{post_id}" if username and username != "unknown" else "",
        like_count=int(metrics.get("like_count", 0)),
        reply_count=int(metrics.get("reply_count", 0)),
        repost_count=int(metrics.get("retweet_count", 0)),
        quote_count=int(metrics.get("quote_count", 0)),
        account_weight=account_weight,
    )


def _ticker_queries(config: AppConfig) -> list[str]:
    queries: list[str] = []
    for ticker in config.tickers:
        terms = [f"${ticker.symbol.split('.')[0]}", ticker.symbol, *ticker.names, *ticker.aliases]
        unique_terms = sorted({term.strip() for term in terms if term.strip()})
        quoted_terms = [f'"{term}"' if " " in term else term for term in unique_terms]
        query = f"({' OR '.join(quoted_terms)}) (stock OR stocks OR market OR earnings OR shares) -is:retweet"
        queries.append(query)
    return queries


def _looks_market_related(text: str) -> bool:
    lowered = text.lower()
    signals = ("$", "stock", "stocks", "market", "earnings", "shares", "fed", "rate", "inflation")
    return any(signal in lowered for signal in signals)


def _parse_x_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
