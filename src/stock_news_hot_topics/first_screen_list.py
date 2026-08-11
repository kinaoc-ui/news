from __future__ import annotations

import re
from pathlib import Path

from .models import TickerConfig

_EXCHANGE_PREFIX = re.compile(
    r"^(?:NASDAQ|NYSE|AMEX|OTC|BATS|ARCA|CBOE|NYSEARCA|NYSEAMERICAN):",
    re.IGNORECASE,
)


def latest_first_screen_comma(reports_dir: str | Path) -> Path | None:
    root = Path(reports_dir)
    if not root.is_dir():
        return None
    files = [p for p in root.glob("FirstScreen_*_*_comma.txt") if p.is_file()]
    legacy = [p for p in root.glob("FirstScreen_*/FirstScreen_*_comma.txt") if p.is_file()]
    all_files = sorted({*files, *legacy}, key=lambda p: p.stat().st_mtime, reverse=True)
    return all_files[0] if all_files else None


def parse_first_screen_symbols(path: Path) -> list[str]:
    """Return bare ticker symbols from a TV import comma/sector txt."""
    symbols: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Sector headers look like "### Foo — Bar"
        if line.startswith("###"):
            continue
        token = line.split()[0].strip(",;")
        if not token or token.startswith("#"):
            continue
        symbol = _EXCHANGE_PREFIX.sub("", token).upper()
        if not symbol or symbol in seen:
            continue
        # Skip pure index / crypto style if they slip in
        if ":" in symbol:
            symbol = symbol.split(":")[-1]
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def tickers_from_symbols(symbols: list[str]) -> list[TickerConfig]:
    return [
        TickerConfig(
            symbol=symbol,
            names=[],
            aliases=[f"${symbol}", symbol],
        )
        for symbol in symbols
    ]
