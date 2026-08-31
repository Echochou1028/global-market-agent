import re
from collections import defaultdict


# ============================================================
# 全球金融市场日报
# 新闻评分、分类、事件合并模块
#
# 核心规则
#
# 1. 只保留对金融市场具有实际影响力的信息
#
# 2. 分类按照“事件本身是什么”
#    而不是按照关键词命中决定
#
# 3. 评分：
#       影响范围     40分
#       影响程度     40分
#       来源可信度   20分
#       总分         100分
#
# 4. 总分 > 40：
#       全部保留，不受数量限制
#
# 5. 总分 <= 40：
#       按分类分别执行 Top10
#
# 6. 每个低权重分类最多10条
#
# 7. 不足10条：
#       有几条展示几条
#       不强行补足
#
# 8. 同一事件：
#       去重、合并
#       不重复占用展示数量
#
# 9. 来源定位：
#       官方源      → 事实确认
#       权威媒体    → 事件发现、背景、交叉验证
#       金融机构    → 权威研究
#       知名个人    → 扩展接口
#
# 10. 来源不决定重要性
#     来源只影响20分的可信度
#
# ============================================================


# ============================================================
# 分类定义
# ============================================================

CATEGORIES = [

    "宏观经济与央行政策",
    "AI与半导体",
    "全球股市",
    "能源与大宗商品",
    "外汇与债券",
    "地缘政治与制裁",
    "公司重大事件",
    "其他市场事件",

]


# ============================================================
# 来源可信度
#
# 注意：
# 来源可信度只能影响20分。
#
# 不能因为来源权威，
# 就直接把新闻判断成高影响事件。
# ============================================================

SOURCE_CREDIBILITY = {

    # --------------------------------------------------------
    # 官方 / 一手来源
    # --------------------------------------------------------

    "Federal Reserve": 20,
    "U.S. Federal Reserve": 20,
    "Federal Reserve Board": 20,

    "ECB": 20,
    "European Central Bank": 20,

    "Bank of Japan": 20,
    "BOJ": 20,

    "Bank of England": 20,
    "BOE": 20,

    "U.S. Treasury": 20,
    "U.S. Department of Treasury": 20,

    "White House": 20,

    "OPEC": 20,

    # --------------------------------------------------------
    # 权威国际媒体
    # --------------------------------------------------------

    "Reuters": 19,
    "Bloomberg": 19,
    "Financial Times": 19,
    "The Wall Street Journal": 19,

    "CNBC Markets": 18,
    "CNBC Finance": 18,
    "CNBC World News": 17,
    "CNBC Top News": 17,

    "BBC Business": 17,
    "BBC News": 17,

    # --------------------------------------------------------
    # 国际金融机构
    # --------------------------------------------------------

    "IMF": 20,
    "International Monetary Fund": 20,

    "World Bank": 20,

    "BIS": 20,
    "Bank for International Settlements": 20,

}


DEFAULT_SOURCE_CREDIBILITY = 15


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
        r"[^a-z0-9\u4e00-\u9fff\s]",
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
# 来源可信度
# ============================================================

def get_source_credibility(article):

    source = (
        article.get("source")
        or ""
    ).strip()

    if source in SOURCE_CREDIBILITY:

        return SOURCE_CREDIBILITY[source]

    source_lower = source.lower()

    # 权威媒体模糊匹配
    if "reuters" in source_lower:
        return 19

    if "bloomberg" in source_lower:
        return 19

    if "financial times" in source_lower:
        return 19

    if "wall street journal" in source_lower:
        return 19

    if "cnbc" in source_lower:

        if "markets" in source_lower:
            return 18

        if "finance" in source_lower:
            return 18

        return 17

    if "bbc" in source_lower:
        return 17

    if "federal reserve" in source_lower:
        return 20

    if "treasury" in source_lower:
        return 20

    if "ecb" in source_lower:
        return 20

    if "bank of japan" in source_lower:
        return 20

    if "opec" in source_lower:
        return 20

    if "imf" in source_lower:
        return 20

    if "world bank" in source_lower:
        return 20

    if "bis" in source_lower:
        return 20

    return DEFAULT_SOURCE_CREDIBILITY


# ============================================================
# 市场影响关键词
#
# 注意：
# 这些词只用于“判断事件是否可能属于金融市场事件”
#
# 不用于：
#   - 影响范围评分
#   - 影响程度评分
#   - 分类最终决定
# ============================================================

MARKET_SIGNAL_GROUPS = {

    "macro": [
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
        "monetary policy",
        "policy rate",
    ],

    "equity": [
        "stock",
        "stocks",
        "shares",
        "equity",
        "equities",
        "nasdaq",
        "s&p 500",
        "dow jones",
        "nikkei",
        "kospi",
        "hang seng",
        "vix",
        "selloff",
        "sell-off",
        "rally",
        "market",
    ],

    "ai_semiconductor": [
        "nvidia",
        "amd",
        "broadcom",
        "intel",
        "tsmc",
        "asml",
        "semiconductor",
        "chip",
        "chips",
        "gpu",
        "hbm",
        "artificial intelligence",
        "ai",
        "data center",
        "data centre",
        "foundry",
        "optical networking",
    ],

    "company": [
        "earnings",
        "quarterly results",
        "revenue",
        "profit",
        "loss",
        "guidance",
        "forecast",
        "acquisition",
        "merger",
        "takeover",
        "bankruptcy",
        "ipo",
        "ceo",
        "chief executive",
        "regulatory approval",
    ],

    "energy": [
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

    "fx_bond": [
        "dollar",
        "yen",
        "yuan",
        "euro",
        "forex",
        "currency",
        "treasury",
        "bond",
        "bonds",
        "yield",
        "yields",
    ],

    "geopolitical": [
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
        "tariff",
        "tariffs",
        "trade war",
        "export controls",
        "iran",
        "israel",
        "russia",
        "ukraine",
        "taiwan",
        "middle east",
        "hormuz",
    ],

}


# ============================================================
# 明显非金融市场内容
# ============================================================

NON_MARKET_SIGNALS = [

    "celebrity",
    "entertainment",
    "movie",
    "music",
    "sports",
    "travel",
    "food",
    "restaurant",
    "lifestyle",
    "recipe",
    "fashion",

]


# ============================================================
# 判断文本是否包含信号
# ============================================================

def contains_signal(text, signal):

    text = normalize_text(text)
    signal = normalize_text(signal)

    if not text or not signal:
        return False

    return signal in text


# ============================================================
# 判断新闻是否具有金融市场相关性
#
# 这里是“市场影响力初筛”，
# 不是最终评分。
# ============================================================

def is_financial_market_event(article):

    title = article.get("title", "")
    summary = article.get("summary", "")

    text = normalize_text(
        f"{title} {summary}"
    )

    if not text:
        return False

    # 明显非金融新闻
    for signal in NON_MARKET_SIGNALS:

        if contains_signal(
            text,
            signal
        ):

            return False

    # 至少具备一个市场相关信号
    for group in MARKET_SIGNAL_GROUPS.values():

        for signal in group:

            if contains_signal(
                text,
                signal
            ):

                return True

    return False


# ============================================================
# 事件关键词
#
# 仅用于“事件相似度”
# 不用于重要性评分
# ============================================================

EVENT_STOP_WORDS = {

    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "as",
    "is",
    "are",
    "was",
    "were",
    "this",
    "that",
    "from",
    "after",
    "before",
    "says",
    "said",
    "how",
    "why",
    "what",
    "new",
    "latest",
    "here",
    "top",
}


def event_tokens(article):

    text = normalize_text(
        f"{article.get('title', '')} "
        f"{article.get('summary', '')}"
    )

    tokens = text.split()

    result = set()

    for token in tokens:

        if len(token) < 3:
            continue

        if token in EVENT_STOP_WORDS:
            continue

        result.add(token)

    return result


# ============================================================
# 事件相似度
#
# 采用：
#   标题 + 核心事实
#   关键词交集比例
#
# 这里只用于发现重复事件。
# ============================================================

def event_similarity(article_a, article_b):

    tokens_a = event_tokens(article_a)
    tokens_b = event_tokens(article_b)

    if not tokens_a or not tokens_b:
        return 0

    intersection = (
        tokens_a & tokens_b
    )

    union = (
        tokens_a | tokens_b
    )

    if not union:
        return 0

    jaccard = (
        len(intersection)
        / len(union)
    )

    return jaccard


# ============================================================
# 核心事件关键词
#
# 用于避免明显不同事件被错误合并。
# ============================================================

EVENT_ANCHORS = [

    "iran",
    "israel",
    "russia",
    "ukraine",
    "taiwan",

    "fed",
    "federal reserve",

    "nvidia",
    "amd",
    "broadcom",
    "tsmc",
    "asml",

    "byd",
    "jio",
    "hdfc",

    "venezuela",
    "canada",
    "mexico",

    "oil",
    "hormuz",

]


def shared_anchor(article_a, article_b):

    text_a = normalize_text(
        f"{article_a.get('title', '')} "
        f"{article_a.get('summary', '')}"
    )

    text_b = normalize_text(
        f"{article_b.get('title', '')} "
        f"{article_b.get('summary', '')}"
    )

    for anchor in EVENT_ANCHORS:

        if (
            contains_signal(text_a, anchor)
            and
            contains_signal(text_b, anchor)
        ):

            return True

    return False


# ============================================================
# 判断是否属于同一事件
# ============================================================

def is_same_event(article_a, article_b):

    # 已经明确 event_id
    event_a = article_a.get("event_id")
    event_b = article_b.get("event_id")

    if event_a and event_b:

        return event_a == event_b

    similarity = event_similarity(
        article_a,
        article_b
    )

    # 高相似度直接合并
    if similarity >= 0.55:
        return True

    # 有共同核心事件锚点时，
    # 使用稍低的相似度阈值。
    if (
        shared_anchor(
            article_a,
            article_b
        )
        and similarity >= 0.28
    ):

        return True

    return False


# ============================================================
# 同一事件合并
#
# 保留信息最完整的一条作为主记录。
#
# 不虚构新事实。
# ============================================================

def merge_event_articles(articles):

    if not articles:
        return []

    # 按发布时间倒序
    articles = sorted(
        articles,
        key=lambda x: x.get(
            "published_at"
        ) or "",
        reverse=True
    )

    groups = []

    for article in articles:

        matched_group = None

        for group in groups:

            if is_same_event(
                article,
                group[0]
            ):

                matched_group = group
                break

        if matched_group is None:

            groups.append(
                [article]
            )

        else:

            matched_group.append(
                article
            )

    merged = []

    for group in groups:

        # 主新闻：
        # 优先选择可信度高、
        # 信息完整、
        # 时间较新的记录
        group_sorted = sorted(
            group,
            key=lambda x: (
                get_source_credibility(x),
                len(
                    x.get(
                        "summary",
                        ""
                    )
                ),
                x.get(
                    "published_at"
                ) or "",
            ),
            reverse=True
        )

        primary = dict(
            group_sorted[0]
        )

        # 保留所有真实来源
        sources = []

        for item in group:

            source = item.get(
                "source"
            )

            url = item.get(
                "url"
            )

            if source and url:

                source_item = {
                    "source": source,
                    "url": url,
                }

                if source_item not in sources:

                    sources.append(
                        source_item
                    )

        primary["sources"] = sources

        # 兼容旧字段
        primary["source"] = (
            primary.get("source")
            or "未知"
        )

        primary["url"] = (
            primary.get("url")
            or ""
        )

        # 标记合并数量
        primary["merged_count"] = len(
            group
        )

        merged.append(
            primary
        )

    return merged


# ============================================================
# 事件分类
#
# 这里必须遵循：
#
# “事件本身是什么”
#
# 分类优先级不是关键词数量。
#
# 使用事件主题的结构化判断。
# ============================================================

def classify_event(article):

    title = normalize_text(
        article.get("title", "")
    )

    summary = normalize_text(
        article.get("summary", "")
    )

    text = (
        f"{title} {summary}"
    )

    # --------------------------------------------------------
    # 1. 宏观 / 央行
    #
    # 只有当核心事件本身是：
    #   利率
    #   货币政策
    #   通胀
    #   就业
    #   GDP
    #   央行政策
    # 才归入此类。
    # --------------------------------------------------------

    macro_strong = [

        "interest rate",
        "rate cut",
        "rate hike",
        "policy rate",
        "monetary policy",
        "fomc",
        "fed decision",
        "fed meeting",
        "inflation data",
        "cpi report",
        "ppi report",
        "jobs report",
        "payroll report",
        "unemployment rate",
        "gdp growth",
        "central bank decision",

    ]

    if any(
        contains_signal(text, x)
        for x in macro_strong
    ):

        return "宏观经济与央行政策"

    # --------------------------------------------------------
    # 2. AI / 半导体
    #
    # 核心事件本身必须与：
    #   AI产业
    #   芯片
    #   半导体
    #   GPU
    #   HBM
    #   晶圆代工
    #   数据中心
    # 有直接关系。
    # --------------------------------------------------------

    ai_strong = [

        "artificial intelligence",
        "ai chip",
        "ai model",
        "semiconductor",
        "semiconductors",
        "gpu",
        "hbm",
        "foundry",
        "data center",
        "data centre",
        "optical networking",
        "nvidia",
        "amd",
        "broadcom",
        "tsmc",
        "asml",

    ]

    if any(
        contains_signal(text, x)
        for x in ai_strong
    ):

        # 如果新闻明确是公司业绩、
        # CEO任命等纯公司事件，
        # 则仍归公司重大事件。
        company_event_signals = [

            "earnings",
            "quarterly results",
            "ceo",
            "chief executive",
            "acquisition",
            "merger",
            "takeover",
            "bankruptcy",

        ]

        if any(
            contains_signal(
                text,
                x
            )
            for x in company_event_signals
        ):

            # 若核心对象明显是AI/半导体企业，
            # 且事件是产业层面的影响，
            # AI分类优先。
            if any(
                contains_signal(
                    text,
                    x
                )
                for x in [
                    "semiconductor",
                    "ai chip",
                    "hbm",
                    "gpu",
                    "data center",
                    "foundry",
                ]
            ):

                return "AI与半导体"

        else:

            return "AI与半导体"

    # --------------------------------------------------------
    # 3. 能源 / 大宗商品
    #
    # 事件本身是：
    #   原油
    #   OPEC
    #   黄金
    #   铜
    #   天然气
    #   大宗商品供给
    # 等。
    # --------------------------------------------------------

    energy_strong = [

        "oil",
        "crude",
        "brent",
        "wti",
        "opec",
        "oil production",
        "oil supply",
        "oil reserves",
        "natural gas",
        "gold price",
        "silver price",
        "copper price",
        "commodity prices",

    ]

    if any(
        contains_signal(text, x)
        for x in energy_strong
    ):

        return "能源与大宗商品"

    # --------------------------------------------------------
    # 4. 外汇 / 债券
    #
    # 核心事件是：
    #   汇率
    #   美元
    #   日元
    #   人民币
    #   国债
    #   收益率
    # --------------------------------------------------------

    fx_bond_strong = [

        "forex",
        "currency market",
        "dollar index",
        "dollar rises",
        "dollar falls",
        "yen rises",
        "yen falls",
        "yuan",
        "treasury yield",
        "treasury yields",
        "bond yields",
        "bond market",
        "government bonds",

    ]

    if any(
        contains_signal(text, x)
        for x in fx_bond_strong
    ):

        return "外汇与债券"

    # --------------------------------------------------------
    # 5. 地缘政治 / 制裁
    #
    # 核心事件本身是：
    #   战争
    #   冲突
    #   制裁
    #   关税
    #   贸易战
    #   军事行动
    #   地缘风险
    #
    # 即使同时出现 oil，
    # 如果核心事件是战争/制裁，
    # 仍然归地缘政治。
    # --------------------------------------------------------

    geopolitical_strong = [

        "war",
        "armed conflict",
        "military strike",
        "military strikes",
        "air strike",
        "airstrikes",
        "missile attack",
        "sanctions",
        "sanction",
        "trade war",
        "tariff war",
        "export controls",
        "geopolitical",
        "ceasefire",
        "iran",
        "israel",
        "russia",
        "ukraine",
        "taiwan",

    ]

    if any(
        contains_signal(text, x)
        for x in geopolitical_strong
    ):

        return "地缘政治与制裁"

    # --------------------------------------------------------
    # 6. 公司重大事件
    #
    # 核心事件：
    #   财报
    #   IPO
    #   并购
    #   CEO变化
    #   监管批准
    #   公司重大经营变化
    # --------------------------------------------------------

    company_strong = [

        "earnings",
        "quarterly results",
        "financial results",
        "revenue",
        "profit",
        "loss",
        "guidance",
        "forecast",
        "acquisition",
        "merger",
        "takeover",
        "bankruptcy",
        "ipo",
        "chief executive",
        "ceo",
        "regulatory approval",
        "regulatory nod",
        "regulatory clearance",

    ]

    if any(
        contains_signal(text, x)
        for x in company_strong
    ):

        return "公司重大事件"

    # --------------------------------------------------------
    # 7. 全球股市
    #
    # 事件本身是：
    #   指数
    #   市场整体上涨/下跌
    #   股市风险偏好
    #   大规模市场波动
    # --------------------------------------------------------

    equity_strong = [

        "stock market",
        "stock markets",
        "equity market",
        "equity markets",
        "market rally",
        "market selloff",
        "market sell-off",
        "market crash",
        "stocks rise",
        "stocks fall",
        "shares rise",
        "shares fall",
        "nasdaq",
        "s&p 500",
        "dow jones",
        "nikkei",
        "kospi",
        "hang seng",

    ]

    if any(
        contains_signal(text, x)
        for x in equity_strong
    ):

        return "全球股市"

    # --------------------------------------------------------
    # 8. 其他市场事件
    # --------------------------------------------------------

    return "其他市场事件"


# ============================================================
# 影响范围评分
#
# 40分
#
# 这里不是关键词数量评分。
#
# 根据事件影响的市场覆盖范围判断。
# ============================================================

def score_impact_scope(article):

    category = article.get(
        "category"
    )

    title = normalize_text(
        article.get("title", "")
    )

    summary = normalize_text(
        article.get("summary", "")
    )

    text = (
        f"{title} {summary}"
    )

    # --------------------------------------------------------
    # 全球系统性事件
    # --------------------------------------------------------

    global_events = [

        "federal reserve",
        "fed",
        "fomc",
        "interest rate",
        "monetary policy",
        "global trade",
        "trade war",
        "war",
        "armed conflict",
        "iran",
        "russia",
        "ukraine",
        "oil supply",
        "oil reserves",
        "opec",
        "treasury",

    ]

    if any(
        contains_signal(text, x)
        for x in global_events
    ):

        return 40

    # --------------------------------------------------------
    # 跨区域 / 重要国家
    # --------------------------------------------------------

    cross_region = [

        "united states",
        "u.s.",
        "china",
        "europe",
        "european",
        "japan",
        "india",
        "canada",
        "middle east",
        "asia",

    ]

    region_hit = sum(
        1
        for x in cross_region
        if contains_signal(text, x)
    )

    if region_hit >= 2:

        return 35

    if region_hit == 1:

        return 28

    # --------------------------------------------------------
    # 行业级事件
    # --------------------------------------------------------

    if category in [
        "AI与半导体",
        "能源与大宗商品",
    ]:

        return 24

    # --------------------------------------------------------
    # 单公司 / 单市场
    # --------------------------------------------------------

    if category == "公司重大事件":

        return 22

    if category == "全球股市":

        return 22

    if category == "外汇与债券":

        return 24

    if category == "地缘政治与制裁":

        return 25

    return 10


# ============================================================
# 影响程度评分
#
# 40分
#
# 判断事件本身已经产生或可能产生的市场冲击。
# ============================================================

def score_impact_degree(article):

    title = normalize_text(
        article.get("title", "")
    )

    summary = normalize_text(
        article.get("summary", "")
    )

    text = (
        f"{title} {summary}"
    )

    # --------------------------------------------------------
    # 已经发生实际市场冲击
    # --------------------------------------------------------

    strong_market_effect = [

        "shares slide",
        "shares plunged",
        "shares plunge",
        "stocks plunged",
        "stocks plunge",
        "market crash",
        "market selloff",
        "market sell-off",
        "markets tumble",
        "markets sank",
        "markets surged",
        "stocks surge",
        "shares surge",
        "oil prices spike",
        "oil prices surge",
        "oil prices plunge",
        "yields spike",
        "dollar surges",
        "dollar plunges",

    ]

    if any(
        contains_signal(text, x)
        for x in strong_market_effect
    ):

        return 40

    # --------------------------------------------------------
    # 政策/战争/制裁等重大冲击
    # --------------------------------------------------------

    severe_events = [

        "armed conflict",
        "military strike",
        "military strikes",
        "airstrike",
        "missile attack",
        "new sanctions",
        "trade war",
        "tariff war",
        "fed rate decision",
        "rate hike",
        "rate cut",

    ]

    if any(
        contains_signal(text, x)
        for x in severe_events
    ):

        return 36

    # --------------------------------------------------------
    # 明显市场影响
    # --------------------------------------------------------

    medium_events = [

        "earnings",
        "quarterly results",
        "ipo",
        "regulatory approval",
        "regulatory nod",
        "ceo",
        "guidance",
        "forecast",
        "oil reserves",
        "oil supply",
        "semiconductor",

    ]

    if any(
        contains_signal(text, x)
        for x in medium_events
    ):

        return 30

    # --------------------------------------------------------
    # 一般市场影响
    # --------------------------------------------------------

    if article.get(
        "category"
    ) in [
        "全球股市",
        "AI与半导体",
        "能源与大宗商品",
        "外汇与债券",
    ]:

        return 20

    if article.get(
        "category"
    ) == "公司重大事件":

        return 18

    if article.get(
        "category"
    ) == "地缘政治与制裁":

        return 15

    return 10


# ============================================================
# 总评分
# ============================================================

def calculate_score(article):

    scope = score_impact_scope(
        article
    )

    degree = score_impact_degree(
        article
    )

    credibility = get_source_credibility(
        article
    )

    # 限制边界
    scope = max(
        0,
        min(40, scope)
    )

    degree = max(
        0,
        min(40, degree)
    )

    credibility = max(
        0,
        min(20, credibility)
    )

    total = (
        scope
        + degree
        + credibility
    )

    article["impact_scope"] = scope

    article["impact_degree"] = degree

    article["source_credibility"] = credibility

    article["score"] = total

    return article


# ============================================================
# 新闻排序
# ============================================================

def sort_news(news_list):

    return sorted(
        news_list,
        key=lambda x: (
            x.get("score", 0),
            x.get("impact_scope", 0),
            x.get("impact_degree", 0),
            x.get("published_at") or "",
        ),
        reverse=True
    )


# ============================================================
# 高权重新闻
#
# >40
#
# 全部保留。
# 不受数量限制。
# ============================================================

def select_high_weight_news(news_list):

    return [
        article
        for article in news_list
        if article.get(
            "score",
            0
        ) > 40
    ]


# ============================================================
# 低权重新闻
#
# <=40
#
# 按分类 Top10
# ============================================================

def select_low_weight_news(news_list):

    category_news = defaultdict(
        list
    )

    for article in news_list:

        score = article.get(
            "score",
            0
        )

        if score <= 40:

            category = article.get(
                "category"
            ) or "其他市场事件"

            category_news[
                category
            ].append(
                article
            )

    result = []

    for category, items in category_news.items():

        items = sort_news(
            items
        )

        # 每个分类最多10条
        selected = items[:10]

        result.extend(
            selected
        )

    return result


# ============================================================
# 最终新闻选择
#
# 规则：
#
# >40
#     全部保留
#
# <=40
#     分类Top10
#
# ============================================================

def select_news(raw_news):

    if not raw_news:

        return {
            category: []
            for category in CATEGORIES
        }


    # ========================================================
    # 第一步：市场影响力初筛
    # ========================================================

    market_news = []

    for article in raw_news:

        if not is_financial_market_event(
            article
        ):

            continue

        market_news.append(
            dict(article)
        )


    # ========================================================
    # 第二步：同一事件去重 / 合并
    # ========================================================

    merged_news = merge_event_articles(
        market_news
    )


    # ========================================================
    # 第三步：事件分类
    # ========================================================

    classified_news = []

    for article in merged_news:

        category = classify_event(
            article
        )

        article["category"] = category

        classified_news.append(
            article
        )


    # ========================================================
    # 第四步：评分
    # ========================================================

    scored_news = []

    for article in classified_news:

        calculate_score(
            article
        )

        scored_news.append(
            article
        )


    # ========================================================
    # 第五步：
    #
    # >40 全部保留
    # ========================================================

    high_weight = select_high_weight_news(
        scored_news
    )


    # ========================================================
    # 第六步：
    #
    # <=40 分类 Top10
    # ========================================================

    low_weight = select_low_weight_news(
        scored_news
    )


    # ========================================================
    # 第七步：合并
    # ========================================================

    final_news = (
        high_weight
        + low_weight
    )


    # ========================================================
    # 最终排序
    # ========================================================

    final_news = sort_news(
        final_news
    )


    # ========================================================
    # 最终按分类整理
    # ========================================================

    result = {
        category: []
        for category in CATEGORIES
    }


    for article in final_news:

        category = article.get(
            "category"
        )

        if category not in result:

            category = "其他市场事件"

            article["category"] = category

        result[
            category
        ].append(
            article
        )


    # ========================================================
    # 输出统计
    # ========================================================

    print(
        "\n============================================================"
    )

    print(
        f"市场相关候选新闻："
        f"{len(market_news)}"
    )

    print(
        f"同一事件合并后："
        f"{len(merged_news)}"
    )

    print(
        f"高权重新闻（>40）："
        f"{len(high_weight)}"
    )

    print(
        f"低权重新闻（<=40）："
        f"{len(low_weight)}"
    )

    print(
        f"最终新闻数量："
        f"{len(final_news)}"
    )

    print(
        "============================================================"
    )


    return result
