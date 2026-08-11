from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .analyzer import match_event_tags, match_tickers
from .first_screen_list import latest_first_screen_comma, parse_first_screen_symbols, tickers_from_symbols
from .models import AppConfig, NewsItem, XPost, utc_now
from .symbol_news import collect_symbol_news, is_noteworthy

_TAG_ZH = {
    "earnings": "業績／指引",
    "ai": "AI相關",
    "macro": "宏觀",
    "deal": "併購／交易",
}


@dataclass
class DigestItem:
    n: int
    symbol: str
    short: str
    detail: str
    url: str = ""
    source: str = ""
    kind: str = "news"  # news | x | note


@dataclass
class DigestResult:
    title: str
    body: str
    list_path: Path
    symbols: list[str]
    items: list[DigestItem] = field(default_factory=list)
    x_note: str = ""


def build_fs_digest(
    config: AppConfig,
    *,
    first_screen_dir: Path,
    lookback_hours: int,
    general_news: list[NewsItem],
    x_posts: list[XPost],
    max_bullets: int = 12,
) -> DigestResult:
    list_path = latest_first_screen_comma(first_screen_dir)
    if list_path is None:
        raise FileNotFoundError(f"No FirstScreen_*_comma.txt under {first_screen_dir}")

    symbols = parse_first_screen_symbols(list_path)
    if not symbols:
        raise ValueError(f"First Screen list is empty: {list_path}")

    tickers = tickers_from_symbols(symbols)
    symbol_news = collect_symbol_news(symbols, lookback_hours)
    all_news = _dedupe_news([*general_news, *symbol_news])

    by_symbol: dict[str, list[NewsItem]] = defaultdict(list)
    for news in all_news:
        matched = match_tickers(tickers, news.text)
        source_sym = _source_symbol(news.source)
        if source_sym and source_sym in {t.symbol for t in tickers}:
            matched.add(source_sym)
        for symbol in matched:
            by_symbol[symbol].append(news)

    x_by_symbol: dict[str, list[XPost]] = defaultdict(list)
    for post in x_posts:
        for symbol in match_tickers(tickers, post.text):
            x_by_symbol[symbol].append(post)

    scored: list[tuple[int, DigestItem]] = []

    for symbol in symbols:
        news_list = by_symbol.get(symbol, [])
        posts = x_by_symbol.get(symbol, [])
        candidates = [n for n in news_list if is_noteworthy(n.text)]
        if not candidates and news_list:
            for n in news_list[:2]:
                if match_event_tags(config.event_keywords, n.text):
                    candidates.append(n)
        if not candidates and not posts:
            continue

        if candidates:
            top = candidates[0]
            tags = sorted(match_event_tags(config.event_keywords, top.text))
            tag_zh = "、".join(_TAG_ZH.get(t, t) for t in tags)
            headline = _clip(top.title, 88)
            # Short line must carry the actual story — never bare "相關消息".
            if tag_zh:
                short = f"{symbol} — {tag_zh}：{headline}"
            else:
                short = f"{symbol} — {headline}"
            summary_bit = _clip(top.summary, 280) if top.summary else ""
            detail_parts = [
                f"{symbol}",
                f"重點：{tag_zh or '新聞'}",
                f"標題：{top.title}",
            ]
            if summary_bit and summary_bit != top.title:
                detail_parts.append(f"摘要：{summary_bit}")
            detail_parts.append(f"來源：{top.source}")
            if len(candidates) > 1:
                extras = "; ".join(_clip(n.title, 60) for n in candidates[1:4])
                detail_parts.append(f"其他：{extras}")
            detail = "\n".join(detail_parts)
            score = 100 + len(candidates) * 5 + len(posts)
            scored.append(
                (
                    score,
                    DigestItem(
                        n=0,
                        symbol=symbol,
                        short=short,
                        detail=detail,
                        url=top.url,
                        source=top.source,
                        kind="news",
                    ),
                )
            )
        elif posts:
            top_post = max(posts, key=lambda p: p.engagement * p.account_weight)
            excerpt = _clip(top_post.text, 120)
            short = f"{symbol} — X @{top_post.author_username}：{_clip(top_post.text, 70)}"
            detail = (
                f"{symbol}\n"
                f"重點：X 討論（@{top_post.author_username}）\n"
                f"內容：{excerpt}"
            )
            score = 40 + top_post.engagement
            scored.append(
                (
                    score,
                    DigestItem(
                        n=0,
                        symbol=symbol,
                        short=short,
                        detail=detail,
                        url=top_post.url or f"https://x.com/{top_post.author_username}",
                        source=f"X @{top_post.author_username}",
                        kind="x",
                    ),
                )
            )

    scored.sort(key=lambda row: (-row[0], row[1].symbol))
    items: list[DigestItem] = []
    for i, (_, item) in enumerate(scored[:max_bullets], start=1):
        item.n = i
        items.append(item)

    x_matched = sum(1 for it in items if it.kind == "x")
    x_note = ""
    if x_posts and x_matched == 0:
        x_note = "X：已掃描，但對今日 First Screen list 暫無可用訊號。"
    elif not x_posts:
        x_note = "X：今輪未能取得貼文（可能未登入／略過）。"

    now = utc_now().astimezone()
    title = f"FS新聞 {now.strftime('%m-%d %H:%M')}"
    body = format_short_digest(title, list_path.name, items, x_note=x_note)
    return DigestResult(
        title=title,
        body=body,
        list_path=list_path,
        symbols=symbols,
        items=items,
        x_note=x_note,
    )


def _clip(text: str, max_len: int) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def format_short_digest(
    title: str,
    list_name: str,
    items: list[DigestItem],
    *,
    x_note: str = "",
) -> str:
    lines = [title, f"列表: {list_name}", ""]
    if items:
        for item in items:
            lines.append(f"{item.n}. {item.short}")
    else:
        lines.append("今輪 First Screen list 冇特別值得留意嘅新聞。")
    if x_note:
        lines.extend(["", x_note])
    lines.extend(["", "回覆 more 1 可睇詳情"])
    return "\n".join(lines)


def write_digest_file(report_dir: Path, title: str, body: str) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = report_dir / f"fs_digest_{stamp}.md"
    path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    return path


def save_last_digest_state(
    report_dir: Path,
    *,
    title: str,
    list_name: str,
    items: list[DigestItem],
    x_note: str = "",
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    path = report_dir / "last_fs_digest.json"
    payload = {
        "title": title,
        "list_name": list_name,
        "created_at": utc_now().isoformat(),
        "x_note": x_note,
        "items": [asdict(item) for item in items],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_last_digest_state(report_dir: Path) -> dict | None:
    path = report_dir / "last_fs_digest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def format_item_detail(item: DigestItem | dict) -> str:
    if isinstance(item, dict):
        n = item.get("n")
        detail = str(item.get("detail") or "")
        url = str(item.get("url") or "")
        source = str(item.get("source") or "")
    else:
        n = item.n
        detail = item.detail
        url = item.url
        source = item.source
    lines = [f"詳情 #{n}", detail]
    if source:
        lines.append(f"來源名：{source}")
    if url:
        lines.append(f"連結：{url}")
    return "\n".join(lines)


def _dedupe_news(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    out: list[NewsItem] = []
    for item in items:
        key = item.url or item.title
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _source_symbol(source: str) -> str | None:
    if ":" not in source:
        return None
    return source.rsplit(":", 1)[-1].upper()
