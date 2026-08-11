# Stock Hot Topics Program

This tool collects stock-related news and X posts, then ranks the stocks and market conversations that are getting the most attention.

The ranking is based on X discussion volume, like/reply/repost/quote engagement, number of accounts involved, configured expert-account weights, and supporting news coverage.

## Setup

1. Install Python 3.10 or newer.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Install the browser engine for browser-based X collection:

```bash
python -m playwright install chromium
```

4. Create your local config:

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item config.example.yaml config.yaml
Copy-Item .env.example .env
```

5. Optional: edit `.env` and set your X API bearer token if you want official API mode:

```bash
X_BEARER_TOKEN=your-token-here
```

6. Edit `config.yaml` to add the stocks, company names, X accounts, account weights, RSS feeds, and event keywords you care about.

## Run

Run with browser-based X collection:

```bash
python scripts/run_daily.py --x-source browser
```

By default on Windows this uses Edge (`--browser-channel msedge`) with a persistent profile at `.browser-profile/x`. If X asks you to log in, log in manually in that browser window, close it after the run, then run the command again.

If login fails on one engine, try another:

```bash
python scripts/run_daily.py --x-source browser --browser-channel msedge
python scripts/run_daily.py --x-source browser --browser-channel chrome
python scripts/run_daily.py --x-source browser --browser-channel chromium
```

Run with official X API collection:

```bash
python scripts/run_daily.py --x-source api
```

Run with news only, without calling X:

```bash
python scripts/run_daily.py --x-source none
```

Use a custom config or output directory:

```bash
python scripts/run_daily.py --x-source browser --config config.yaml --output-dir reports
```

Reports are written to:

```text
reports/YYYY-MM-DD.md
```

## Config Guide

`tickers` controls which stocks the program should recognize. Add both ticker symbols and common company names.

```yaml
tickers:
  - symbol: NVDA
    names:
      - Nvidia
      - NVIDIA
    aliases:
      - "$NVDA"
```

`x_accounts` controls the expert/fund-manager accounts to monitor. Higher weight means that account's engagement contributes more to the attention score.

```yaml
max_browser_accounts: 10

x_accounts:
  - name: Bill Ackman
    username: BillAckman
    category: Activist / Long
    weight: 1.5
    signal_profile: Deep-dive threads on specific names; activist campaigns and public letters can move targets.
```

Browser mode reads only the first `max_browser_accounts` accounts from this list, so put your highest-signal accounts first.

`event_keywords` groups related catalysts so the report can surface broader market conversations as well as individual stocks.

```yaml
event_keywords:
  earnings:
    - earnings
    - guidance
  macro:
    - Fed
    - rate cut
```

## Browser X Notes

Browser mode is designed for small-scale monitoring of a curated account list, such as 10 high-signal investors or short sellers. It is not designed for bulk scraping.

Useful command:

```bash
python scripts/run_daily.py --x-source browser --posts-per-account 5
```

If you need to see the browser and log in manually, do not use `--browser-headless`. If you already logged in once and want a hidden run, you can try:

```bash
python scripts/run_daily.py --x-source browser --browser-headless
```

X changes its website often, and login walls or captchas can block collection. If an account cannot be read, the program prints a warning and continues with the other accounts and news data.

## Expanding The Follow List

Start with people whose posts have a plausible path to market impact:

- Activists: public campaigns, board fights, takeover pressure, specific stock theses.
- Short sellers: fraud reports, accounting concerns, borrow pressure, target-specific research.
- Macro managers: Fed, rates, currencies, credit, commodities.
- Sector specialists: AI, semis, biotech, energy, China ADRs, crypto equities.
- Retail catalysts: accounts whose posting can create immediate attention in meme or high-short-interest names.

For each candidate, add `name`, `username`, `category`, `weight`, and `signal_profile` to `config.yaml`. Keep the top 10 to 20 accounts high quality; more accounts creates more noise and makes browser collection less stable.

Review the report weekly. If an account produces noisy general commentary with no stock-specific signal, lower its `weight` or move it lower in the list. If an account repeatedly posts early, specific, market-moving information, raise its `weight`.

## X API Notes

This project uses the official X API. Depending on your X API plan, some endpoints or request volume may be limited.

The collector currently uses:

- Recent search for configured tickers and company names.
- User timeline reads for configured expert/fund-manager accounts.
- Public metrics: likes, replies, reposts, and quotes.

If X API access is rate-limited or unavailable, the program will print the API error and continue with any data already collected.

## How Ranking Works

Each hot item can be a stock, such as `NVDA`, or an event conversation, such as `earnings` or `macro`.

The attention score uses:

- Number of matching X posts.
- Total X engagement.
- Number of unique X accounts involved.
- Expert-account weights from `config.yaml`.
- Number of related news items.

The report is designed to answer: "Which stocks or market events are people paying attention to right now, and what are they saying?"

## Local First Screen Digest (no Cursor)

Reads the newest `FirstScreen_*_comma.txt` from your screening reports folder, pulls news (RSS + per-symbol Yahoo/Google), optionally X, writes a digest under `reports/`, and can push it to your phone.

```powershell
# Dry run (report only)
python scripts/run_fs_digest.py --dry-run --x-source none

# With X browser accounts from config.yaml
python scripts/run_fs_digest.py --x-source browser --browser-headless

# Send once (after configuring notify)
python scripts/run_fs_digest.py --x-source none --notify telegram
```

Install Windows Task Scheduler jobs for **08:30 / 13:00 / 18:00** local time:

```powershell
scripts\install_fs_digest_tasks.bat
```

Logs: `.local/logs/fs_digest.log`

### How to text / notify you

| Method | Cost | Setup |
|--------|------|--------|
| **Telegram** | Free | BotFather token + your chat id → `notify.channels: [telegram]` |
| **ntfy** | Free | Phone app + secret topic → `notify.channels: [ntfy]` |
| **Email** | Free (Gmail app password etc.) | SMTP vars in `.env` → `email` |
| **SMS** | Paid (Twilio) | Twilio SID/token/from/to → `sms` |
| **WhatsApp** | Paid (Twilio WhatsApp) | Same Twilio vars, WhatsApp-enabled number → `whatsapp` |

Copy `.env.example` → `.env`, fill the channel you want, then set in `config.yaml`:

```yaml
notify:
  channels:
    - telegram   # or ntfy / email / sms / whatsapp
```

Telegram short message has **no links**. Reply `more 1` (or `more N`) to the bot for detail.

```powershell
# Process pending Telegram more N commands once
python scripts/tg_reply_more.py

# Or send detail for item 1 directly
python scripts/tg_reply_more.py -n 1
```

State file: `reports/last_fs_digest.json`

## GitHub 上跑（唔使部機長開 TG listener）

可以，但有限制。`news` 資料夾而家**仲未係 git repo**——要先 `git init`、推去 GitHub（例如 `kinaoc-ui/...`），Actions 先會跑。

### 做得到咩
- **定時** 08:30／13:00／18:00（HKT）：用 `.github/workflows/fs_digest.yml` → 掃新聞 → 推 Telegram
- **手動**：GitHub Actions 頁撳 **Run workflow**（`workflow_dispatch`）

### TG 打 `run` 即刻跑？
GitHub Actions **唔可以**好似本機咁長期等 Telegram。要即時 `run`，要額外一件「收 webhook」嘅嘢（例如 Cloudflare Worker）再觸發 `workflow_dispatch`／`repository_dispatch`。嫌麻煩可以：定時用 GitHub + 得閒先本機／Actions 手動掣。

### First Screen list
Actions 讀唔到你電腦。每日 FS 完後要把最新 `FirstScreen_*_comma.txt` 複製去 `data/first_screen/latest_comma.txt` 再 **commit／push**。

### X
GitHub **唔適合**用 Edge browser login。請用 Repo Secret `X_BEARER_TOKEN`（API）；冇 token 就新聞-only。

### Secrets（Repo → Settings → Secrets）
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- 可選 `X_BEARER_TOKEN`

**唔好** commit `.env`／token。你之前喺 chat 貼過 token，建議 BotFather **Revoke** 換新。

### 本機 9edge
開 `9edge.bat` 會一併開 TG listener（本機 `run`／`more N`）。若全面改用 GitHub 定時＋手動，可以唔再開本機 listener。

## TG 被 hack 會唔會控制到部機？

而家設計：**唔會变成任意遙控部機**。

- Bot 只認你嘅 `TELEGRAM_CHAT_ID`，指令只有固定嘅 `run`／`more N`
- `run` 只會跑指定嘅 `run_fs_digest.py`（掃新聞推 TG），**唔係**任意 shell
- 若有人盜用你個 TG／知 chat id，最多係不停叫你跑 digest（耗 CPU／網絡），睇到摘要
- 上 GitHub 都一樣：只會跑 workflow 入面寫死嘅步驟，控制唔到你部 PC

仍然要保護：bot token、chat id、唔好公開 Secrets；換過已洩露嘅 token。

## Disclaimer

This tool is for research and market monitoring only. It is not financial advice.
