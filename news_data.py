import re
from difflib import SequenceMatcher

import feedparser


# ==============================
# RSS 新闻源
# ==============================

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


# ==============================
# 输出数量
# ==============================

MAX_NEWS = 10


# ==============================
# 市场关键词
# ==============================

MARKET_KEYWORDS = [

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
    "jobs",
    "employment",
    "payroll",
    "gdp",

    # 市场
    "stock",
    "stocks",
    "market",
    "nasdaq",
    "s&p",
    "dow",
    "shares",
    "earnings",

    # 龙头科技
    "nvidia",
    "apple",
    "microsoft",
    "amazon",
    "google",
    "alphabet",
    "meta",
    "tesla",
    "tsmc",
    "asml",

    # AI/半导体
    "ai",
    "artificial intelligence",
    "ai model",
    "semiconductor",
    "chip",
    "chips",
    "memory",
    "optical",
    "data center",

    # 中国
    "china",
    "tariff",
    "trade",
    "sanction",

    # 商品
    "oil",
    "crude",
    "gold",
    "dollar",
    "treasury",
    "bond",
    "yield",

    # 地缘
    "war",
    "conflict",
    "geopolitical",
]


# ==============================
# 文本清洗
# ==============================

def clean_text(text):

    text = text.lower()

    text = re.sub(
        r"https?://\S+",
        "",
        text
    )

    text = re.sub(
        r"[^a-z0-9\u4e00-\u9fff\s]",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text



# ==============================
# 市场相关判断
# ==============================

def is_market_relevant(title, summary=""):

    text = clean_text(
        f"{title} {summary}"
    )

    return any(
        keyword in text
        for keyword in MARKET_KEYWORDS
    )



# ==============================
# 标题相似去重
# ==============================

def is_duplicate(
        title,
        existing_titles,
        threshold=0.82
):

    title = clean_text(title)

    for existing in existing_titles:

        similarity = SequenceMatcher(
            None,
            title,
            existing
        ).ratio()

        if similarity >= threshold:
            return True

    return False



# ==============================
# 事件关键词提取
# ==============================

def event_key(title):

    text = clean_text(title)


    companies = [

        "nvidia",
        "apple",
        "microsoft",
        "amazon",
        "google",
        "alphabet",
        "meta",
        "tesla",
        "tsmc",
        "asml",
        "crowdstrike",
        "salesforce",
        "z ai",
    ]


    events = [

        "earnings",
        "quarter",
        "results",
        "forecast",
        "guidance",
        "ai model",
        "launch",
        "release",
        "shares",
        "stock",
    ]


    result = []


    for item in companies:

        if item in text:
            result.append(item)


    for item in events:

        if item in text:
            result.append(item)


    if result:

        return "_".join(result)


    return text[:40]



# ==============================
# 新闻评分
# ==============================

def calculate_score(article):

    text = clean_text(
        article["title"]
    )


    score = 0


    # 宏观最高权重

    macro = [

        "fed",
        "fomc",
        "inflation",
        "cpi",
        "interest rate",
        "yield",
        "treasury",
        "dollar",
    ]


    for word in macro:

        if word in text:
            score += 3



    # 龙头科技

    big_tech = [

        "nvidia",
        "apple",
        "microsoft",
        "amazon",
        "google",
        "meta",
        "tesla",
        "tsmc",
        "asml",

    ]


    for word in big_tech:

        if word in text:
            score += 2



    # 普通事件

    events = [

        "earnings",
        "forecast",
        "guidance",
        "ai model",
        "launch",

    ]


    for word in events:

        if word in text:
            score += 1


    return score



# ==============================
# 新闻分类
# ==============================

def classify_news(title):

    text = clean_text(title)


    if "ai" in text or "nvidia" in text:

        return "AI/科技"


    if (
        "chip" in text
        or "semiconductor" in text
        or "tsmc" in text
    ):

        return "半导体"


    if (
        "fed" in text
        or "inflation" in text
        or "rate" in text
    ):

        return "宏观"


    if (
        "oil" in text
        or "gold" in text
    ):

        return "商品"


    if (
        "war" in text
        or "conflict" in text
    ):

        return "地缘政治"


    return "公司事件"



# ==============================
# 主函数
# ==============================

def get_news_data():

    articles = []

    event_pool = set()


    for source, url in NEWS_FEEDS.items():

        try:

            feed = feedparser.parse(url)


            for item in feed.entries[:20]:


                title = getattr(
                    item,
                    "title",
                    ""
                ).strip()


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



                if not title or not link:

                    continue



                if not is_market_relevant(
                    title,
                    summary
                ):

                    continue



                # 事件级去重

                key = event_key(title)


                if key in event_pool:

                    continue


                event_pool.add(key)



                article = {

                    "title": title,

                    "summary": summary,

                    "source": source,

                    "published": published,

                    "url": link,

                    "category":
                        classify_news(title),

                }


                article["score"] = calculate_score(
                    article
                )


                articles.append(article)



        except Exception as e:

            print(
                f"{source} 获取失败: {e}"
            )



    # 分数排序

    articles.sort(
        key=lambda x:
        x["score"],
        reverse=True
    )


    return articles[:MAX_NEWS]



# ==============================
# 测试
# ==============================

if __name__ == "__main__":


    news = get_news_data()


    print(
        "\n========== TOP10 重大市场事件 ==========\n"
    )


    if not news:

        print(
            "未发现重要市场新闻"
        )


    else:


        for i, article in enumerate(
            news,
            1
        ):


            print(
                f"{i}. [{article['category']}] "
                f"{article['title']}"
            )


            print(
                f"   评分：{article['score']}"
            )

            print(
                f"   来源：{article['source']}"
            )

            print(
                f"   时间：{article['published']}"
            )

            print(
                f"   原文：{article['url']}"
            )


            print()
