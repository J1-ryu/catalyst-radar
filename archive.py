"""RSS取得結果を日付ごとに生データとして保存/読込するヘルパー。

取得(fetch)と分析(Gemini呼び出し)を分離するために使う。RSSフィードは
最新N件しか保持しないため、分析ステップだけが失敗した場合でも、この
生データが残っていれば当日分のニュース内容を失わずに分析を再実行できる。
"""

import json
import os
import re

RAW_DIR = "data/raw"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _raw_path(date_str):
    if not _DATE_RE.match(date_str):
        raise ValueError(f"date_str must be YYYY-MM-DD, got: {date_str!r}")
    return os.path.join(RAW_DIR, f"{date_str}.json")


def save_articles(date_str, articles):
    """指定日の取得結果を保存する。既に存在する場合は上書きしない。"""
    path = _raw_path(date_str)
    if os.path.exists(path):
        return path
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    return path


def load_articles(date_str):
    """指定日の取得結果を読み込む。無ければ None を返す。"""
    path = _raw_path(date_str)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
