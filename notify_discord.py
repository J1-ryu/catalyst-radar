import os
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

DISCORD_HARD_LIMIT = 2000

ARTICLE_SEPARATOR = re.compile(r"\n-{3,}\n")
TITLE_PATTERN = re.compile(r"^(#\s.*?)\n\n(.*)$", re.DOTALL)


def split_into_messages(text):
    """タイトル行と記事（### 🔴 ...セクション）を1メッセージずつに分割する。"""
    segments = [seg.strip() for seg in ARTICLE_SEPARATOR.split(text.strip())]

    messages = []
    if segments:
        title_match = TITLE_PATTERN.match(segments[0])
        if title_match:
            messages.append(title_match.group(1).strip())
            first_article = title_match.group(2).strip()
            segments[0] = first_article

    for seg in segments:
        if seg:
            messages.append(seg)

    # Discordの1メッセージ2000文字制限を超える記事のみ、安全策として行単位で分割する
    final_messages = []
    for msg in messages:
        final_messages.extend(_split_if_too_long(msg))
    return final_messages


def _split_if_too_long(msg, limit=DISCORD_HARD_LIMIT - 100):
    if len(msg) <= limit:
        return [msg]
    chunks = []
    current = ""
    for line in msg.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = line
    if current:
        chunks.append(current)
    return chunks


def main():
    webhook_url = os.environ["DISCORD_WEBHOOK_URL"]
    if len(sys.argv) > 1:
        report_path = sys.argv[1]
    else:
        date_str = os.environ.get("TARGET_DATE", "").strip()
        if not date_str:
            date_str = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
        report_path = f"reports/{date_str}.md"

    with open(report_path, "r", encoding="utf-8") as f:
        text = f.read()

    messages = split_into_messages(text)
    for i, msg in enumerate(messages):
        resp = requests.post(webhook_url, json={"content": msg})
        resp.raise_for_status()
        if i < len(messages) - 1:
            time.sleep(1)


if __name__ == "__main__":
    main()
