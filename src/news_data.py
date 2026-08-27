import re
from difflib import SequenceMatcher

import feedparser


# =====================================
# RSS 新闻源
# =====================================

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


# 输出数量

MAX_NEWS = 10



# =====================================
# 公司实体库
# =====================================

COMPANY_ENTITIES = {

    "Nvidia": [
        "nvidia",
        "nvda"
    ],

    "CrowdStrike": [
        "crowdstrike",
        "crwd"
    ],

    "Salesforce": [
        "salesforce",
        "crm"
    ],

    "Apple": [
        "apple",
        "aapl"
    ],

    "Microsoft": [
        "microsoft",
        "msft"
    ],

    "Tesla": [
        "tesla",
        "tsla"
    ],

    "Google": [
        "google",
        "alphabet"
    ],

    "Amazon": [
        "amazon",
        "amzn"
    ],

    "TSMC": [
        "tsmc",
        "taiwan semiconductor"
    ],

    "ASML": [
        "asml"
    ],

    "Okta": [
        "okta"
    ]

}



# =====================================
# 市场关键词
# =====================================

MARKET_KEYWORDS = [

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

    "stock",
    "stocks",
    "shares",
    "market",

    "earnings",
    "quarter",
    "forecast",

    "ai",
    "artificial intelligence",

    "semiconductor",
    "chip",
    "gpu",

    "nvidia",
    "apple",
    "microsoft",
    "amazon",
    "google",
    "meta",
    "tesla",

    "crowdstrike",
    "okta",

    "china",
    "trade",
    "tariff",

    "oil",
    "gold",
    "dollar",
    "treasury",
    "bond",
    "yield",

    "war",
    "conflict"

]



# =====================================
# 文本清理
# =====================================

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

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text



# =====================================
# 新闻相关判断
# =====================================

def is_market_relevant(title, summary=""):

    text = clean_text(
        title + " " + summary
    )

    for keyword in MARKET_KEYWORDS:

        if keyword in text:

            return True


    return False



# =====================================
# 公司识别
# =====================================

def detect_company(title):

    text = clean_text(title)


    for company, keywords in COMPANY_ENTITIES.items():

        for word in keywords:

            if word in text:

                return company


    return "Other"



# =====================================
# 事件类型
# =====================================

def detect_event(title):

    text = clean_text(title)


    if any(
        x in text
        for x in [
            "earnings",
            "quarter",
            "results"
        ]
    ):

        return "earnings"


    if any(
        x in text
        for x in [
            "ai model",
            "artificial intelligence",
            "gpu"
        ]
    ):

        return "ai"



    if any(
        x in text
        for x in [
            "fed",
            "inflation",
            "interest rate",
            "cpi"
        ]
    ):

        return "macro"


    return "market"



# =====================================
# 事件ID
# =====================================

def generate_event_id(title):

    company = detect_company(title)

    event = detect_event(title)


    return f"{company}_{event}"



# =====================================
# 分类
# =====================================

def classify_news(title):

    text = clean_text(title)


    if (
        "nvidia" in text
        or "ai" in text
        or "gpu" in text
    ):

        return "AI/科技"


    if (
        "chip" in text
        or "semiconductor" in text
        or "tsmc" in text
    ):

        return "半导体"


    if (
        "crowdstrike" in text
        or "okta" in text
    ):

        return "网络安全"


    if (
        "fed" in text
        or "inflation" in text
        or "rate" in text
    ):

        return "宏观"


    return "公司事件"



# =====================================
# 新闻评分
# =====================================

def calculate_score(article):

    text = clean_text(
        article["title"]
    )


    score = 0


    # 宏观

    for word in [

        "fed",
        "fomc",
        "inflation",
        "cpi",
        "interest rate",
        "yield"

    ]:

        if word in text:

            score += 10



    # AI核心

    for word in [

        "nvidia",
        "tsmc",
        "asml",
        "gpu",
        "ai"

    ]:

        if word in text:

            score += 8



    # 科技巨头

    for word in [

        "apple",
        "microsoft",
        "google",
        "amazon",
        "tesla"

    ]:

        if word in text:

            score += 6



    # 网络安全

    for word in [

        "crowdstrike",
        "okta"

    ]:

        if word in text:

            score += 5



    # 普通财报

    if "earnings" in text:

        score += 1



    return score



# =====================================
# 获取新闻
# =====================================

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



                event_id = generate_event_id(
                    title
                )


                if event_id in event_pool:

                    continue


                event_pool.add(event_id)



                article = {

                    "title": title,

                    "summary": summary,

                    "source": source,

                    "published": published,

                    "url": link,

                    "category":
                        classify_news(title)

                }



                article["score"] = calculate_score(
                    article
                )


                articles.append(article)



        except Exception as e:

            print(
                source,
                "获取失败:",
                e
            )



    # 高分优先

    articles.sort(
        key=lambda x:
        x["score"],
        reverse=True
    )


    return articles[:MAX_NEWS]



# =====================================
# 测试
# =====================================

if __name__ == "__main__":


    news = get_news_data()


    print(
        "\n========== TOP10重大市场事件 ==========\n"
    )


    for i, article in enumerate(
        news,
        1
    ):

        print(
            f"{i}.【{article['category']}】"
        )

        print(
            article["title"]
        )

        print(
            "评分:",
            article["score"]
        )

        print(
            "来源:",
            article["source"]
        )

        print(
            "时间:",
            article["published"]
        )

        print(
            "链接:",
            article["url"]
        )

        print()
