"""RSSフィードを取得し、日付ごとの生データとして保存する（分析は行わない）。

このスクリプトは意図的に分析ステップ(generate_report.py)と分離している。
RSSフィードは最新N件しか保持しないため、分析ステップが失敗しても
このスクリプトが保存した生データが残っていれば、後日でも当日分の
ニュース内容を正しく再分析できる。

対象日付は環境変数 TARGET_DATE (YYYY-MM-DD) で指定でき、未指定または
空文字の場合は実行時点のJST日付を使う。同日分の生データが既に存在する
場合は再取得・上書きしない（冪等）。
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from archive import load_articles, save_articles
from fetch_rss import fetch_articles


def resolve_date_str():
    target = os.environ.get("TARGET_DATE", "").strip()
    if target:
        return target
    return datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")


def main():
    date_str = resolve_date_str()

    if load_articles(date_str) is not None:
        print(f"{date_str} 分の生データは既に存在するため、取得をスキップしました。")
        return

    articles = fetch_articles()
    path = save_articles(date_str, articles)
    print(f"{date_str} 分の記事 {len(articles)} 件を {path} に保存しました。")


if __name__ == "__main__":
    main()
