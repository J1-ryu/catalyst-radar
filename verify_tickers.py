"""SEC EDGAR の公式ティッカー台帳を用いたレポートのティッカー検証。

生成モデルの学習カットオフ起因で発生する2種類の誤りを、権威ある構造化データ
（SEC EDGAR company_tickers.json）で機械的に検出する:

1. 表記の古い/誤ったティッカー（例: ソニーを旧「SNE」と記載。正しくは「SONY」）
2. 実際は米国上場済みの企業を「未上場」と誤記（例: SpaceX が上場後も未上場扱い）

台帳は SEC が随時更新するため、新規IPOや改称にも追従できる（手動のリスト保守が不要）。
検証はあくまで補助であり、レポート生成自体はブロックしない（警告を出力するのみ）。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

# SEC は User-Agent に連絡先を含めることを要求している
# https://www.sec.gov/os/webmaster-faq#developers
# 実行者自身の連絡先を SEC_EDGAR_CONTACT 環境変数で指定すること（例: "tech-news-analyst you@example.com"）。
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
USER_AGENT = os.environ.get(
    "SEC_EDGAR_CONTACT", "tech-news-analyst (set SEC_EDGAR_CONTACT env var with your contact info)"
)

CACHE_PATH = Path(".cache/edgar_company_tickers.json")
CACHE_TTL_SECONDS = 7 * 24 * 60 * 60  # 7日

# 銘柄行から抽出した際に、ティッカーではないと分かっている大文字トークン
STOPLIST = {"ADR", "IPO", "US", "EU", "UK", "AI", "CEO", "CFO", "GCP", "AWS", "OS"}

# 米国上場済みか判定したい、私企業/上場が混同されやすい著名企業。
# 値は EDGAR の会社名（title）に含まれる検索用の部分文字列（小文字）。
# EDGAR に該当会社が存在すれば「上場済み」と判定する（上場すれば SEC に登録されるため）。
# 新たに追加したい企業があればここに1行足すだけでよい。
LISTING_ALIASES = {
    "SpaceX": "space exploration technologies",
    "OpenAI": "openai",
    "Stripe": "stripe",
    "Databricks": "databricks",
    "Anthropic": "anthropic",
    "Canva": "canva",
    "Discord": "discord",
}

UNLISTED_MARKERS = ("未上場", "非上場", "上場していない", "上場企業ではない")


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def load_edgar_index(force_refresh: bool = False) -> dict | None:
    """EDGAR のティッカー台帳を取得（ローカルに7日キャッシュ）。

    取得に失敗し、かつ有効なキャッシュも無い場合は None を返す（検証をスキップ）。
    戻り値: {"by_ticker": {TICKER: title}, "names": [(normalized_title, ticker), ...]}
    """
    raw = None
    if not force_refresh and CACHE_PATH.exists():
        age = time.time() - CACHE_PATH.stat().st_mtime
        if age < CACHE_TTL_SECONDS:
            try:
                raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = None

    if raw is None:
        try:
            resp = requests.get(
                SEC_TICKERS_URL,
                headers={"User-Agent": USER_AGENT},
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json()
            CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CACHE_PATH.write_text(
                json.dumps(raw, ensure_ascii=False), encoding="utf-8"
            )
        except (requests.RequestException, ValueError):
            # ネットワーク不通などで取得できず、期限切れキャッシュも無い場合
            if CACHE_PATH.exists():
                try:
                    raw = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    return None
            else:
                return None

    by_ticker: dict[str, str] = {}
    names: list[tuple[str, str]] = []
    for entry in raw.values():
        ticker = str(entry.get("ticker", "")).upper()
        title = str(entry.get("title", ""))
        if not ticker:
            continue
        by_ticker[ticker] = title
        names.append((_normalize(title), ticker))
    return {"by_ticker": by_ticker, "names": names}


def extract_cited_tickers(report_text: str) -> set[str]:
    """「関連する主な上場銘柄」行から米国株ティッカー候補を抽出する。

    日本株の証券コード（数字）や、全大文字で書かれた社名（複数語）は除外する。
    """
    tickers: set[str] = set()
    for line in report_text.splitlines():
        if "関連する主な上場銘柄" not in line:
            continue
        content = line.split(":", 1)[-1] if ":" in line else line
        for seg in re.split(r"[,、/]", content):
            seg = seg.strip()
            if not seg:
                continue
            # 括弧内はティッカーが入っていることが多い: "GAMESTOP (GME)"
            paren_bodies = re.findall(r"[（(]([^）)]*)[）)]", seg)
            for body in paren_bodies:
                tickers.update(re.findall(r"\b[A-Z]{1,5}\b", body))
            # 括弧の前が単独の大文字トークンならティッカー: "SONY (...)"
            head = re.sub(r"[（(].*", "", seg).strip()
            if re.fullmatch(r"[A-Z]{1,5}", head):
                tickers.add(head)
    return {t for t in tickers if t not in STOPLIST}


def _resolve_alias_ticker(search_substr: str, index: dict) -> str | None:
    for normalized_title, ticker in index["names"]:
        if search_substr in normalized_title:
            return ticker
    return None


def verify_report(report_text: str, index: dict) -> dict:
    """レポートを検証し、検出事項を返す。

    戻り値:
      {
        "unknown_tickers": [ティッカー...],          # EDGARに存在しない（要確認）
        "listing_mislabels": [(社名, ティッカー)...], # 上場済みだが未上場扱い
        "confirmed": [(ティッカー, 正式社名)...],     # EDGARで確認できたもの
      }
    """
    by_ticker = index["by_ticker"]

    unknown: list[str] = []
    confirmed: list[tuple[str, str]] = []
    for ticker in sorted(extract_cited_tickers(report_text)):
        if ticker in by_ticker:
            confirmed.append((ticker, by_ticker[ticker]))
        else:
            unknown.append(ticker)

    # 著名企業について、記事ブロック単位で2種類の誤りを検出する:
    #  - listing_mislabels: 上場済みなのに「未上場」と明記している
    #  - missing_parent:    記事の主題である上場企業のティッカーが関連銘柄行に無い
    #                       （例: SpaceXAI の記事で上場親会社 SPCX が抜けている）
    blocks = re.split(r"(?m)^---\s*$", report_text)
    mislabels: list[tuple[str, str]] = []
    missing: list[tuple[str, str]] = []
    seen_mislabel: set[str] = set()
    seen_missing: set[str] = set()
    for alias, search_substr in LISTING_ALIASES.items():
        ticker = _resolve_alias_ticker(search_substr, index)
        if not ticker:
            continue  # EDGARに無い＝まだ未上場。誤りではない
        for block in blocks:
            if alias not in block:
                continue
            if any(m in block for m in UNLISTED_MARKERS):
                if alias not in seen_mislabel:
                    mislabels.append((alias, ticker))
                    seen_mislabel.add(alias)
            elif ticker not in extract_cited_tickers(block):
                if alias not in seen_missing:
                    missing.append((alias, ticker))
                    seen_missing.add(alias)

    return {
        "unknown_tickers": unknown,
        "listing_mislabels": mislabels,
        "missing_parent": missing,
        "confirmed": confirmed,
    }


def format_findings(findings: dict) -> str:
    lines: list[str] = []
    if findings["unknown_tickers"]:
        lines.append(
            "⚠️ EDGARに存在しないティッカー（表記誤り/古い表記、または米国外上場の可能性）: "
            + ", ".join(findings["unknown_tickers"])
        )
    for alias, ticker in findings["listing_mislabels"]:
        lines.append(
            f"⚠️ {alias} は米国上場済み（EDGAR: {ticker}）だが、"
            "レポートで未上場として扱われている可能性があります"
        )
    for alias, ticker in findings["missing_parent"]:
        lines.append(
            f"⚠️ {alias} は米国上場企業（EDGAR: {ticker}）だが、"
            f"その記事の関連銘柄に {ticker} が含まれていません"
            "（上場親会社の取りこぼしの可能性）"
        )
    if not lines:
        lines.append(
            f"✅ ティッカー検証OK（EDGARで{len(findings['confirmed'])}件確認、問題なし）"
        )
    return "\n".join(lines)


def verify_report_text(report_text: str) -> bool:
    """レポート文字列を検証し結果を標準出力へ。問題があれば False を返す。"""
    index = load_edgar_index()
    if index is None:
        print("ℹ️ EDGAR台帳を取得できずティッカー検証をスキップしました")
        return True
    findings = verify_report(report_text, index)
    print(format_findings(findings))
    return not (
        findings["unknown_tickers"]
        or findings["listing_mislabels"]
        or findings["missing_parent"]
    )


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python verify_tickers.py <report.md>", file=sys.stderr)
        return 2
    report_text = Path(sys.argv[1]).read_text(encoding="utf-8")
    ok = verify_report_text(report_text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
