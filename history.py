"""過去レポートから時系列ダイジェストを組み立てるヘルパー。

各過去レポート（reports/YYYY-MM-DD.md）を解析し、記事ごとに
「優先度・総合点・投資スタンス・関連銘柄・タイトル」を1行へ圧縮して
時系列で並べる。生成モデルに「これまでの流れ」を渡すために使う。
"""

import os
import re
from datetime import datetime

import requests

DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")

# 見出し・各フィールドの抽出パターン
HEADING_RE = re.compile(r"^###\s+(.*)$")
PRIORITY_RE = re.compile(r"^-\s*\*\*【投資優先度】\*\*[:：]\s*(.+?)\s*$")
SCORE_RE = re.compile(r"^\s*-\s*\*\*総合点\*\*[:：]\s*([0-9]+)\s*/\s*30")
TICKERS_RE = re.compile(r"^-\s*\*\*関連する主な上場銘柄\*\*[:：]\s*(.+?)\s*$")
STANCE_RE = re.compile(r"^-\s*\*\*ポートフォリオ戦略と理由\*\*[:：]\s*(.*?)\s*$")

# 「銘柄名 (TICKER)」形式の括弧内からティッカーだけを取り出す。
# 「(未上場)」は日本語のみなので、この文字クラスには一致しない。
TICKER_IN_PARENS_RE = re.compile(r"\(([A-Za-z0-9.]{1,12})\)")

# タイトル先頭から取り除く優先度アイコン等
_LEADING_ICONS = "🔥👁️💤🔴⚪🟢🟡 \t"

MAX_TITLE_LEN = 50


def _clean_title(raw):
    title = raw.strip()
    # 先頭の優先度アイコンや装飾を除去
    while title and title[0] in _LEADING_ICONS:
        title = title[1:]
    title = title.strip()
    if len(title) > MAX_TITLE_LEN:
        title = title[:MAX_TITLE_LEN] + "…"
    return title


def _parse_report(text):
    """1レポート本文から記事ダイジェストのリストを返す。"""
    articles = []
    current = None

    def flush():
        if current and current.get("title"):
            articles.append(current)

    for line in text.splitlines():
        m = HEADING_RE.match(line)
        if m:
            flush()
            current = {"title": _clean_title(m.group(1))}
            continue
        if current is None:
            continue
        m = PRIORITY_RE.match(line)
        if m:
            current["priority"] = m.group(1)
            continue
        m = SCORE_RE.match(line)
        if m:
            current["score"] = m.group(1)
            continue
        m = TICKERS_RE.match(line)
        if m:
            current["tickers"] = m.group(1)
            continue
        m = STANCE_RE.match(line)
        if m and m.group(1):
            current["stance"] = m.group(1)
            continue
    flush()
    return articles


def _extract_tickers(tickers_field):
    """「Microsoft (MSFT), ソニーグループ (6758.T), (未上場)OpenAI」のような
    フィールドから、括弧内のティッカーだけを取り出す。"""
    return TICKER_IN_PARENS_RE.findall(tickers_field)


def _format_day(date_str, articles):
    lines = [f"## {date_str}"]
    if not articles:
        lines.append("- （分析対象記事なし）")
        return "\n".join(lines)
    for a in articles:
        priority = a.get("priority", "?")
        score = a.get("score", "?")
        stance = a.get("stance", "?")
        parts = [f"- [{priority} / {score}点 / {stance}] {a['title']}"]
        if a.get("tickers"):
            parts.append(f"（銘柄: {a['tickers']}）")
        lines.append("".join(parts))
    return "\n".join(lines)


def load_history_digest(today_str, days=7, reports_dir="reports"):
    """today_str より前の直近 days 日分のレポートを圧縮したダイジェスト文字列と、
    その期間に登場した銘柄ティッカーの集合を返す（digest_str, tickers_set）。

    対象レポートが無い場合は ("", set()) を返す。
    """
    if not os.path.isdir(reports_dir):
        return "", set()

    today = datetime.strptime(today_str, "%Y-%m-%d").date()
    dated = []
    for name in os.listdir(reports_dir):
        m = DATE_RE.match(name)
        if not m:
            continue
        d = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        if d < today:
            dated.append((d, name))

    dated.sort()
    recent = dated[-days:]
    if not recent:
        return "", set()

    blocks = []
    tickers = set()
    for d, name in recent:
        path = os.path.join(reports_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        articles = _parse_report(text)
        blocks.append(_format_day(d.strftime("%Y-%m-%d"), articles))
        for a in articles:
            if a.get("tickers"):
                tickers.update(_extract_tickers(a["tickers"]))

    return "\n\n".join(blocks), tickers


# --- 実際の株価動向（Yahoo Finance 公開チャートAPIを requests で直接叩く） ---
# 新規の依存パッケージ（yfinance等）は追加せず、既存の requests のみで実装する。

_YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _fetch_ticker_closes(ticker, timeout=10):
    """直近1ヶ月の日次終値のリストを返す。取得失敗時は None。"""
    url = _YAHOO_CHART_URL.format(ticker=ticker)
    try:
        resp = requests.get(
            url,
            headers=_YAHOO_HEADERS,
            params={"range": "1mo", "interval": "1d"},
            timeout=timeout,
        )
        resp.raise_for_status()
        result = resp.json()["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
    except Exception:
        return None

    closes = [c for c in closes if c is not None]
    if len(closes) < 2:
        return None
    return closes


def _pct_change(latest, past):
    if not past:
        return None
    return (latest - past) / past * 100


def _format_ticker_snapshot(ticker, closes):
    latest = closes[-1]
    parts = [f"${latest:,.2f}"]

    d1 = _pct_change(latest, closes[-2]) if len(closes) >= 2 else None
    if d1 is not None:
        parts.append(f"1日: {d1:+.1f}%")

    d5 = _pct_change(latest, closes[-6]) if len(closes) >= 6 else None
    if d5 is not None:
        parts.append(f"5日: {d5:+.1f}%")

    d1mo = _pct_change(latest, closes[0])
    if d1mo is not None:
        parts.append(f"1ヶ月: {d1mo:+.1f}%")

    return f"- {ticker}: 現在値 " + ", ".join(parts)


def load_price_snapshot(tickers):
    """指定ティッカー群の実際の価格動向スナップショットを文字列で返す。

    個々の銘柄の取得に失敗した場合はその銘柄だけを黙って省略する
    （verify_tickers.py と同様、生成をブロックしない方針）。
    全銘柄の取得に失敗、またはtickersが空の場合は空文字列を返す。
    """
    lines = []
    for ticker in sorted(set(tickers)):
        closes = _fetch_ticker_closes(ticker)
        if closes is None:
            continue
        lines.append(_format_ticker_snapshot(ticker, closes))
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    today = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    digest, tickers = load_history_digest(today)
    print(digest)
    print("\n--- tickers ---")
    print(sorted(tickers))
    print("\n--- price snapshot ---")
    print(load_price_snapshot(tickers))
