import base64
import json
import os
import sys
import subprocess
from pathlib import Path
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
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(
            f"Telegram {method} failed: {payload.get('description', 'unknown error')}"
        )
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


def publish(text, image_url=None, image_base64=None, image_svg_path=None, source_url=None):
    text = (text or "").strip()
    if not text:
        raise ValueError("news text is required")

    source_url = require_https_url(source_url, "source_url")
    image_url = require_https_url(image_url, "image_url")
    if source_url and source_url not in text:
        text = f"{text}\n\nИсточник: {source_url}"

    if image_svg_path:
        import cairosvg
        svg_path = Path(image_svg_path)
        if not svg_path.is_file():
            raise FileNotFoundError(f"Image SVG not found: {image_svg_path}")
        image_bytes = cairosvg.svg2png(url=str(svg_path), output_width=1200)
        caption = text[:CAPTION_LIMIT]
        telegram(
            "sendPhoto",
            {**base_data(), "caption": caption},
            files={"photo": ("turvleto-quang-tri.png", image_bytes, "image/png")},
        )
        print("Telegram confirmed photo + caption.")
        remainder = text[CAPTION_LIMIT:].strip()
    elif image_base64:
        image_bytes = base64.b64decode(image_base64, validate=True)
        if not image_bytes:
            raise ValueError("image_base64 decoded to an empty file")
        caption = text[:CAPTION_LIMIT]
        telegram(
            "sendPhoto",
            {**base_data(), "caption": caption},
            files={"photo": ("turvleto-news.jpg", image_bytes, "image/jpeg")},
        )
        print("Telegram confirmed photo + caption.")
        remainder = text[CAPTION_LIMIT:].strip()
    elif image_url:
        caption = text[:CAPTION_LIMIT]
        telegram("sendPhoto", {**base_data(), "photo": image_url, "caption": caption})
        print("Telegram confirmed photo + caption.")
        remainder = text[CAPTION_LIMIT:].strip()
    else:
        remainder = text
        print("No image supplied; text-only publication.")

    if remainder:
        for part in split_text(remainder):
            telegram("sendMessage", {**base_data(), "text": part})
        print("Telegram confirmed text continuation.")


def load_approved_items():
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        raise ValueError("GITHUB_EVENT_PATH is missing")
    event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    paths = []

    # Use the push range; the commits array may be absent in API-generated pushes.
    before = event.get("before")
    after = event.get("after") or os.environ.get("GITHUB_SHA")
    zero_sha = "0" * 40
    if after:
        if before and before != zero_sha:
            command = ["git", "diff", "--name-only", f"{before}..{after}"]
        else:
            command = ["git", "show", "--pretty=", "--name-only", after]
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        paths.extend(line.strip() for line in result.stdout.splitlines() if line.strip())

    # Retain the event commit list as a fallback.
    for commit in event.get("commits", []):
        paths.extend(commit.get("added", []))
        paths.extend(commit.get("modified", []))

    approved = [
        path for path in dict.fromkeys(paths)
        if path.startswith("projects/turvleto-news/approved/")
        and path.endswith(".json")
    ]
    if not approved:
        raise ValueError(
            "No approved news JSON found in push diff; "
            f"before={before!r}, after={after!r}, "
            f"event_commits={len(event.get('commits', []))}"
        )
    return approved


def main():
    for relative_path in load_approved_items():
        item = json.loads(Path(relative_path).read_text(encoding="utf-8"))
        print(f"Publishing approved item: {relative_path}")
        publish(
            text=item.get("text", ""),
            image_url=item.get("image_url"),
            image_base64=item.get("image_base64"),
            image_svg_path=item.get("image_svg_path"),
            source_url=item.get("source_url"),
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Publication failed: {exc}", file=sys.stderr)
        raise
