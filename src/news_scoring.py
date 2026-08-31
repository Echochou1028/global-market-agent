import re
from collections import defaultdict


# ============================================================
# 全球金融市场日报
# 新闻评分与筛选模块
#
# 最终规则
#
# 1. 先筛选：
#    只保留对金融市场具有实际影响力的信息
#
# 2. 再分类：
#    按“事件本身是什么”确定分类
#    不按照关键词命中数量决定分类
#
# 3. 评分：
#    影响范围     40分
#    影响程度     40分
#    来源可信度   20分
#    总分         100分
#
# 4. 取消 TOP10 总量限制
#
# 5. 高权重新闻：
#    > 40分，全部保留
#
# 6. 低权重新闻：
#    <= 40分
#    按分类执行 Top10
#
# 7. 不足10条：
#    有几条展示几条
#    不强行补足
#
# 8. 同一事件：
#    去重、合并
#    不重复占用展示数量
#
# 9. 来源定位：
#    一手官方源：
#       事实确认
#
#    权威媒体：
#       事件发现
#       背景补充
#       交叉验证
#
#    国际金融机构：
#       权威研究信息
#
#    知名个人：
#       保留扩展接口
#
# 10. 来源不决定重要性：
#     来源只影响20分可信度
#
# 11. 高影响力研报/观点：
#     可以进入新闻池
#     但前提仍然是对金融市场具有实际影响力
#
# 12. 新闻必须来自真实媒体/官方机构
#
# 13. 每条新闻必须保留：
#     来源名称 + 原文链接
#
# 14. 无法验证：
#     明确标记“数据缺失/获取失败”
#
# 15. 严禁 AI 编造：
#     新闻
#     行情
#     事件
#     引用
#
# ============================================================


# ============================================================
# 分类定义
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
# 注意：
# 来源可信度只占20分。
#
# 绝不能因为来源分高，
# 就直接把新闻判定为高影响力。
# ============================================================

SOURCE_CREDIBILITY = {

    # --------------------------------------------------------
    # 官方 / 一手机构
    # --------------------------------------------------------

    "Federal Reserve": 20,
    "U.S. Federal Reserve": 20,
    "ECB": 20,
    "European Central Bank": 20,
    "Bank of Japan": 20,
    "BOJ": 20,
    "People's Bank of China": 20,
    "PBOC": 20,
    "Bank of England": 20,
    "BOE": 20,
    "U.S. Treasury": 20,
    "Treasury": 20,
    "U.S. Department of Energy": 20,
    "OPEC": 20,
    "IMF": 20,
    "World Bank": 20,
    "BIS": 20,

    # --------------------------------------------------------
    # 国际权威金融媒体
    # --------------------------------------------------------

    "Reuters": 19,
    "Bloomberg": 19,
    "CNBC Finance": 18,
    "CNBC Markets": 18,
    "CNBC World News": 17,
    "CNBC Top News": 17,
    "BBC Business": 17,
    "Financial Times": 19,
    "Wall Street Journal": 19,
    "The Wall Street Journal": 19,

    # --------------------------------------------------------
    # 其他
    # --------------------------------------------------------

    "major_media": 17,

}


# ============================================================
# 默认可信度
# ============================================================

DEFAULT_SOURCE_CREDIBILITY = 15


# ============================================================
# 金融市场实际影响力初筛
#
# 注意：
#
# 这里不是通过“关键词数量”评分。
#
# 这里只用于判断：
#
#     这条新闻是否明显属于金融市场事件。
#
# 最终重要性仍然由：
#
#     影响范围
#     +
#     影响程度
#     +
#     来源可信度
#
# 决定。
# ============================================================

MARKET_IMPACT_TERMS = [

    # --------------------------------------------------------
    # 宏观 / 央行
    # --------------------------------------------------------

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
    "unemployment",
    "gdp",
    "central bank",

    # --------------------------------------------------------
    # 股票市场
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # AI / 半导体
    # --------------------------------------------------------

    "artificial intelligence",
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

    "nvidia",
    "amd",
    "broadcom",
    "intel",
    "tsmc",
    "asml",

    # --------------------------------------------------------
    # 公司
    # --------------------------------------------------------

    "earnings",
    "quarterly results",
    "revenue",
    "profit",
    "guidance",
    "forecast",
    "acquisition",
    "merger",
    "takeover",
    "bankruptcy",
    "ipo",

    # --------------------------------------------------------
    # 能源 / 商品
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 外汇 / 债券
    # --------------------------------------------------------

    "dollar",
    "yen",
    "yuan",
    "forex",
    "currency",
    "treasury",
    "bond",
    "bonds",
    "yield",

    # --------------------------------------------------------
    # 贸易 / 制裁
    # --------------------------------------------------------

    "tariff",
    "tariffs",
    "trade war",
    "sanction",
    "sanctions",
    "export controls",
    "export restriction",

    # --------------------------------------------------------
    # 地缘政治
    # --------------------------------------------------------

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
# 明显不属于金融市场的信息
# ============================================================

NON_MARKET_TERMS = [

    "celebrity",
    "entertainment",
    "movie",
    "music",
    "sports",
    "travel",
    "food",
    "restaurant",
    "lifestyle",

]


# ============================================================
# 文本标准化
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


# ============================================================
# 判断文本是否包含指定词
# ============================================================

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
# 金融市场实际影响力初筛
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
    # 明显非金融内容
    # --------------------------------------------------------

    for term in NON_MARKET_TERMS:

        if contains_term(
            text,
            term
        ):
            return False

    # --------------------------------------------------------
    # 已经通过上游初筛
    # --------------------------------------------------------

    if article.get(
        "market_relevant"
    ) is True:

        return True

    # --------------------------------------------------------
    # 兼容独立调用
    # --------------------------------------------------------

    for term in MARKET_IMPACT_TERMS:

        if contains_term(
            text,
            term
        ):

            return True

    return False


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
# 事件分类
#
# 核心原则：
#
# “事件本身是什么”
#
# 而不是：
#
# “标题里出现了什么关键词”
#
# ============================================================

def classify_event(article):

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
    # 第一优先级：宏观经济 / 央行政策
    # ========================================================

    macro_patterns = [

        "federal reserve",
        "fed chair",
        "fomc",
        "interest rate",
        "rate cut",
        "rate hike",
        "inflation",
        "cpi",
        "ppi",
        "payroll",
        "unemployment",
        "central bank",

    ]

    for pattern in macro_patterns:

        if contains_term(
            text,
            pattern
        ):

            return CATEGORY_MACRO


    # ========================================================
    # 第二优先级：地缘政治 / 制裁
    #
    # 战争、军事冲突、制裁、关税、
    # 国际贸易冲突属于该事件本身。
    # ========================================================

    geopolitics_patterns = [

        "war",
        "conflict",
        "military",
        "missile",
        "attack",
        "strike",
        "ceasefire",
        "geopolitical",
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
    # 第三优先级：能源 / 大宗商品
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
    # 第四优先级：AI / 半导体
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
    # 第五优先级：外汇 / 债券
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
    # 第六优先级：公司重大事件
    # ========================================================

    company_patterns = [

        "earnings",
        "quarterly results",
        "revenue",
        "profit",
        "guidance",
        "acquisition",
        "merger",
        "takeover",
        "bankruptcy",
        "ipo",

    ]

    for pattern in company_patterns:

        if contains_term(
            text,
            pattern
        ):

            return CATEGORY_COMPANY


    # ========================================================
    # 第七优先级：全球股市
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


    # ========================================================
    # 其他市场事件
    # ========================================================

    return CATEGORY_OTHER


# ============================================================
# 影响范围评分
#
# 0 - 40
#
# 不是简单统计关键词数量。
#
# 根据事件涉及的市场范围进行判断。
# ============================================================

def score_impact_scope(article):

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


    # --------------------------------------------------------
    # 全球金融体系 / 全球主要市场
    # --------------------------------------------------------

    global_patterns = [

        "federal reserve",
        "fed",
        "fomc",
        "global market",
        "global markets",
        "world economy",
        "global economy",
        "u.s. dollar",
        "treasury",

    ]

    for pattern in global_patterns:

        if contains_term(
            text,
            pattern
        ):

            return 40


    # --------------------------------------------------------
    # 多国 / 跨区域
    # --------------------------------------------------------

    multi_region_patterns = [

        "trade war",
        "tariff",
        "sanctions",
        "war",
        "iran",
        "russia",
        "ukraine",
        "middle east",
        "u.s.-canada",
        "us-canada",

    ]

    for pattern in multi_region_patterns:

        if contains_term(
            text,
            pattern
        ):

            return 35


    # --------------------------------------------------------
    # 单一国家 / 主要行业
    # --------------------------------------------------------

    industry_patterns = [

        "semiconductor",
        "chip",
        "nvidia",
        "broadcom",
        "oil",
        "crude",
        "gold",
        "ipo",
        "earnings",

    ]

    for pattern in industry_patterns:

        if contains_term(
            text,
            pattern
        ):

            return 28


    # --------------------------------------------------------
    # 单一公司 / 单一资产
    # --------------------------------------------------------

    return 10


# ============================================================
# 影响程度评分
#
# 0 - 40
#
# 衡量：
#
# 事件对市场可能造成多大程度的重新定价。
# ============================================================

def score_impact_degree(article):

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


    # --------------------------------------------------------
    # 极高影响
    # --------------------------------------------------------

    very_high_patterns = [

        "rate hike",
        "rate cut",
        "war",
        "armed conflict",
        "exchange strikes",
        "sanctions",
        "trade war",
        "market crash",

    ]

    for pattern in very_high_patterns:

        if contains_term(
            text,
            pattern
        ):

            return 40


    # --------------------------------------------------------
    # 高影响
    # --------------------------------------------------------

    high_patterns = [

        "tariff",
        "tariffs",
        "inflation",
        "fomc",
        "federal reserve",
        "oil",
        "crude",
        "missile",
        "military strike",
        "earnings",

    ]

    for pattern in high_patterns:

        if contains_term(
            text,
            pattern
        ):

            return 34


    # --------------------------------------------------------
    # 中等影响
    # --------------------------------------------------------

    medium_patterns = [

        "ipo",
        "acquisition",
        "merger",
        "profit",
        "revenue",
        "semiconductor",
        "nvidia",
        "broadcom",
        "stocks",
        "equities",

    ]

    for pattern in medium_patterns:

        if contains_term(
            text,
            pattern
        ):

            return 28


    # --------------------------------------------------------
    # 普通市场信息
    # --------------------------------------------------------

    return 10


# ============================================================
# 单条新闻评分
# ============================================================

def score_article(article):

    article = dict(article)

    scope = score_impact_scope(
        article
    )

    degree = score_impact_degree(
        article
    )

    credibility = get_source_credibility(
        article
    )

    total_score = (
        scope
        + degree
        + credibility
    )

    article[
        "impact_scope"
    ] = scope

    article[
        "impact_degree"
    ] = degree

    article[
        "source_credibility"
    ] = credibility

    article[
        "score"
    ] = total_score

    return article


# ============================================================
# 同一事件识别
#
# 目的：
#
# CNBC / BBC / Reuters
# 同时报道同一事件时，
# 不重复占用展示数量。
#
# 注意：
# 这是事件去重，不是简单标题去重。
# ============================================================

def build_event_key(article):

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


    # --------------------------------------------------------
    # 事件级关键词
    # --------------------------------------------------------

    event_groups = {

        "fed_policy":
            [
                "federal reserve",
                "fed chair",
                "fomc",
                "rate hike",
                "rate cut",
            ],

        "iran_conflict":
            [
                "iran",
                "hormuz",
                "larak",
                "kharg",
            ],

        "russia_ukraine":
            [
                "russia",
                "ukraine",
            ],

        "us_canada_trade":
            [
                "u.s.-canada",
                "us-canada",
                "canada",
                "trade war",
                "tariff",
            ],

        "venezuela_oil":
            [
                "venezuela",
                "65 billion barrels",
            ],

        "jio_ipo":
            [
                "jio platforms",
                "jio",
                "ipo",
            ],

        "byd_earnings":
            [
                "byd",
                "earnings",
                "first-half",
            ],

    }


    for event_id, patterns in event_groups.items():

        matched = 0

        for pattern in patterns:

            if contains_term(
                text,
                pattern
            ):

                matched += 1

        # 关键事件至少命中2个特征
        if matched >= 2:

            return event_id


    # --------------------------------------------------------
    # 通用标题归一化
    # --------------------------------------------------------

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

    }

    words = [
        word
        for word in words
        if word not in stop_words
    ]

    if words:

        return " ".join(
            words[:8]
        )

    return title


# ============================================================
# 同一事件合并
#
# 保留：
# 1. 评分最高的报道作为主新闻
# 2. 其他报道作为交叉验证来源
#
# 不编造任何内容。
# ============================================================

def merge_same_events(articles):

    groups = defaultdict(list)

    for article in articles:

        event_id = build_event_key(
            article
        )

        groups[event_id].append(
            article
        )


    merged = []


    for event_id, group in groups.items():

        # ----------------------------------------------------
        # 按总分排序
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

        primary[
            "event_id"
        ] = event_id


        # ----------------------------------------------------
        # 交叉验证来源
        # ----------------------------------------------------

        related_sources = []

        for item in group:

            source = item.get(
                "source"
            )

            if (
                source
                and source
                not in related_sources
            ):

                related_sources.append(
                    source
                )


        primary[
            "related_sources"
        ] = related_sources


        # ----------------------------------------------------
        # 保留原始报道数量
        # ----------------------------------------------------

        primary[
            "related_article_count"
        ] = len(
            group
        )


        merged.append(
            primary
        )


    return merged


# ============================================================
# 低权重分类 Top10
#
# 只有 <=40 分的新闻进入这里。
#
# 高权重新闻完全不受 Top10 限制。
# ============================================================

def limit_low_score_by_category(
    articles,
    limit=10
):

    high_score = []
    low_score = []

    for article in articles:

        if article.get(
            "score",
            0
        ) > 40:

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
    # 低权重分类
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
# 结果重新按照分类组织
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


    # 每个分类内部：
    # 高分优先
    # 同分按发布时间倒序

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
# news_data.py 正是调用这里：
#
#     select_news(raw_news)
#
# ============================================================

def select_news(raw_news):

    if not raw_news:

        return {
            category: []
            for category in ALL_CATEGORIES
        }


    # ========================================================
    # 第一步：金融市场实际影响力筛选
    # ========================================================

    candidates = []

    for article in raw_news:

        if not is_market_impactful(
            article
        ):

            continue

        # 必须有真实来源
        if not article.get(
            "source"
        ):

            continue

        # 必须有原文链接
        if not article.get(
            "url"
        ):

            continue

        candidates.append(
            article
        )


    # ========================================================
    # 第二步：按事件本身分类
    # ========================================================

    classified = []

    for article in candidates:

        article = dict(
            article
        )

        article[
            "category"
        ] = classify_event(
            article
        )

        classified.append(
            article
        )


    # ========================================================
    # 第三步：评分
    #
    # 影响范围 40
    # 影响程度 40
    # 来源可信度 20
    # ========================================================

    scored = []

    for article in classified:

        article = score_article(
            article
        )

        scored.append(
            article
        )


    # ========================================================
    # 第四步：同一事件去重 / 合并
    # ========================================================

    merged = merge_same_events(
        scored
    )


    # ========================================================
    # 第五步：
    #
    # >40：
    #     全部保留
    #
    # <=40：
    #     每个分类最多10条
    # ========================================================

    selected = limit_low_score_by_category(
        merged,
        limit=10
    )


    # ========================================================
    # 第六步：重新按照分类组织
    # ========================================================

    result = group_by_category(
        selected
    )


    # ========================================================
    # 第七步：
    # 分类内部最终排序
    # ========================================================

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
# 兼容接口
#
# 某些旧代码可能调用 fetch_news。
# 保留这个接口，避免旧代码再次报错。
#
# ============================================================

def fetch_news(raw_news=None):

    if raw_news is None:

        return []

    return select_news(
        raw_news
    )


# ============================================================
# 单独测试
# ============================================================

if __name__ == "__main__":

    test_news = [

        {
            "title":
                "Fed signals higher rates",

            "summary":
                "Federal Reserve officials indicate tighter policy",

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
                "BYD shares fall after earnings",

            "summary":
                "BYD reports first-half results",

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
        "\n========== 新闻评分测试 ==========\n"
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
