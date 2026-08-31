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

# ============================================================
# 排除低价值 / 评论 / 分析类新闻
# ============================================================

EXCLUDE_KEYWORDS = [

    # --------------------------------------------------------
    # 评论 / 观点
    # --------------------------------------------------------

    "op-ed",
    "op ed",
    "opinion",
    "commentary",
    "editorial",
    "column",

    # --------------------------------------------------------
    # 分析类
    # --------------------------------------------------------

    "analysis:",
    "analysis",
    "what we learned",
    "what we know",
    "what to know",
    "the big lesson",
    "why investors",
    "why markets",
    "here's what",
    "heres what",

    # --------------------------------------------------------
    # 投资策略 / 市场评论
    # --------------------------------------------------------

    "investing club",
    "stock picks",
    "top stock",
    "stocks to watch",
    "market outlook",
    "investment outlook",
    "investor outlook",
    "trading strategy",
    "investment strategy",

    # --------------------------------------------------------
    # 娱乐 / 体育
    # --------------------------------------------------------

    "celebrity",
    "entertainment",
    "movie",
    "music",
    "sports",

    # --------------------------------------------------------
    # 生活方式
    # --------------------------------------------------------

    "travel",
    "food",
    "restaurant",
    "lifestyle",

    # --------------------------------------------------------
    # 美国政治 / 司法等非金融市场事件
    # --------------------------------------------------------

    "hush money",
    "court",
    "court case",
    "lawsuit",
    "legal battle",
    "conviction",
    "trial",
    "judge",
    "sentenced",
    "indicted",
    "indictment",
    "criminal case",

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
# 新闻重要性评分 V1.1
# ============================================================
# 核心原则：先判断信息是否具有金融市场价值，再评分。
# 评分维度固定为：影响范围 40 + 影响程度 40 + 来源可信度 20。
# 时效性不参与重要性评分；仅用于新闻窗口控制、排序及去重。
# 来源不决定新闻是否重要，只影响可信度。

SOURCE_CREDIBILITY_SCORE = {
    # 第一优先级：官方 / 交易所一手信息
    "Federal Reserve": 20,
    "U.S. Treasury": 20,
    "SEC": 20,
    "BEA": 20,
    "BLS": 20,
    "PBOC": 20,
    "NBS China": 20,
    "CSRC": 20,
    "HKEX": 20,
    "NYSE": 20,
    "Nasdaq": 20,
    "CME Group": 20,

    # 第二优先级：权威财经媒体
    "Reuters": 18,
    "Bloomberg": 18,
    "CNBC Finance": 18,
    "CNBC Markets": 18,
    "CNBC World News": 17,
    "CNBC Top News": 17,
    "Financial Times": 18,
    "Wall Street Journal": 18,
    "BBC Business": 17,
    "新华社": 18,

    # 第三优先级：国际金融机构
    "IMF": 19,
    "BIS": 19,
    "World Bank": 19,
}


def _event_profile(article):
    """根据文章已经识别出的事件类别和事实性信息建立事件画像。

    注意：这里不再统计关键词命中数量。关键词仅作为现有RSS文本
    分类/事件识别的基础；最终分数由事件类型的市场经济含义决定。
    """
    title = clean_text(article.get("title", ""))
    summary = clean_text(article.get("summary", ""))
    text = f"{title} {summary}"
    category = article.get("category", "全球金融市场")

    event_type = "一般市场信息"

    # 真实政策/宏观事件
    if any(x in text for x in [
        "rate decision", "rate hike", "rate cut", "interest rate",
        "fed", "fomc", "central bank", "inflation", "cpi", "ppi",
        "payroll", "gdp", "tariff", "sanctions", "export controls"
    ]):
        event_type = "政策或宏观事件"

    # 地缘重大事件
    elif any(x in text for x in [
        "war", "military attack", "missile", "invasion",
        "ceasefire", "conflict", "geopolitical"
    ]):
        event_type = "重大地缘事件"

    # 公司重大资本事件
    elif any(x in text for x in [
        "acquisition", "merger", "takeover", "bankruptcy", "ipo"
    ]):
        event_type = "重大公司资本事件"

    # 财报/经营结果
    elif any(x in text for x in [
        "earnings", "quarterly results", "revenue", "profit", "guidance"
    ]):
        event_type = "重大财报或经营事件"

    # 市场价格/风险偏好变化
    elif any(x in text for x in [
        "market crash", "market selloff", "selloff", "sell-off",
        "surge", "plunge", "soar", "slump", "tumble",
        "record high", "record low"
    ]):
        event_type = "重大市场价格变化"

    # 研究/观点：只有来源本身具备高影响力才有资格进入新闻池；
    # 是否具有市场价值由影响范围和影响程度决定。
    elif any(x in title for x in [
        "analysis", "opinion", "outlook", "forecast", "why ",
        "how ", "the big lesson", "what we learned"
    ]):
        event_type = "高影响力研究或观点"

    return category, event_type


def _impact_scope_score(article):
    """影响范围：0-40。判断影响市场、国家、行业、资产类别和参与者的广度。"""
    category, event_type = _event_profile(article)

    if event_type == "政策或宏观事件":
        return 40
    if event_type == "重大地缘事件":
        return 38

    if category == "能源与大宗商品":
        return 32 if event_type != "高影响力研究或观点" else 24

    if category == "全球金融市场":
        return 32 if event_type in ["重大市场价格变化", "政策或宏观事件"] else 24

    if category == "AI与半导体":
        return 30 if event_type in ["重大公司资本事件", "重大财报或经营事件"] else 22

    if category == "公司重大事件":
        return 28 if event_type in ["重大公司资本事件", "重大财报或经营事件"] else 20

    return 20


def _impact_degree_score(article):
    """影响程度：0-40。判断是否改变价格、估值、政策预期、资金流向、风险偏好或经营预期。"""
    category, event_type = _event_profile(article)
    title = clean_text(article.get("title", ""))
    summary = clean_text(article.get("summary", ""))
    text = f"{title} {summary}"

    if event_type == "政策或宏观事件":
        return 40
    if event_type == "重大地缘事件":
        return 38
    if event_type == "重大公司资本事件":
        return 34
    if event_type == "重大财报或经营事件":
        return 30
    if event_type == "重大市场价格变化":
        return 32

    if event_type == "高影响力研究或观点":
        # 观点只有在明确涉及政策、资产价格、估值或资金流向时才获得较高分。
        if any(x in text for x in [
            "policy", "rate", "tariff", "sanctions", "yield",
            "valuation", "capital flows", "market impact", "price"
        ]):
            return 24
        return 12

    return 10


def _source_credibility_score(article):
    source = article.get("source", "")
    return SOURCE_CREDIBILITY_SCORE.get(
        source,
        SOURCE_PRIORITY.get(source, 10) * 2
    )


def calculate_score(article):
    scope = _impact_scope_score(article)
    degree = _impact_degree_score(article)
    credibility = _source_credibility_score(article)

    return max(
        0,
        min(
            100,
            scope + degree + credibility
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
                # 重要性评分取代旧的 EXCLUDE_KEYWORDS 硬过滤
                # =================================================
                # 高影响力研报/观点允许进入评分；普通低价值观点将由
                # 影响范围、影响程度和来源可信度自然获得较低分。


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
    # 展示层：高权重全部保留；低权重最多10条
    # ========================================================
    # 高权重定义：Score > 40
    # 低权重定义：Score <= 40
    # 评分与展示数量解耦。

    high_weight_news = [
        article
        for article in articles
        if article["score"] > 40
    ]

    low_weight_news = [
        article
        for article in articles
        if article["score"] <= 40
    ]

    low_weight_news = low_weight_news[:MAX_NEWS]

    top_news = high_weight_news + low_weight_news

    print(
        f"\n原始有效新闻："
        f"{len(articles)} 条"
    )

    print(
        f"高权重新闻（>40）："
        f"{len(high_weight_news)} 条"
    )

    print(
        f"低权重新闻（<=40，最多{MAX_NEWS}条）："
        f"{len(low_weight_news)} 条"
    )

    print(
        f"最终展示："
        f"{len(top_news)} 条"
    )


    return top_news


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":

    news = get_news_data()


    print(
        "\n========== 重大市场事件 ==========\n"
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
