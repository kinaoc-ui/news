from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from typing import Callable
from urllib.parse import quote

import httpx


def send_notifications(title: str, body: str, channels: list[str]) -> list[str]:
    """Send digest via configured channels. Returns status lines."""
    senders: dict[str, Callable[[str, str], str]] = {
        "telegram": _send_telegram,
        "ntfy": _send_ntfy,
        "email": _send_email,
        "sms": _send_twilio_sms,
        "whatsapp": _send_twilio_whatsapp,
    }
    results: list[str] = []
    for raw in channels:
        name = raw.strip().lower()
        if not name:
            continue
        sender = senders.get(name)
        if not sender:
            results.append(f"{name}: unknown channel")
            continue
        try:
            results.append(f"{name}: {sender(title, body)}")
        except Exception as exc:  # noqa: BLE001
            results.append(f"{name}: FAILED — {exc}")
    return results


def send_telegram_text(text: str) -> str:
    """Send a plain Telegram message (used by more-N replies)."""
    return _send_telegram("", text)


def _send_telegram(title: str, body: str) -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
    text = f"{title}\n\n{body}".strip() if title else body.strip()
    # Telegram hard limit ~4096
    if len(text) > 4000:
        text = text[:3990] + "…"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
        )
        resp.raise_for_status()
    return "sent"


def _send_ntfy(title: str, body: str) -> str:
    topic = os.getenv("NTFY_TOPIC", "").strip()
    base = os.getenv("NTFY_URL", "https://ntfy.sh").rstrip("/")
    if not topic:
        raise RuntimeError("Set NTFY_TOPIC in .env (e.g. your-secret-topic)")
    url = f"{base}/{quote(topic, safe='')}"
    payload = body if len(body) < 3500 else body[:3490] + "…"
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            url,
            content=payload.encode("utf-8"),
            headers={
                "Title": title[:120],
                "Priority": "default",
                "Tags": "chart_with_upwards_trend",
            },
        )
        resp.raise_for_status()
    return "sent"


def _send_email(title: str, body: str) -> str:
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    to_addr = os.getenv("NOTIFY_EMAIL_TO", "").strip() or user
    from_addr = os.getenv("NOTIFY_EMAIL_FROM", "").strip() or user
    port = int(os.getenv("SMTP_PORT", "587"))
    if not host or not user or not password or not to_addr:
        raise RuntimeError("Set SMTP_HOST, SMTP_USER, SMTP_PASSWORD, NOTIFY_EMAIL_TO in .env")
    msg = EmailMessage()
    msg["Subject"] = title
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    return f"sent to {to_addr}"


def _send_twilio_sms(title: str, body: str) -> str:
    return _twilio_message(title, body, whatsapp=False)


def _send_twilio_whatsapp(title: str, body: str) -> str:
    return _twilio_message(title, body, whatsapp=True)


def _twilio_message(title: str, body: str, *, whatsapp: bool) -> str:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_num = os.getenv("TWILIO_FROM", "").strip()
    to_num = os.getenv("TWILIO_TO", "").strip()
    if not sid or not token or not from_num or not to_num:
        raise RuntimeError("Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM, TWILIO_TO in .env")
    text = f"{title}\n\n{body}"
    # SMS ~1600 practical; WhatsApp higher but keep short
    limit = 1500 if not whatsapp else 3500
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    from_value = f"whatsapp:{from_num}" if whatsapp else from_num
    to_value = f"whatsapp:{to_num}" if whatsapp else to_num
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            url,
            data={"From": from_value, "To": to_value, "Body": text},
            auth=(sid, token),
        )
        resp.raise_for_status()
    return "sent"
