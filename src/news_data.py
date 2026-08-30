import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher

import feedparser


# ============================================================
# 第三部分：全球重大市场事件与政策
# ============================================================

MAX_NEWS = 10

# 新闻时间窗口
# 08:15 日报运行时，覆盖上一报告周期至当前生成时间
NEWS_WINDOW_HOURS = 36


# ============================================================
# RSS 新闻源
# ============================================================

NEWS_FEEDS = {
    "CNBC Markets":
        "https://www.cnbc.com/id/15839135/device/rss/rss.html",

    "CNBC Finance":
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",

    "CNBC World News":
        "https://www.cnbc.com/id/100727362/device/rss/rss.html",

    "CNBC Top News":
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",

    "BBC Business":
        "https://feeds.bbci.co.uk/news/business/rss.xml",
}


# ============================================================
# 新闻源可信度
# ============================================================

SOURCE_PRIORITY = {

    "CNBC Finance": 10,

    "CNBC Markets": 10,

    "CNBC World News": 9,

    "CNBC Top News": 9,

    "BBC Business": 9,

}


# ============================================================
# 市场相关关键词
# ============================================================

MARKET_KEYWORDS = [

    # ----------------------------
    # 宏观
    # ----------------------------

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
    "unemployment",
    "gdp",
    "central bank",
    "treasury yield",
    "bond yield",

    # ----------------------------
    # 股票市场
    # ----------------------------

    "stock market",
    "stocks",
    "equity",
    "equities",
    "nasdaq",
    "s&p 500",
    "dow jones",
    "nikkei",
    "kospi",
    "hang seng",
    "shares",
    "market rally",
    "market selloff",
    "selloff",
    "sell-off",
    "market crash",
    "vix",

    # ----------------------------
    # 龙头科技
    # ----------------------------

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
    "broadcom",
    "amd",
    "intel",

    # ----------------------------
    # AI / 半导体
    # ----------------------------

    "artificial intelligence",
    "ai model",
    "ai chip",
    "gpu",
    "semiconductor",
    "chip",
    "chips",
    "memory",
    "hbm",
    "optical",
    "optical networking",
    "data center",
    "data centre",
    "foundry",

    # ----------------------------
    # 中国 / 贸易
    # ----------------------------

    "china",
    "tariff",
    "tariffs",
    "trade war",
    "trade",
    "sanction",
    "sanctions",
    "export controls",
    "export restriction",

    # ----------------------------
    # 商品
    # ----------------------------

    "oil",
    "crude",
    "brent",
    "wti",
    "opec",
    "gold",
    "silver",
    "copper",
    "natural gas",
    "commodity",
    "commodities",

    # ----------------------------
    # 外汇 / 债券
    # ----------------------------

    "dollar",
    "yen",
    "yuan",
    "forex",
    "currency",
    "treasury",
    "bond",
    "yield",

    # ----------------------------
    # 地缘政治
    # ----------------------------

    "war",
    "conflict",
    "military",
    "missile",
    "attack",
    "strike",
    "ceasefire",
    "geopolitical",
    "iran",
    "israel",
    "russia",
    "ukraine",
    "taiwan",
    "middle east",

]


# ============================================================
# 高影响关键词
# ============================================================

HIGH_IMPACT_KEYWORDS = [

    "fed",
    "fomc",
    "interest rate",
    "rate cut",
    "rate hike",
    "inflation",
    "cpi",
    "payroll",
    "gdp",
    "central bank",

    "nvidia",
    "broadcom",
    "amd",
    "tsmc",
    "semiconductor",
    "chip export",
    "export controls",
    "artificial intelligence",

    "opec",
    "oil",
    "crude",
    "brent",
    "gold",

    "market crash",
    "selloff",
    "sell-off",
    "surge",
    "plunge",
    "record high",
    "record low",

    "war",
    "sanctions",
    "tariff",
    "trade war",
    "military attack",

    "earnings",
    "guidance",
    "acquisition",
    "merger",
    "bankruptcy",

]


# ============================================================
# 分类关键词
# ============================================================

CATEGORY_KEYWORDS = {

    "宏观经济与央行政策": [

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
        "unemployment",
        "gdp",
        "central bank",
        "treasury yield",
        "bond yield",

    ],

    "AI与半导体": [

        "artificial intelligence",
        "ai model",
        "ai chip",
        "gpu",
        "nvidia",
        "amd",
        "broadcom",
        "intel",
        "tsmc",
        "asml",
        "semiconductor",
        "chip",
        "chips",
        "memory",
        "hbm",
        "optical",
        "data center",
        "data centre",
        "foundry",

    ],

    "全球金融市场": [

        "stock market",
        "stocks",
        "equity",
        "equities",
        "nasdaq",
        "s&p 500",
        "dow jones",
        "nikkei",
        "kospi",
        "hang seng",
        "market rally",
        "market selloff",
        "selloff",
        "sell-off",
        "market crash",
        "vix",
        "dollar",
        "yen",
        "yuan",
        "forex",
        "currency",
        "treasury",
        "bond",
        "yield",

    ],

    "能源与大宗商品": [

        "oil",
        "crude",
        "brent",
        "wti",
        "opec",
        "gold",
        "silver",
        "copper",
        "natural gas",
        "commodity",
        "commodities",

    ],

    "公司重大事件": [

        "earnings",
        "quarterly results",
        "results",
        "revenue",
        "profit",
        "guidance",
        "forecast",
        "outlook",
        "acquisition",
        "merger",
        "takeover",
        "bankruptcy",
        "layoffs",
        "ipo",

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
        "salesforce",

    ],

    "地缘政治与制裁": [

        "war",
        "conflict",
        "military",
        "missile",
        "attack",
        "strike",
        "ceasefire",
        "geopolitical",
        "sanctions",
        "tariff",
        "trade war",
        "export controls",

        "iran",
        "israel",
        "russia",
        "ukraine",
        "taiwan",
        "middle east",

    ],

}


# ============================================================
# 排除关键词
# ============================================================

EXCLUDE_KEYWORDS = [

    # ========================================================
    # 评论 / 观点类
    # ========================================================

    "op-ed",
    "opinion",
    "commentary",
    "editorial",
    "analysis:",
    "what we learned",
    "investing club",
    "homestretch",

    # ========================================================
    # 司法 / 法律案件
    # ========================================================

    "court case",
    "lawsuit",
    "legal case",
    "criminal case",
    "conviction",
    "hush money",
    "trial",
    "appeal",

    # ========================================================
    # 娱乐
    # ========================================================

    "celebrity",
    "entertainment",
    "movie",
    "music",
    "sports",

    # ========================================================
    # 生活
    # ========================================================

    "travel",
    "food",
    "restaurant",
    "lifestyle",

]


# ============================================================
# 文本清洗
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = text.lower()

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

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


# ============================================================
# 关键词匹配
# ============================================================

def keyword_match(
    text,
    keyword
):

    text = clean_text(text)

    keyword = clean_text(keyword)

    if not text or not keyword:

        return False

    # 多词关键词
    if " " in keyword:

        return keyword in text

    # 单词关键词使用完整单词匹配
    pattern = rf"\b{re.escape(keyword)}\b"

    return re.search(
        pattern,
        text
    ) is not None


# ============================================================
# 发布时间解析
# ============================================================

def parse_publish_time(item):

    candidates = [

        getattr(
            item,
            "published",
            ""
        ),

        getattr(
            item,
            "updated",
            ""
        ),

    ]

    for value in candidates:

        if not value:
            continue

        try:

            dt = parsedate_to_datetime(
                value
            )

            if dt.tzinfo is None:

                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(
                timezone.utc
            )

        except Exception:
            pass

    # feedparser parsed time

    parsed = getattr(
        item,
        "published_parsed",
        None
    )

    if parsed:

        try:

            return datetime(
                parsed.tm_year,
                parsed.tm_mon,
                parsed.tm_mday,
                parsed.tm_hour,
                parsed.tm_min,
                parsed.tm_sec,
                tzinfo=timezone.utc
            )

        except Exception:
            pass

    return None


# ============================================================
# 时间格式
# ============================================================

def format_publish_time(dt):

    if not dt:
        return "时间缺失"

    china_tz = timezone(
        timedelta(hours=8)
    )

    return dt.astimezone(
        china_tz
    ).strftime(
        "%Y-%m-%d %H:%M"
    )


# ============================================================
# 市场相关判断
# ============================================================

def is_market_relevant(
    title,
    summary=""
):

    text = clean_text(
        f"{title} {summary}"
    )


    # ========================================================
    # 第一层：明确市场关键词
    # ========================================================

    if any(
        keyword in text
        for keyword in MARKET_KEYWORDS
    ):

        return True


    # ========================================================
    # 第二层：重大金融 / 公司事件
    # ========================================================

    secondary_keywords = [

        # 公司重大事件
        "earnings",
        "quarterly results",
        "revenue",
        "profit",
        "guidance",
        "forecast",
        "outlook",

        "acquisition",
        "merger",
        "takeover",
        "bankruptcy",

        # 金融机构
        "bank",
        "banking",
        "insurer",
        "insurance",
        "financial institution",

        # 市场走势
        "traders",
        "investors",
        "investor",
        "shares",
        "stocks",

        # 科技产业
        "software",
        "cloud",
        "data center",
        "technology",

        # 国际经济
        "economy",
        "economic",
        "trade",
        "imports",
        "exports",

    ]

    if any(
        keyword in text
        for keyword in secondary_keywords
    ):

        return True


    return False

# ============================================================
# 排除低价值新闻
# ============================================================

def is_excluded(
    title,
    summary=""
):

    text = clean_text(
        f"{title} {summary}"
    )

    return any(
        keyword_match(
            text,
            keyword
        )
        for keyword in EXCLUDE_KEYWORDS
    )


# ============================================================
# 分类
# ============================================================

def classify_news(
    title,
    summary=""
):

    text = clean_text(
        f"{title} {summary}"
    )


    # ========================================================
    # 1. 宏观经济与央行政策
    # ========================================================

    macro_keywords = [

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
        "unemployment",
        "gdp",
        "central bank",
        "treasury yield",
        "bond yield",

    ]

    if any(
        keyword_match(
            text,
            keyword
        )
        for keyword in macro_keywords
    ):

        return "宏观经济与央行政策"


    # ========================================================
    # 2. 地缘政治与制裁
    # ========================================================

    geopolitical_keywords = [

        "war",
        "conflict",
        "military",
        "missile",
        "attack",
        "strike",
        "ceasefire",
        "geopolitical",
        "sanctions",
        "tariff",
        "trade war",
        "export controls",

        "iran",
        "israel",
        "russia",
        "ukraine",
        "taiwan",
        "middle east",

    ]

    if any(
        keyword_match(
            text,
            keyword
        )
        for keyword in geopolitical_keywords
    ):

        return "地缘政治与制裁"


    # ========================================================
    # 3. 能源与大宗商品
    # ========================================================

    commodity_keywords = [

        "oil",
        "crude",
        "brent",
        "wti",
        "opec",
        "gold",
        "silver",
        "copper",
        "natural gas",
        "commodity",
        "commodities",

    ]

    if any(
        keyword_match(
            text,
            keyword
        )
        for keyword in commodity_keywords
    ):

        return "能源与大宗商品"


    # ========================================================
    # 4. AI与半导体
    # ========================================================

    ai_keywords = [

        "artificial intelligence",
        "ai model",
        "ai chip",
        "gpu",
        "nvidia",
        "amd",
        "broadcom",
        "intel",
        "tsmc",
        "asml",
        "semiconductor",
        "chip",
        "chips",
        "memory",
        "hbm",
        "optical",
        "data center",
        "data centre",
        "foundry",

    ]

    if any(
        keyword_match(
            text,
            keyword
        )
        for keyword in ai_keywords
    ):

        return "AI与半导体"


    # ========================================================
    # 5. 公司重大事件
    # ========================================================

    company_keywords = [

        "earnings",
        "quarterly results",
        "results",
        "revenue",
        "profit",
        "guidance",
        "forecast",
        "outlook",
        "acquisition",
        "merger",
        "takeover",
        "bankruptcy",
        "layoffs",
        "ipo",

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
        "salesforce",

    ]

    if any(
        keyword_match(
            text,
            keyword
        )
        for keyword in company_keywords
    ):

        return "公司重大事件"


    # ========================================================
    # 6. 全球金融市场
    # ========================================================

    market_keywords = [

        "stock market",
        "stocks",
        "equity",
        "equities",
        "nasdaq",
        "s&p 500",
        "dow jones",
        "nikkei",
        "kospi",
        "hang seng",
        "market rally",
        "market selloff",
        "selloff",
        "sell-off",
        "market crash",
        "vix",
        "dollar",
        "yen",
        "yuan",
        "forex",
        "currency",
        "treasury",
        "bond",
        "yield",

    ]

    if any(
        keyword_match(
            text,
            keyword
        )
        for keyword in market_keywords
    ):

        return "全球金融市场"


    return "全球金融市场"

# ============================================================
# 标题去重
# ============================================================

def is_duplicate(
    title,
    existing_titles,
    threshold=0.82
):

    title = clean_text(
        title
    )

    # ========================================================
    # 1. 标题高度相似
    # ========================================================

    for existing in existing_titles:

        similarity = SequenceMatcher(
            None,
            title,
            existing
        ).ratio()

        if similarity >= threshold:

            return True


    # ========================================================
    # 2. 关键事件词组合去重
    # ========================================================

    event_groups = [

        # Fed / Jackson Hole
        [
            "warsh",
            "jackson hole",
        ],

        # Fed 利率
        [
            "fed",
            "rate",
        ],

        # 通胀
        [
            "fed",
            "inflation",
        ],

        # Nvidia
        [
            "nvidia",
            "earnings",
        ],

        # Salesforce
        [
            "salesforce",
            "ai",
        ],

        # TSMC
        [
            "tsmc",
            "chip",
        ],

        # 原油
        [
            "oil",
            "venezuela",
        ],

        # 伊朗
        [
            "iran",
            "sanctions",
        ],

    ]


    for group in event_groups:

        if all(
            keyword in title
            for keyword in group
        ):

            for existing in existing_titles:

                if all(
                    keyword in existing
                    for keyword in group
                ):

                    return True


    return False


# ============================================================
# 新闻重要性评分
# ============================================================

def calculate_score(
    article
):

    title = clean_text(
        article["title"]
    )

    summary = clean_text(
        article.get(
            "summary",
            ""
        )
    )

    text = f"{title} {summary}"

    score = 0


    # ========================================================
    # 1. 市场影响范围：0-30
    # ========================================================

    scope_keywords = [

        # 央行 / 宏观
        "fed",
        "fomc",
        "federal reserve",
        "central bank",
        "interest rate",
        "rate cut",
        "rate hike",
        "inflation",
        "cpi",
        "gdp",

        # 贸易 / 地缘
        "tariff",
        "trade war",
        "sanctions",
        "war",
        "military attack",

        # 能源
        "opec",
        "oil",
        "crude",
        "brent",

        # 金融市场
        "global market",
        "stock market",
        "market crash",
        "market selloff",
        "selloff",

    ]

    scope_hits = sum(
        1
        for word in scope_keywords
        if word in text
    )

    if scope_hits >= 4:
        score += 30

    elif scope_hits == 3:
        score += 27

    elif scope_hits == 2:
        score += 23

    elif scope_hits == 1:
        score += 16

    else:
        score += 5


    # ========================================================
    # 2. 直接市场冲击：0-30
    # ========================================================

    direct_impact_keywords = [

        "rate hike",
        "rate cut",
        "interest rate",

        "inflation",
        "cpi",
        "payroll",
        "gdp",

        "market crash",
        "selloff",
        "sell-off",
        "surge",
        "plunge",

        "record high",
        "record low",

        "earnings",
        "quarterly results",
        "guidance",

        "acquisition",
        "merger",
        "takeover",
        "bankruptcy",

        "oil",
        "crude",
        "brent",
        "opec",

        "sanctions",
        "tariff",
        "trade war",

        "export controls",

    ]

    impact_hits = sum(
        1
        for word in direct_impact_keywords
        if word in text
    )

    if impact_hits >= 5:
        score += 30

    elif impact_hits >= 4:
        score += 27

    elif impact_hits >= 3:
        score += 23

    elif impact_hits >= 2:
        score += 18

    elif impact_hits == 1:
        score += 12

    else:
        score += 5


    # ========================================================
    # 3. 龙头公司 / 核心资产：0-15
    # ========================================================

    major_assets = [

        "nvidia",
        "apple",
        "microsoft",
        "amazon",
        "alphabet",
        "google",
        "meta",
        "tesla",
        "broadcom",
        "amd",
        "intel",
        "tsmc",
        "asml",

    ]

    asset_hits = sum(
        1
        for word in major_assets
        if word in text
    )

    if asset_hits >= 3:
        score += 15

    elif asset_hits == 2:
        score += 12

    elif asset_hits == 1:
        score += 8


    # ========================================================
    # 4. 来源可信度：0-10
    # ========================================================

    score += SOURCE_PRIORITY.get(
        article["source"],
        5
    )


    # ========================================================
    # 5. 重大事件类型：0-10
    # ========================================================

    event_keywords = [

        "earnings",
        "results",
        "guidance",

        "rate",
        "fed",
        "fomc",

        "tariff",
        "sanctions",

        "oil",
        "crude",
        "brent",

        "war",
        "military",

        "acquisition",
        "merger",
        "bankruptcy",

    ]

    if any(
        word in title
        for word in event_keywords
    ):

        score += 10

    else:

        score += 4


    # ========================================================
    # 6. Opinion / Analysis 大幅降权
    # ========================================================

    opinion_words = [

        "op-ed",
        "opinion",
        "commentary",
        "editorial",
        "analysis",

    ]

    if any(
        word in title
        for word in opinion_words
    ):

        score -= 20


    # ========================================================
    # 7. 低市场价值人物 / 故事类新闻降权
    # ========================================================

    low_value_patterns = [

        "birthday",
        "remains active",
        "what we learned",
        "who's next",
        "social media fears",
        "landmark settlement",

    ]

    if any(
        word in title
        for word in low_value_patterns
    ):

        score -= 15


    # ========================================================
    # 8. 时效性：0-20
    # ========================================================

    published_at = article.get(
        "published_at"
    )

    if published_at:

        now = datetime.now(
            timezone.utc
        )

        hours = (
            now - published_at
        ).total_seconds() / 3600

        if hours <= 6:

            score += 20

        elif hours <= 12:

            score += 17

        elif hours <= 24:

            score += 14

        elif hours <= 36:

            score += 10

        else:

            score += 2


    # ========================================================
    # 最终限制：0-100
    # ========================================================

    return max(
        0,
        min(
            100,
            score
        )
    )


# ============================================================
# 获取新闻
# ============================================================

def get_news_data():

    articles = []

    existing_titles = []

    since = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            hours=NEWS_WINDOW_HOURS
        )
    )


    print(
        "\n============================================================"
    )

    print(
        "开始获取全球重大市场事件"
    )

    print(
        f"新闻时间窗口：最近 "
        f"{NEWS_WINDOW_HOURS} 小时"
    )


    # ========================================================
    # RSS
    # ========================================================

    for source, url in NEWS_FEEDS.items():

        print(
            f"\n正在获取新闻源：{source}"
        )

        try:

            feed = feedparser.parse(
                url
            )

            if getattr(
                feed,
                "bozo",
                False
            ):

                print(
                    f"警告：{source} RSS解析异常"
                )


            source_count = 0


            for item in feed.entries[:50]:

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


                if not title or not link:

                    continue


                published_at = (
                    parse_publish_time(
                        item
                    )
                )


                # 没有明确发布时间
                # 不猜测
                if not published_at:

                    continue


                # =================================================
                # 时间窗口
                # =================================================

                if published_at < since:

                    continue


                # =================================================
                # 市场相关性
                # =================================================

                if not is_market_relevant(
                    title,
                    summary
                ):

                    continue


                # =================================================
                # 排除低价值资讯
                # =================================================

                if is_excluded(
                    title,
                    summary
                ):

                    continue


                # =================================================
                # 标题去重
                # =================================================

                if is_duplicate(
                    title,
                    existing_titles
                ):

                    continue


                existing_titles.append(
                    clean_text(title)
                )


                article = {

                    "title":
                        title,

                    "summary":
                        summary,

                    "source":
                        source,

                    "published":
                        format_publish_time(
                            published_at
                        ),

                    "published_at":
                        published_at,

                    "url":
                        link,

                    "category":
                        classify_news(
                            title,
                            summary
                        ),

                }


                article["score"] = (
                    calculate_score(
                        article
                    )
                )


                articles.append(
                    article
                )

                source_count += 1


            print(
                f"{source} 获取到 "
                f"{source_count} 条候选新闻"
            )


        except Exception as e:

            print(
                f"{source} 获取失败：{e}"
            )


    # ========================================================
    # 综合排序
    # ========================================================

    articles.sort(
        key=lambda x: (
            x["score"],
            x["published_at"]
        ),
        reverse=True
    )


    # ========================================================
    # TOP10
    # ========================================================

    top_news = articles[
        :MAX_NEWS
    ]


    print(
        f"\n原始有效新闻："
        f"{len(articles)} 条"
    )

    print(
        f"最终 TOP{MAX_NEWS}："
        f"{len(top_news)} 条"
    )


    return top_news


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":

    news = get_news_data()


    print(
        "\n========== TOP10重大市场事件 ==========\n"
    )


    if not news:

        print(
            "数据缺失/获取失败："
            "当前没有获得有效新闻"
        )


    else:

        for i, article in enumerate(
            news,
            1
        ):

            print(
                f"{i}. "
                f"【{article['category']}】"
            )

            print(
                f"标题："
                f"{article['title']}"
            )

            print(
                f"核心事实："
                f"{article['summary']}"
            )

            print(
                f"来源："
                f"{article['source']}"
            )

            print(
                f"时间："
                f"{article['published']}"
            )

            print(
                f"重要性评分："
                f"{article['score']}"
            )

            print(
                f"原文："
                f"{article['url']}"
            )

            print()
