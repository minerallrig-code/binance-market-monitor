import os
import sys
from urllib.parse import urlparse

import requests

API_BASE = "https://api.telegram.org"
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "-1003065943939")
THREAD_ID = os.environ.get("TELEGRAM_MESSAGE_THREAD_ID", "114")
CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096


def require_https_url(value, label):
    value = (value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{label} must be a valid HTTPS URL")
    return value


def telegram(method, data, files=None):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    response = requests.post(
        f"{API_BASE}/bot{token}/{method}",
        data=data,
        files=files,
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {payload.get('description', 'unknown error')}")
    return payload["result"]


def base_data():
    data = {"chat_id": CHAT_ID}
    if THREAD_ID:
        data["message_thread_id"] = THREAD_ID
    return data


def split_text(text, limit=MESSAGE_LIMIT):
    parts = []
    remaining = text.strip()
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        parts.append(remaining)
    return parts


def main():
    text = os.environ.get("NEWS_TEXT", "").strip()
    image_url = require_https_url(os.environ.get("NEWS_IMAGE_URL"), "NEWS_IMAGE_URL")
    source_url = require_https_url(os.environ.get("NEWS_SOURCE_URL"), "NEWS_SOURCE_URL")

    if not text:
        raise ValueError("NEWS_TEXT is required")
    if source_url and source_url not in text:
        text = f"{text}\n\nИсточник: {source_url}"

    if image_url:
        caption = text[:CAPTION_LIMIT]
        telegram("sendPhoto", {**base_data(), "photo": image_url, "caption": caption})
        print("News image and caption sent.")
        remainder = text[CAPTION_LIMIT:].strip()
        if remainder:
            for part in split_text(remainder):
                telegram("sendMessage", {**base_data(), "text": part})
            print("News continuation sent.")
    else:
        for part in split_text(text):
            telegram("sendMessage", {**base_data(), "text": part})
        print("News text sent.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Publication failed: {exc}", file=sys.stderr)
        raise
