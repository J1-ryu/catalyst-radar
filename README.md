# Tech News Investor Analyst

TechCrunch / The Verge のRSSフィードを取得し、米国株・日本株への投資影響をVC/機関投資家の視点でスコアリング・分析するツールです。

## 必要環境

- Python 3.8 以上
- pip

## セットアップ（Linux）

### 1. Python と pip のインストール

**Ubuntu / Debian 系**
```bash
sudo apt update
sudo apt install -y python-is-python3 python3-pip
```

**Fedora / RHEL 系**
```bash
sudo dnf install -y python3 python3-pip
sudo ln -s /usr/bin/python3 /usr/local/bin/python
```

インストール確認:
```bash
python --version
pip --version
```

### 2. 依存パッケージのインストール

```bash
pip install feedparser
```

pip コマンドが使えない場合:
```bash
python -m pip install feedparser
```

### 3. 動作確認

```bash
python fetch_rss.py
```

JSON形式で記事一覧が出力されれば成功です。

## 環境変数 / Secrets

日次レポート生成（`generate_report.py`）と GitHub Actions での自動実行には、以下の環境変数を使用します。
ローカル実行時はシェルの環境変数として、GitHub Actions では Settings → Secrets and variables →
Actions → New repository secret から設定してください。

| 変数名 | 必須 | 用途 |
| --- | --- | --- |
| `GEMINI_API_KEY` | 必須 | レポート生成（Gemini API）に使用。 |
| `DISCORD_WEBHOOK_URL` | 任意 | 生成したレポートをDiscordに通知する場合に使用。 |
| `SEC_EDGAR_CONTACT` | 任意（推奨） | ティッカー検証（SEC EDGAR）のUser-Agentに含める連絡先。例: `"tech-news-analyst you@example.com"`。未設定時は検証機能自体は動くが、SEC側の利用ポリシー上、実際の連絡先を設定することが推奨される。 |
| `PORTFOLIO_CONFIG_PY` | 任意 | 下記「ポートフォリオ設定」参照。 |

## ポートフォリオ設定（任意）

`generate_report.py` は、自分の実際のポートフォリオ構成を踏まえて「新規に検討すべき投資アイデア」を
絞り込む機能を持っています。設定しなくても動作しますが（汎用的な機関投資家目線の分析のみになります）、
自分のポートフォリオに合わせたい場合は以下の手順で設定してください。

```bash
cp portfolio_config.example.py portfolio_config.py
```

`portfolio_config.py` を自分のポートフォリオに書き換えてください。このファイルは `.gitignore` 済みで、
リポジトリにはコミットされません。

設定項目はすべて任意で、書いた項目だけがプロンプトに反映されます。枠（バケット）の数・名称・比率、
および新規提案の条件は特定の構成を前提としておらず、自由に定義できます。

| 設定項目 | 用途 |
| --- | --- |
| `PORTFOLIO_OVERVIEW` | ポートフォリオ構成・投資方針の自由記述。枠で管理していない場合は方針だけでも可。 |
| `NEW_IDEA_LABEL` | 新規アイデアを提案してもらう枠のラベル。レポート末尾の「本日の〇〇」見出しに使われる（既定: `新規投資候補`）。 |
| `NEW_IDEA_CRITERIA` | 新規提案が満たすべき条件の自由記述。条件の数・粒度は任意。未設定なら汎用の既定条件が使われる。 |
| `CORE_HOLDING_TICKERS` | 長期保有で新規のトレード提案が不要なティッカー。該当記事は🟡Hold（既存保有のため新規提案不要）として扱われる。 |
| `EXISTING_IDEA_TICKERS` | すでに新規アイデア枠で保有中のティッカー。セクター重複チェックと二重提案の防止に使われる。 |

旧名の `USER_PORTFOLIO` / `SPECULATIVE_HOLDING_TICKERS` もそのまま読み込まれるため、既存の設定を
書き換えずに使い続けられます。

GitHub Actions で日次実行させる場合は、リポジトリの Secrets に `PORTFOLIO_CONFIG_PY` として
`portfolio_config.py` の内容をそのまま登録してください。未設定の場合はポートフォリオを考慮しない
汎用モードで実行されます。

## 使い方

Claude Code のプロジェクトルートで `/tech-news-investor-analyst` スキルを呼び出してください。

スキルが自動的に `fetch_rss.py` を実行し、分析結果を `reports/YYYY-MM-DD.md` に書き出します。

## ファイル構成

```
tech-news-analyst/
├── fetch_rss.py        # RSSフィード取得スクリプト
├── reports/            # 分析レポート出力先
└── .claude/
    └── skills/
        └── tech-news-investor-analyst/
            └── SKILL.md
```
