import re
from difflib import SequenceMatcher

import feedparser


# 免费公开 RSS 新闻源
NEWS_FEEDS = {
    "CNBC Markets":
        "https://www.cnbc.com/id/15839135/device/rss/rss.html",

    "CNBC Finance":
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",

    "Federal Reserve":
        "https://www.federalreserve.gov/feeds/press_all.xml",

    "Yahoo Finance":
        "https://finance.yahoo.com/news/rssindex",
}


# 与金融市场高度相关的关键词
MARKET_KEYWORDS = [
    "fed",
    "federal reserve",
    "interest rate",
    "rate cut",
    "rate hike",
    "inflation",
    "cpi",
    "ppi",
    "jobs",
    "employment",
    "payroll",
    "gdp",

    "stock",
    "stocks",
    "market",
    "nasdaq",
    "s&p",
    "dow",
    "shares",
    "earnings",

    "nvidia",
    "apple",
    "microsoft",
    "amazon",
    "google",
    "alphabet",
    "meta",
    "tesla",

    "ai",
    "artificial intelligence",
    "semiconductor",
    "chip",
    "chips",
    "memory",
    "optical",
    "data center",

    "china",
    "tariff",
    "trade",
    "sanction",

    "oil",
    "crude",
    "gold",
    "dollar",
    "treasury",
    "bond",
    "yield",

    "war",
    "conflict",
    "geopolitical",
]


def clean_text(text):
    """清理标题，方便去重和关键词匹配。"""

    text = text.lower()

    text = re.sub(r"https?://\S+", "", text)

    text = re.sub(r"[^a-z0-9\u4e00-\u9fff\s]", " ", text)

    text = re.sub(r"\s+", " ", text).strip()

    return text


def is_market_relevant(title, summary=""):
    """判断新闻是否与金融市场明显相关。"""

    text = clean_text(f"{title} {summary}")

    for keyword in MARKET_KEYWORDS:
        if keyword in text:
            return True

    return False


def is_duplicate(title, existing_titles, threshold=0.82):
    """使用标题相似度进行去重。"""

    cleaned_title = clean_text(title)

    for existing in existing_titles:

        similarity = SequenceMatcher(
            None,
            cleaned_title,
            existing
        ).ratio()

        if similarity >= threshold:
            return True

    return False


def get_news_data():

    articles = []

    for source, url in NEWS_FEEDS.items():

        try:

            feed = feedparser.parse(url)

            for item in feed.entries[:15]:

                title = getattr(item, "title", "").strip()

                summary = getattr(
                    item,
                    "summary",
                    ""
                ).strip()

                link = getattr(
                    item,
                    "link",
                    ""
                ).strip()

                published = getattr(
                    item,
                    "published",
                    ""
                ).strip()

                # 没有标题或链接，不进入系统
                if not title or not link:
                    continue

                # 只保留市场相关新闻
                if not is_market_relevant(
                    title,
                    summary
                ):
                    continue

                # 去重
                existing_titles = [
                    clean_text(article["title"])
                    for article in articles
                ]

                if is_duplicate(
                    title,
                    existing_titles
                ):
                    continue

                articles.append({
                    "title": title,
                    "summary": summary,
                    "source": source,
                    "published": published,
                    "url": link,
                })

        except Exception as e:

            print(
                f"{source} 获取失败: {e}"
            )

    return articles


if __name__ == "__main__":

    news = get_news_data()

    print("\n========== 重要市场新闻 ==========\n")

    if not news:

        print(
            "过去24小时未发现符合筛选条件的重要市场新闻。"
        )

    else:

        for index, article in enumerate(
            news,
            start=1
        ):

            print(
                f"{index}. "
                f"{article['title']}"
            )

            print(
                f"   来源："
                f"{article['source']}"
            )

            print(
                f"   时间："
                f"{article['published']}"
            )

            print(
                f"   原文："
                f"{article['url']}"
            )

            print()
