import feedparser
import json
import sys

RSS_FEEDS = [
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("The Verge", "https://www.theverge.com/rss/index.xml"),
]

MAX_ARTICLES_PER_FEED = 10


def fetch_articles():
    articles = []
    for source_name, url in RSS_FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
            articles.append({
                "source": source_name,
                "title": entry.get("title", ""),
                "summary": entry.get("summary", entry.get("description", "")),
                "url": entry.get("link", ""),
                "published": entry.get("published", ""),
            })
    return articles


if __name__ == "__main__":
    articles = fetch_articles()
    json.dump(articles, sys.stdout, ensure_ascii=False, indent=2)
