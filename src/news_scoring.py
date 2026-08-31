import re
from collections import defaultdict


# ============================================================
# 全球金融市场日报
# news_scoring.py
#
# 最终规则
#
# ① 只保留对金融市场具有实际影响力的信息
#
# ② 按“事件本身是什么”进行分类
#    不按照关键词命中数量决定分类
#
# ③ 评分：
#    影响范围     40分
#    影响程度     40分
#    来源可信度   20分
#
# ④ 取消 TOP10 总量限制
#
# ⑤ >40分：
#    全部保留，不受数量限制
#
# ⑥ <=40分：
#    按分类执行 Top10
#
# ⑦ 不足10条：
#    有几条展示几条
#
# ⑧ 同一事件：
#    去重、合并
#    不重复占用展示数量
#
# ⑨ 来源：
#    官方一手源 → 事实确认
#    权威媒体 → 事件发现、背景、交叉验证
#    国际金融机构 → 权威研究
#    知名个人 → 扩展接口
#
# ⑩ 来源不决定重要性
#    来源只影响20分可信度
#
# ⑪ 高影响力研报/观点可以进入新闻池，
#    但前提是本身对金融市场具有实际影响力
#
# ⑫ 严禁 AI 编造新闻、行情、事件、引用
#
# ============================================================


# ============================================================
# 分类
# ============================================================

CATEGORY_MACRO = "宏观经济与央行政策"
CATEGORY_AI = "AI与半导体"
CATEGORY_STOCK = "全球股市"
CATEGORY_ENERGY = "能源与大宗商品"
CATEGORY_FX = "外汇与债券"
CATEGORY_GEOPOLITICS = "地缘政治与制裁"
CATEGORY_COMPANY = "公司重大事件"
CATEGORY_OTHER = "其他市场事件"

ALL_CATEGORIES = [
    CATEGORY_MACRO,
    CATEGORY_AI,
    CATEGORY_STOCK,
    CATEGORY_ENERGY,
    CATEGORY_FX,
    CATEGORY_GEOPOLITICS,
    CATEGORY_COMPANY,
    CATEGORY_OTHER,
]


# ============================================================
# 来源可信度
#
# 最高20分。
#
# 注意：
# 来源可信度绝不能代替事件影响力。
# ============================================================

SOURCE_CREDIBILITY = {

    # 官方 / 一手机构
    "Federal Reserve": 20,
    "U.S. Federal Reserve": 20,
    "European Central Bank": 20,
    "ECB": 20,
    "Bank of Japan": 20,
    "BOJ": 20,
    "People's Bank of China": 20,
    "PBOC": 20,
    "Bank of England": 20,
    "BOE": 20,
    "U.S. Treasury": 20,
    "Treasury": 20,
    "OPEC": 20,
    "IMF": 20,
    "World Bank": 20,
    "BIS": 20,

    # 权威金融媒体
    "Reuters": 19,
    "Bloomberg": 19,
    "Financial Times": 19,
    "Wall Street Journal": 19,
    "The Wall Street Journal": 19,

    "CNBC Finance": 18,
    "CNBC Markets": 18,

    "CNBC World News": 17,
    "CNBC Top News": 17,
    "BBC Business": 17,

    # 默认媒体
    "major_media": 17,
}


DEFAULT_SOURCE_CREDIBILITY = 15


# ============================================================
# 内容类型
# ============================================================

CONTENT_FACT = "fact"
CONTENT_ANALYSIS = "analysis"
CONTENT_OPINION = "opinion"
CONTENT_RESEARCH = "research"
CONTENT_UNKNOWN = "unknown"


# ============================================================
# 文本处理
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text).lower()

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"https?://\S+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def contains_term(text, term):

    text = normalize_text(text)
    term = normalize_text(term)

    if not text or not term:
        return False

    if " " in term:
        return term in text

    return re.search(
        rf"\b{re.escape(term)}\b",
        text
    ) is not None


# ============================================================
# 内容类型识别
#
# 非常重要：
#
# “事件报道”和“观点/分析”不能混为一谈。
# ============================================================

def detect_content_type(article):

    title = normalize_text(
        article.get("title", "")
    )

    summary = normalize_text(
        article.get("summary", "")
    )

    text = f"{title} {summary}"

    # --------------------------------------------------------
    # 明确的观点 / 评论 / 分析
    # --------------------------------------------------------

    opinion_patterns = [

        "jim cramer",
        "analyst roundup",
        "analysts suggest",
        "analysts say",
        "analysts expect",
        "wall street analysts",
        "what caused",
        "look to the fed for clues",
        "why",
        "here are the",
        "what we're watching",
        "what investors should",
        "opinion",
        "analysis",
        "column",
        "commentary",

    ]

    for pattern in opinion_patterns:

        if contains_term(
            text,
            pattern
        ):

            return CONTENT_ANALYSIS


    # --------------------------------------------------------
    # 研究报告
    # --------------------------------------------------------

    research_patterns = [

        "research",
        "report",
        "study",
        "outlook",
        "forecast",
        "economic outlook",
        "market outlook",

    ]

    for pattern in research_patterns:

        if contains_term(
            text,
            pattern
        ):

            return CONTENT_RESEARCH


    # --------------------------------------------------------
    # 默认视为事实报道
    # --------------------------------------------------------

    return CONTENT_FACT


# ============================================================
# 金融市场实际影响力判断
#
# 这里不是“关键词越多越重要”。
#
# 只判断：
#
#     这条信息是否有理由进入金融市场新闻池。
# ============================================================

def is_market_impactful(article):

    if not article:
        return False

    title = article.get(
        "title",
        ""
    )

    summary = article.get(
        "summary",
        ""
    )

    text = normalize_text(
        f"{title} {summary}"
    )

    if not text:
        return False

    # --------------------------------------------------------
    # 已通过 news_data.py 初筛
    # --------------------------------------------------------

    if article.get(
        "market_relevant"
    ) is True:

        return True


    # --------------------------------------------------------
    # 独立调用时的市场相关性判断
    # --------------------------------------------------------

    market_terms = [

        "fed",
        "federal reserve",
        "fomc",
        "interest rate",
        "rate cut",
        "rate hike",
        "inflation",
        "cpi",
        "ppi",
        "payroll",
        "employment",
        "gdp",

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
        "vix",

        "semiconductor",
        "chip",
        "gpu",
        "artificial intelligence",
        "nvidia",
        "broadcom",
        "tsmc",

        "earnings",
        "revenue",
        "profit",
        "guidance",
        "acquisition",
        "merger",
        "bankruptcy",
        "ipo",

        "oil",
        "crude",
        "brent",
        "wti",
        "opec",
        "gold",
        "silver",
        "copper",

        "dollar",
        "yen",
        "yuan",
        "forex",
        "treasury",
        "bond",
        "yield",

        "tariff",
        "tariffs",
        "trade war",
        "sanction",
        "sanctions",

        "war",
        "conflict",
        "military",
        "missile",
        "attack",
        "strike",
        "geopolitical",

    ]

    for term in market_terms:

        if contains_term(
            text,
            term
        ):

            return True

    return False


# ============================================================
# 事件本身分类
#
# 重点：
#
# 不再根据“关键词数量”分类。
#
# 优先判断文章真正报道的事件。
# ============================================================

def classify_event(article):

    title = normalize_text(
        article.get("title", "")
    )

    summary = normalize_text(
        article.get("summary", "")
    )

    text = f"{title} {summary}"


    # ========================================================
    # ① 公司重大事件
    #
    # 如果新闻核心是：
    # 财报、IPO、并购、破产、公司重大决策
    #
    # 即使文章同时提到 AI / 股票，
    # 仍然按照事件本身归入公司事件。
    # ========================================================

    company_patterns = [

        "earnings",
        "quarterly results",
        "first-half earnings",
        "annual results",
        "revenue",
        "profit",
        "guidance",
        "ipo",
        "initial public offering",
        "acquisition",
        "merger",
        "takeover",
        "bankruptcy",

    ]

    for pattern in company_patterns:

        if contains_term(
            text,
            pattern
        ):

            return CATEGORY_COMPANY


    # ========================================================
    # ② 宏观经济 / 央行政策
    #
    # 核心是政策、利率、通胀、经济数据。
    # ========================================================

    macro_patterns = [

        "federal reserve",
        "fed chair",
        "fomc",
        "interest rate",
        "rate hike",
        "rate cut",
        "inflation",
        "cpi",
        "ppi",
        "payroll",
        "unemployment",
        "gdp",
        "central bank",

    ]

    for pattern in macro_patterns:

        if contains_term(
            text,
            pattern
        ):

            return CATEGORY_MACRO


    # ========================================================
    # ③ 地缘政治与制裁
    #
    # 核心是：
    # 战争、军事行动、制裁、贸易战、关税。
    # ========================================================

    geopolitics_patterns = [

        "war",
        "armed conflict",
        "military",
        "missile",
        "attack",
        "strike",
        "ceasefire",
        "sanction",
        "sanctions",
        "trade war",
        "tariff",
        "tariffs",
        "export controls",

    ]

    for pattern in geopolitics_patterns:

        if contains_term(
            text,
            pattern
        ):

            return CATEGORY_GEOPOLITICS


    # ========================================================
    # ④ 能源与大宗商品
    # ========================================================

    energy_patterns = [

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

    for pattern in energy_patterns:

        if contains_term(
            text,
            pattern
        ):

            return CATEGORY_ENERGY


    # ========================================================
    # ⑤ AI与半导体
    # ========================================================

    ai_patterns = [

        "artificial intelligence",
        "ai chip",
        "gpu",
        "semiconductor",
        "chip",
        "chips",
        "memory",
        "hbm",
        "optical networking",
        "data center",
        "data centre",
        "foundry",

        "nvidia",
        "amd",
        "broadcom",
        "intel",
        "tsmc",
        "asml",

    ]

    for pattern in ai_patterns:

        if contains_term(
            text,
            pattern
        ):

            return CATEGORY_AI


    # ========================================================
    # ⑥ 外汇与债券
    # ========================================================

    fx_patterns = [

        "dollar",
        "yen",
        "yuan",
        "forex",
        "currency",
        "treasury",
        "bond",
        "bonds",
        "yield",

    ]

    for pattern in fx_patterns:

        if contains_term(
            text,
            pattern
        ):

            return CATEGORY_FX


    # ========================================================
    # ⑦ 全球股市
    # ========================================================

    stock_patterns = [

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
        "vix",
        "rally",
        "selloff",
        "sell-off",
        "market crash",

    ]

    for pattern in stock_patterns:

        if contains_term(
            text,
            pattern
        ):

            return CATEGORY_STOCK


    return CATEGORY_OTHER


# ============================================================
# 来源可信度
# ============================================================

def get_source_credibility(article):

    source = str(
        article.get(
            "source",
            ""
        )
    ).strip()

    if source in SOURCE_CREDIBILITY:

        return SOURCE_CREDIBILITY[
            source
        ]

    source_type = str(
        article.get(
            "source_type",
            ""
        )
    ).strip()

    if source_type in SOURCE_CREDIBILITY:

        return SOURCE_CREDIBILITY[
            source_type
        ]

    return DEFAULT_SOURCE_CREDIBILITY


# ============================================================
# 影响范围
#
# 0 - 40
#
# 不是关键词计数。
#
# 而是根据事件涉及的实际市场范围。
# ============================================================

def score_impact_scope(article):

    category = article.get(
        "category",
        CATEGORY_OTHER
    )

    title = normalize_text(
        article.get(
            "title",
            ""
        )
    )

    summary = normalize_text(
        article.get(
            "summary",
            ""
        )
    )

    text = f"{title} {summary}"


    # ========================================================
    # 宏观政策
    # ========================================================

    if category == CATEGORY_MACRO:

        if any(
            contains_term(text, x)
            for x in [
                "federal reserve",
                "fomc",
                "global economy",
                "interest rate",
            ]
        ):

            return 40

        return 32


    # ========================================================
    # 地缘政治
    # ========================================================

    if category == CATEGORY_GEOPOLITICS:

        if any(
            contains_term(text, x)
            for x in [
                "war",
                "armed conflict",
                "trade war",
                "iran",
                "russia",
                "ukraine",
                "middle east",
            ]
        ):

            return 38

        return 30


    # ========================================================
    # 能源
    # ========================================================

    if category == CATEGORY_ENERGY:

        if any(
            contains_term(text, x)
            for x in [
                "opec",
                "global oil",
                "oil supply",
                "oil reserves",
                "crude",
            ]
        ):

            return 34

        return 25


    # ========================================================
    # 外汇 / 债券
    # ========================================================

    if category == CATEGORY_FX:

        if any(
            contains_term(text, x)
            for x in [
                "dollar",
                "treasury",
                "bond",
                "yield",
                "global",
            ]
        ):

            return 32

        return 24


    # ========================================================
    # AI / 半导体
    # ========================================================

    if category == CATEGORY_AI:

        if any(
            contains_term(text, x)
            for x in [
                "nvidia",
                "broadcom",
                "tsmc",
                "semiconductor industry",
                "global semiconductor",
            ]
        ):

            return 28

        return 22


    # ========================================================
    # 全球股市
    # ========================================================

    if category == CATEGORY_STOCK:

        if any(
            contains_term(text, x)
            for x in [
                "global stock market",
                "global markets",
                "wall street",
                "major indexes",
            ]
        ):

            return 32

        return 24


    # ========================================================
    # 公司事件
    # ========================================================

    if category == CATEGORY_COMPANY:

        return 22


    return 10


# ============================================================
# 影响程度
#
# 0 - 40
#
# 核心不是“新闻看起来重要”。
#
# 核心是：
#
#     是否已经造成，
#     或高度可能造成，
#     金融资产重新定价。
# ============================================================

def score_impact_degree(article):

    category = article.get(
        "category",
        CATEGORY_OTHER
    )

    title = normalize_text(
        article.get(
            "title",
            ""
        )
    )

    summary = normalize_text(
        article.get(
            "summary",
            ""
        )
    )

    text = f"{title} {summary}"

    content_type = article.get(
        "content_type",
        CONTENT_FACT
    )


    # ========================================================
    # 观点 / 分析文章降权
    #
    # 因为：
    #
    # “分析市场”
    #
    # ≠
    #
    # “发生了新的市场事件”
    # ========================================================

    analysis_discount = (
        10
        if content_type in [
            CONTENT_ANALYSIS,
            CONTENT_OPINION
        ]
        else 0
    )


    # ========================================================
    # 已经明确发生市场冲击
    # ========================================================

    direct_market_impact = [

        "shares plunge",
        "shares slide",
        "stocks fell",
        "stocks rise",
        "market selloff",
        "market rally",
        "markets surged",
        "markets plunged",
        "yield jumped",
        "yield fell",
        "dollar jumped",
        "dollar fell",
        "oil surged",
        "oil plunged",
        "prices surged",
        "prices plunged",

    ]

    for pattern in direct_market_impact:

        if contains_term(
            text,
            pattern
        ):

            return max(
                30 - analysis_discount,
                5
            )


    # ========================================================
    # 极强的政策 / 冲突事件
    # ========================================================

    if category == CATEGORY_MACRO:

        if any(
            contains_term(text, x)
            for x in [
                "rate hike",
                "rate cut",
                "fomc decision",
                "fed decision",
                "emergency",
            ]
        ):

            return max(
                36 - analysis_discount,
                5
            )


    if category == CATEGORY_GEOPOLITICS:

        if any(
            contains_term(text, x)
            for x in [
                "exchange strikes",
                "armed conflict",
                "war",
                "major attack",
                "strait of hormuz",
            ]
        ):

            return max(
                36 - analysis_discount,
                5
            )


    # ========================================================
    # 重要政策 / 供给 / 公司事件
    # ========================================================

    if category == CATEGORY_ENERGY:

        if any(
            contains_term(text, x)
            for x in [
                "oil supply",
                "opec",
                "production cut",
                "production increase",
                "oil reserves",
            ]
        ):

            return max(
                30 - analysis_discount,
                5
            )


    if category == CATEGORY_COMPANY:

        if any(
            contains_term(text, x)
            for x in [
                "earnings",
                "ipo",
                "bankruptcy",
                "acquisition",
                "merger",
            ]
        ):

            return max(
                28 - analysis_discount,
                5
            )


    if category == CATEGORY_AI:

        if any(
            contains_term(text, x)
            for x in [
                "nvidia",
                "broadcom",
                "tsmc",
                "semiconductor",
            ]
        ):

            return max(
                24 - analysis_discount,
                5
            )


    # ========================================================
    # 普通市场信息
    # ========================================================

    return max(
        15 - analysis_discount,
        5
    )


# ============================================================
# 单条新闻评分
# ============================================================

def score_article(article):

    article = dict(
        article
    )

    article[
        "content_type"
    ] = detect_content_type(
        article
    )

    article[
        "category"
    ] = classify_event(
        article
    )

    article[
        "impact_scope"
    ] = score_impact_scope(
        article
    )

    article[
        "impact_degree"
    ] = score_impact_degree(
        article
    )

    article[
        "source_credibility"
    ] = get_source_credibility(
        article
    )

    article[
        "score"
    ] = (
        article["impact_scope"]
        + article["impact_degree"]
        + article["source_credibility"]
    )

    return article


# ============================================================
# 事件实体识别
#
# 目标：
# 同一事件的多篇报道合并。
# ============================================================

def identify_event(article):

    title = normalize_text(
        article.get(
            "title",
            ""
        )
    )

    summary = normalize_text(
        article.get(
            "summary",
            ""
        )
    )

    text = f"{title} {summary}"


    # ========================================================
    # 美联储 / Jackson Hole / 利率
    # ========================================================

    if (
        "jackson hole" in text
        or "fed chair" in text
        or "federal reserve" in text
    ):

        if any(
            x in text
            for x in [
                "warsh",
                "rate hike",
                "rate cut",
                "hawkish",
            ]
        ):

            return "FED_POLICY_JACKSON_HOLE"


    # ========================================================
    # 美伊冲突
    # ========================================================

    if (
        "iran" in text
        and (
            "strike" in text
            or "war" in text
            or "hormuz" in text
            or "larak" in text
            or "kharg" in text
        )
    ):

        return "US_IRAN_CONFLICT"


    # ========================================================
    # 俄乌冲突
    # ========================================================

    if (
        "russia" in text
        and "ukraine" in text
    ):

        return "RUSSIA_UKRAINE_CONFLICT"


    # ========================================================
    # 美加贸易战
    # ========================================================

    if (
        "canada" in text
        and (
            "tariff" in text
            or "trade war" in text
        )
    ):

        return "US_CANADA_TRADE_WAR"


    # ========================================================
    # 委内瑞拉石油
    # ========================================================

    if (
        "venezuela" in text
        and (
            "65 billion barrels" in text
            or "oil reserves" in text
            or "oil" in text
        )
    ):

        return "VENEZUELA_OIL_DEAL"


    # ========================================================
    # Jio IPO
    # ========================================================

    if (
        "jio" in text
        and "ipo" in text
    ):

        return "JIO_IPO"


    # ========================================================
    # BYD 财报
    # ========================================================

    if (
        "byd" in text
        and (
            "earnings" in text
            or "first-half" in text
            or "profit" in text
        )
    ):

        return "BYD_EARNINGS"


    # ========================================================
    # 无法明确识别
    #
    # 使用规范化标题作为事件ID。
    # ========================================================

    words = re.findall(
        r"[a-z0-9]+",
        title
    )

    stop_words = {

        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "as",
        "with",
        "is",
        "are",
        "was",
        "were",
        "this",
        "that",
        "how",
        "why",
        "what",
        "here",
        "says",
        "say",

    }

    words = [
        x
        for x in words
        if x not in stop_words
    ]

    return " ".join(
        words[:8]
    )


# ============================================================
# 同一事件合并
#
# 主报道：
#     选择评分最高的真实报道
#
# 辅助来源：
#     保存其他真实来源名称和链接
#
# 不创造任何新的事实。
# ============================================================

def merge_same_events(articles):

    groups = defaultdict(list)

    for article in articles:

        event_id = identify_event(
            article
        )

        article = dict(
            article
        )

        article[
            "event_id"
        ] = event_id

        groups[
            event_id
        ].append(
            article
        )


    merged = []


    for event_id, group in groups.items():

        # ----------------------------------------------------
        # 最高分报道作为主报道
        # ----------------------------------------------------

        group.sort(
            key=lambda x: (
                x.get(
                    "score",
                    0
                ),
                x.get(
                    "published_at"
                )
                or ""
            ),
            reverse=True
        )

        primary = dict(
            group[0]
        )


        # ----------------------------------------------------
        # 记录相关来源
        # ----------------------------------------------------

        related_sources = []
        related_urls = []

        for article in group:

            source = article.get(
                "source"
            )

            url = article.get(
                "url"
            )

            if (
                source
                and source not in related_sources
            ):

                related_sources.append(
                    source
                )

            if (
                url
                and url not in related_urls
            ):

                related_urls.append(
                    url
                )


        primary[
            "related_sources"
        ] = related_sources

        primary[
            "related_urls"
        ] = related_urls

        primary[
            "related_article_count"
        ] = len(
            group
        )

        primary[
            "event_id"
        ] = event_id


        merged.append(
            primary
        )


    return merged


# ============================================================
# 低权重分类 Top10
#
# 注意：
#
# >40：
#     全部保留
#
# <=40：
#     分类后每类最多10条
# ============================================================

def apply_low_score_limit(
    articles,
    limit=10
):

    high_score = []
    low_score = []

    for article in articles:

        score = article.get(
            "score",
            0
        )

        if score > 40:

            high_score.append(
                article
            )

        else:

            low_score.append(
                article
            )


    # --------------------------------------------------------
    # 高权重全部保留
    # --------------------------------------------------------

    result = list(
        high_score
    )


    # --------------------------------------------------------
    # 低权重按分类
    # --------------------------------------------------------

    category_groups = defaultdict(list)

    for article in low_score:

        category = article.get(
            "category",
            CATEGORY_OTHER
        )

        category_groups[
            category
        ].append(
            article
        )


    # --------------------------------------------------------
    # 每类最多10条
    # --------------------------------------------------------

    for category, items in category_groups.items():

        items.sort(
            key=lambda x: (
                x.get(
                    "score",
                    0
                ),
                x.get(
                    "published_at"
                )
                or ""
            ),
            reverse=True
        )

        result.extend(
            items[:limit]
        )


    return result


# ============================================================
# 分类
# ============================================================

def group_by_category(articles):

    result = {
        category: []
        for category in ALL_CATEGORIES
    }

    for article in articles:

        category = article.get(
            "category",
            CATEGORY_OTHER
        )

        if category not in result:

            category = CATEGORY_OTHER

        result[
            category
        ].append(
            article
        )


    for category in result:

        result[
            category
        ].sort(
            key=lambda x: (
                x.get(
                    "score",
                    0
                ),
                x.get(
                    "published_at"
                )
                or ""
            ),
            reverse=True
        )


    return result


# ============================================================
# 主入口
#
# news_data.py:
#
#     from news_scoring import select_news
#
#     result = select_news(raw_news)
#
# ============================================================

def select_news(raw_news):

    if not raw_news:

        return {
            category: []
            for category in ALL_CATEGORIES
        }


    # ========================================================
    # 第一步
    # 实际金融市场影响力筛选
    # ========================================================

    candidates = []

    for article in raw_news:

        if not is_market_impactful(
            article
        ):

            continue

        # ----------------------------------------------------
        # 必须有来源
        # ----------------------------------------------------

        if not article.get(
            "source"
        ):

            continue

        # ----------------------------------------------------
        # 必须有原文链接
        # ----------------------------------------------------

        if not article.get(
            "url"
        ):

            continue

        candidates.append(
            article
        )


    if not candidates:

        return {
            category: []
            for category in ALL_CATEGORIES
        }


    # ========================================================
    # 第二步
    # 评分 + 分类
    # ========================================================

    scored = []

    for article in candidates:

        scored_article = score_article(
            article
        )

        scored.append(
            scored_article
        )


    # ========================================================
    # 第三步
    # 同一事件合并
    # ========================================================

    merged = merge_same_events(
        scored
    )


    # ========================================================
    # 第四步
    #
    # >40全部保留
    # <=40分类Top10
    # ========================================================

    selected = apply_low_score_limit(
        merged,
        limit=10
    )


    # ========================================================
    # 第五步
    # 按分类输出
    # ========================================================

    return group_by_category(
        selected
    )


# ============================================================
# 兼容旧接口
# ============================================================

def fetch_news(raw_news=None):

    if raw_news is None:

        return []

    result = select_news(
        raw_news
    )

    final_news = []

    for category, items in result.items():

        for article in items:

            final_news.append(
                article
            )

    return final_news


# ============================================================
# 本地测试
# ============================================================

if __name__ == "__main__":

    test_news = [

        {
            "title":
                "Fed signals tighter policy",

            "summary":
                "Federal Reserve officials signal a tighter stance",

            "source":
                "CNBC Finance",

            "source_type":
                "major_media",

            "url":
                "https://example.com/fed",

            "market_relevant":
                True,
        },

        {
            "title":
                "BYD shares slide after first-half earnings",

            "summary":
                "BYD reported first-half earnings and shares declined",

            "source":
                "CNBC World News",

            "source_type":
                "major_media",

            "url":
                "https://example.com/byd",

            "market_relevant":
                True,
        },

    ]


    result = select_news(
        test_news
    )


    print(
        "\n============================================================"
    )

    print(
        "news_scoring.py 测试"
    )

    print(
        "============================================================"
    )


    for category, articles in result.items():

        if not articles:
            continue

        print(
            f"\n【{category}】"
        )

        for article in articles:

            print(
                f"\n标题："
                f"{article.get('title', '')}"
            )

            print(
                f"事件类型："
                f"{article.get('content_type', '')}"
            )

            print(
                f"影响范围："
                f"{article.get('impact_scope', 0)}"
            )

            print(
                f"影响程度："
                f"{article.get('impact_degree', 0)}"
            )

            print(
                f"来源可信度："
                f"{article.get('source_credibility', 0)}"
            )

            print(
                f"总分："
                f"{article.get('score', 0)}"
            )

            print(
                f"来源："
                f"{article.get('source', '')}"
            )

            print(
                f"原文："
                f"{article.get('url', '')}"
            )

            print(
                f"事件ID："
                f"{article.get('event_id', '')}"
            )
