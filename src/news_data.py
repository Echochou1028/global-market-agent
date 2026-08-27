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


CATEGORIES = {

    "宏观政策": [

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
        "dollar",

    ],


    "AI/半导体": [

        "nvidia",
        "amd",
        "intel",
        "tsmc",
        "asml",
        "broadcom",
        "qualcomm",
        "semiconductor",
        "chip",
        "gpu",
        "memory",
        "hbm",
        "artificial intelligence",
        "ai model",
        "data center",

    ],


    "全球股市": [

        "stock",
        "shares",
        "earnings",
        "quarter",
        "revenue",
        "profit",
        "forecast",
        "guidance",
        "apple",
        "microsoft",
        "amazon",
        "google",
        "meta",
        "tesla",
        "alibaba",
        "tencent",

    ],


    "能源商品": [

        "oil",
        "crude",
        "gold",
        "silver",
        "copper",
        "natural gas",
        "opec",
        "commodity",

    ],


    "地缘风险": [

        "china",
        "taiwan",
        "tariff",
        "trade",
        "sanction",
        "war",
        "conflict",
        "geopolitical",
        "supply chain",

    ]

}



HIGH_VALUE = [

    "fed",
    "fomc",
    "rate",
    "inflation",
    "nvidia",
    "apple",
    "microsoft",
    "tsmc",
    "asml",
    "oil",
    "gold",
    "tariff",
    "sanction",

]



def clean(text):

    text = text.lower()

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



def get_time(item):

    try:

        if hasattr(item, "published_parsed"):

            return datetime(
                *item.published_parsed[:6],
                tzinfo=timezone.utc
            )

    except:

        pass

    return None



def recent(item):

    t = get_time(item)

    if not t:

        return False


    return t >= (
        datetime.now(timezone.utc)
        -
        timedelta(hours=36)
    )



def category_score(title):

    text = clean(title)

    result = {}


    for cat, words in CATEGORIES.items():

        score = 0

        for w in words:

            if w in text:

                score += 2


        result[cat] = score


    return result



def importance(title):

    text = clean(title)

    score = 0


    for word in HIGH_VALUE:

        if word in text:

            score += 3


    return score



def duplicate(title, titles):

    for old in titles:

        if SequenceMatcher(
            None,
            clean(title),
            clean(old)
        ).ratio() > 0.82:

            return True

    return False



def collect_news():


    all_news = []


    for source, url in NEWS_FEEDS.items():

        feed = feedparser.parse(url)


        for item in feed.entries[:30]:


            title = getattr(
                item,
                "title",
                ""
            )


            link = getattr(
                item,
                "link",
                ""
            )


            if not title or not link:

                continue


            if not recent(item):

                continue



            scores = category_score(title)


            category = max(
                scores,
                key=scores.get
            )


            if scores[category] == 0:

                continue



            all_news.append({

                "title": title,

                "category": category,

                "source": source,

                "time":
                    str(get_time(item)),

                "url": link,

                "score":
                    importance(title)
                    +
                    scores[category],

            })


    return all_news



def classify_news(news):


    result = {}


    for c in CATEGORIES:

        result[c] = []



    used = []


    for item in sorted(
        news,
        key=lambda x:x["score"],
        reverse=True
    ):


        if duplicate(
            item["title"],
            used
        ):

            continue


        if len(
            result[item["category"]]
        ) >= 10:

            continue


        result[item["category"]].append(
            item
        )

        used.append(
            item["title"]
        )


    return result



if __name__ == "__main__":


    news = classify_news(
        collect_news()
    )


    print(
        "\n========== 重大市场事件 ==========\n"
    )


    for category, items in news.items():


        print(
            f"\n【{category}】\n"
        )


        if not items:

            print(
                "过去36小时未发现重要事件。"
            )

            continue



        for i,item in enumerate(
            items,
            1
        ):


            print(
                f"{i}. {item['title']}"
            )

            print(
                f"评分: {item['score']}"
            )

            print(
                f"来源: {item['source']}"
            )

            print(
                f"时间: {item['time']}"
            )

            print(
                f"链接: {item['url']}\n"
            )
