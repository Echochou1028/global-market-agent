import re
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

import feedparser


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


# 市场影响关键词
IMPACT_KEYWORDS = [

    # 宏观
    "fed",
    "federal reserve",
    "fomc",
    "interest rate",
    "rate cut",
    "rate hike",
    "inflation",
    "cpi",
    "ppi",
    "gdp",
    "jobs",
    "payroll",
    "treasury",
    "yield",

    # 市场
    "stock",
    "stocks",
    "market",
    "wall street",
    "nasdaq",
    "s&p",
    "dow",

    # 财报
    "earnings",
    "quarter",
    "forecast",
    "guidance",
    "revenue",
    "profit",
    "loss",

    # AI科技
    "ai",
    "artificial intelligence",
    "semiconductor",
    "chip",
    "memory",
    "data center",

    # 地缘
    "china",
    "tariff",
    "trade",
    "sanction",
    "war",
    "conflict",
    "geopolitical",

    # 商品
    "oil",
    "crude",
    "gold",
    "dollar",
]


# 重点公司
IMPORTANT_COMPANIES = [

    "nvidia",
    "apple",
    "microsoft",
    "amazon",
    "google",
    "alphabet",
    "meta",
    "tesla",
    "broadcom",
    "amd",
    "intel",
    "tsmc",
    "asml",
    "qualcomm",
    "oracle",
    "salesforce",
    "crowdstrike",
    "alibaba",
    "tencent",

]


def clean_text(text):

    text = text.lower()

    text = re.sub(
        r"https?://\S+",
        "",
        text
    )

    text = re.sub(
        r"[^a-z0-9\s]",
        " ",
        text
    )

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def parse_time(entry):

    try:

        if hasattr(entry, "published_parsed"):

            dt = datetime(
                *entry.published_parsed[:6],
                tzinfo=timezone.utc
            )

            return dt

    except:

        pass


    return None



def is_recent(entry):

    published = parse_time(entry)

    if not published:

        return True


    now = datetime.now(timezone.utc)

    limit = now - timedelta(hours=36)


    return published >= limit



def is_market_related(title, summary):

    text = clean_text(
        title + " " + summary
    )


    score = 0


    for word in IMPACT_KEYWORDS:

        if word in text:

            score += 1



    for company in IMPORTANT_COMPANIES:

        if company in text:

            score += 2



    return score >= 2



def duplicate(title, titles):

    title = clean_text(title)


    for old in titles:

        ratio = SequenceMatcher(
            None,
            title,
            old
        ).ratio()


        if ratio > 0.82:

            return True


    return False



def get_news_data():

    news = []


    for source, url in NEWS_FEEDS.items():

        try:

            feed = feedparser.parse(url)


            for item in feed.entries[:20]:

                title = getattr(
                    item,
                    "title",
                    ""
                )


                summary = getattr(
                    item,
                    "summary",
                    ""
                )


                link = getattr(
                    item,
                    "link",
                    ""
                )


                if not title or not link:

                    continue


                if not is_recent(item):

                    continue


                if not is_market_related(
                    title,
                    summary
                ):

                    continue


                old_titles = [
                    clean_text(x["title"])
                    for x in news
                ]


                if duplicate(
                    title,
                    old_titles
                ):

                    continue


                news.append({

                    "title": title,

                    "source": source,

                    "time":
                    str(
                        parse_time(item)
                    ),

                    "url": link,

                })


        except Exception as e:

            print(
                source,
                "error:",
                e
            )


    # 按数量限制
    return news[:10]



if __name__ == "__main__":


    news = get_news_data()


    print(
        "\n========== 重大市场事件 ==========\n"
    )


    if not news:

        print(
            "过去36小时未发现影响市场的重要事件。"
        )


    else:


        for i, item in enumerate(
            news,
            1
        ):

            print(
                f"{i}. {item['title']}"
            )

            print(
                f"来源：{item['source']}"
            )

            print(
                f"时间：{item['time']}"
            )

            print(
                f"原文：{item['url']}"
            )

            print()
