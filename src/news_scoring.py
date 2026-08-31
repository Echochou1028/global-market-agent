from datetime import datetime, timezone
from typing import Any, Dict, List


# ============================================================
# Global Market Agent
# 新闻评分与筛选核心 V2.1
# ============================================================

HIGH_WEIGHT_THRESHOLD = 40
LOW_WEIGHT_MAX_PER_CATEGORY = 10


# ============================================================
# 新闻分类
# ============================================================

VALID_CATEGORIES = [
    "宏观经济与央行政策",
    "AI与半导体",
    "全球金融市场",
    "能源与大宗商品",
    "公司重大事件",
    "地缘政治与制裁",
    "外汇",
    "债券与利率",
    "贵金属",
    "其他市场事件",
]


# ============================================================
# 来源可信度
# ============================================================

SOURCE_CREDIBILITY_SCORE = {

    # 官方 / 一手机构
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

    # 权威媒体
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

    # 国际金融机构
    "IMF": 19,
    "BIS": 19,
    "World Bank": 19,
}


SOURCE_TYPE_SCORE = {
    "official": 20,
    "financial_institution": 19,
    "major_media": 18,
    "expert": 12,
    "other_verified": 8,
}


# ============================================================
# 文本工具
# ============================================================

def clean_text(text: Any) -> str:

    if not text:
        return ""

    return str(text).lower().strip()


def contains_any(
    text: str,
    phrases: List[str]
) -> bool:

    return any(
        phrase in text
        for phrase in phrases
    )


# ============================================================
# 来源可信度
# ============================================================

def get_source_credibility(
    article: Dict[str, Any]
) -> int:

    source = article.get(
        "source",
        ""
    )

    if source in SOURCE_CREDIBILITY_SCORE:

        return SOURCE_CREDIBILITY_SCORE[source]

    source_type = article.get(
        "source_type",
        "other_verified"
    )

    return SOURCE_TYPE_SCORE.get(
        source_type,
        8
    )


# ============================================================
# 事件识别
# ============================================================
#
# 重要：
#
# 这里不是统计关键词数量。
#
# 而是按照“事件本身是什么”判断。
#
# 优先级非常重要：
#
# 1. 货币政策
# 2. 宏观数据
# 3. 地缘
# 4. 贸易 / 制裁
# 5. 能源
# 6. 公司
# 7. AI / 半导体
# 8. 市场价格
# 9. 外汇
# 10. 债券
#
# ============================================================

def identify_event_type(
    article: Dict[str, Any]
) -> str:

    title = clean_text(
        article.get("title", "")
    )

    summary = clean_text(
        article.get("summary", "")
    )

    text = f"{title} {summary}"


    # --------------------------------------------------------
    # 1. 货币政策
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "fed decision",
            "fed meeting",
            "fomc",
            "federal reserve",
            "fed chair",
            "interest rate decision",
            "rate decision",
            "rate cut",
            "rate hike",
            "interest rate",
            "monetary policy",
            "hawkish",
            "dovish",
        ]
    ):

        return "货币政策事件"


    # --------------------------------------------------------
    # 2. 宏观数据
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "consumer price index",
            "cpi",
            "ppi",
            "nonfarm payroll",
            "payrolls",
            "employment report",
            "unemployment rate",
            "jobs report",
            "gdp",
            "inflation data",
            "retail sales",
            "economic growth",
        ]
    ):

        return "重大宏观数据事件"


    # --------------------------------------------------------
    # 3. 地缘政治
    #
    # 这里要求真正存在军事 / 冲突事实。
    #
    # 单纯出现 war / conflict 不直接判定。
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "military attack",
            "missile attack",
            "airstrike",
            "air strikes",
            "missile strike",
            "military strike",
            "invasion",
            "armed conflict",
            "hostilities",
            "ceasefire",
            "troops",
            "military operation",
        ]
    ):

        return "重大地缘事件"


    # --------------------------------------------------------
    # 4. 制裁 / 贸易
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "sanctions",
            "sanction",
            "tariffs",
            "tariff",
            "trade war",
            "export controls",
            "export ban",
            "trade restrictions",
            "import restrictions",
        ]
    ):

        return "重大贸易或制裁事件"


    # --------------------------------------------------------
    # 5. 能源
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "opec",
            "oil production",
            "oil supply",
            "oil output",
            "crude production",
            "oil reserves",
            "oil reserve",
            "oil deal",
            "oil agreement",
            "oil market",
            "brent crude",
            "wti crude",
        ]
    ):

        return "重大能源事件"


    # --------------------------------------------------------
    # 6. 公司资本事件
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "acquisition",
            "acquires",
            "acquired",
            "merger",
            "takeover",
            "bankruptcy",
            "ipo",
            "initial public offering",
        ]
    ):

        return "重大公司资本事件"


    # --------------------------------------------------------
    # 7. 公司财报
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "earnings",
            "quarterly results",
            "quarterly earnings",
            "revenue",
            "profit",
            "guidance",
            "earnings outlook",
        ]
    ):

        return "重大公司财报事件"


    # --------------------------------------------------------
    # 8. AI / 半导体产业
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "nvidia",
            "broadcom",
            "amd",
            "tsmc",
            "asml",
            "semiconductor",
            "semiconductors",
            "ai chip",
            "artificial intelligence",
            "gpu",
            "hbm",
            "memory chip",
            "data center",
            "data centre",
            "optical networking",
        ]
    ):

        return "AI与半导体产业事件"


    # --------------------------------------------------------
    # 9. 市场剧烈波动
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "market crash",
            "market selloff",
            "market sell-off",
            "selloff",
            "sell-off",
            "market plunge",
            "market surge",
            "record high",
            "record low",
        ]
    ):

        return "重大市场价格变化"


    # --------------------------------------------------------
    # 10. 外汇
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "forex",
            "foreign exchange",
            "currency market",
            "dollar",
            "yen",
            "yuan",
            "exchange rate",
        ]
    ):

        return "外汇市场事件"


    # --------------------------------------------------------
    # 11. 债券
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "treasury yield",
            "bond yield",
            "bond market",
            "treasury market",
        ]
    ):

        return "债券市场事件"


    return "一般市场事件"


# ============================================================
# 分类
# ============================================================

def classify_news(
    article: Dict[str, Any]
) -> str:

    event_type = identify_event_type(
        article
    )


    mapping = {

        "货币政策事件":
            "宏观经济与央行政策",

        "重大宏观数据事件":
            "宏观经济与央行政策",

        "重大地缘事件":
            "地缘政治与制裁",

        "重大贸易或制裁事件":
            "地缘政治与制裁",

        "重大能源事件":
            "能源与大宗商品",

        "重大公司资本事件":
            "公司重大事件",

        "重大公司财报事件":
            "公司重大事件",

        "AI与半导体产业事件":
            "AI与半导体",

        "重大市场价格变化":
            "全球金融市场",

        "外汇市场事件":
            "外汇",

        "债券市场事件":
            "债券与利率",

    }


    return mapping.get(
        event_type,
        "其他市场事件"
    )


# ============================================================
# 影响范围
# ============================================================

def calculate_impact_scope(
    article: Dict[str, Any]
) -> int:

    supplied = article.get(
        "impact_scope"
    )

    if supplied is not None:

        return max(
            0,
            min(
                40,
                int(supplied)
            )
        )


    event_type = identify_event_type(
        article
    )


    # 全球货币政策
    if event_type == "货币政策事件":

        return 40


    # 全球重要宏观数据
    if event_type == "重大宏观数据事件":

        return 36


    # 重大军事冲突
    if event_type == "重大地缘事件":

        return 38


    # 贸易 / 制裁
    if event_type == "重大贸易或制裁事件":

        return 35


    # 全球能源事件
    if event_type == "重大能源事件":

        return 34


    # 大型资本事件
    if event_type == "重大公司资本事件":

        return 28


    # 重要财报
    if event_type == "重大公司财报事件":

        return 26


    # AI / 半导体
    if event_type == "AI与半导体产业事件":

        return 28


    # 市场价格变化
    if event_type == "重大市场价格变化":

        return 30


    # 外汇
    if event_type == "外汇市场事件":

        return 24


    # 债券
    if event_type == "债券市场事件":

        return 24


    return 10


# ============================================================
# 影响程度
# ============================================================

def calculate_impact_degree(
    article: Dict[str, Any]
) -> int:

    supplied = article.get(
        "impact_degree"
    )

    if supplied is not None:

        return max(
            0,
            min(
                40,
                int(supplied)
            )
        )


    event_type = identify_event_type(
        article
    )


    if event_type == "货币政策事件":

        return 40


    if event_type == "重大宏观数据事件":

        return 34


    if event_type == "重大地缘事件":

        return 38


    if event_type == "重大贸易或制裁事件":

        return 34


    if event_type == "重大能源事件":

        return 34


    if event_type == "重大公司资本事件":

        return 32


    if event_type == "重大公司财报事件":

        return 30


    if event_type == "AI与半导体产业事件":

        return 28


    if event_type == "重大市场价格变化":

        return 32


    if event_type == "外汇市场事件":

        return 22


    if event_type == "债券市场事件":

        return 22


    return 10


# ============================================================
# 评分
# ============================================================

def calculate_score(
    article: Dict[str, Any]
) -> int:

    scope = calculate_impact_scope(
        article
    )

    degree = calculate_impact_degree(
        article
    )

    credibility = get_source_credibility(
        article
    )


    return max(
        0,
        min(
            100,
            scope
            + degree
            + credibility
        )
    )


# ============================================================
# 标准化单条新闻
# ============================================================

def score_news(
    article: Dict[str, Any]
) -> Dict[str, Any]:

    result = dict(
        article
    )


    result["category"] = classify_news(
        result
    )


    result["event_type"] = identify_event_type(
        result
    )


    result["impact_scope"] = (
        calculate_impact_scope(
            result
        )
    )


    result["impact_degree"] = (
        calculate_impact_degree(
            result
        )
    )


    result["source_credibility"] = (
        get_source_credibility(
            result
        )
    )


    result["score"] = (
        result["impact_scope"]
        + result["impact_degree"]
        + result["source_credibility"]
    )


    return result


# ============================================================
# 事件指纹
# ============================================================
#
# 用于跨媒体识别“同一个事件”。
#
# 当前阶段采用：
#
#     事件类型
#     +
#     核心实体
#     +
#     事件主题
#
# 后续接入 AI 后可以进一步升级。
#
# ============================================================

def build_event_fingerprint(
    article: Dict[str, Any]
) -> str:

    title = clean_text(
        article.get("title", "")
    )

    summary = clean_text(
        article.get("summary", "")
    )

    text = f"{title} {summary}"

    event_type = identify_event_type(
        article
    )


    entities = []


    entity_groups = {

        "fed": [
            "fed",
            "federal reserve",
            "fomc",
            "fed chair",
        ],

        "iran": [
            "iran",
        ],

        "venezuela": [
            "venezuela",
            "venezuelan",
        ],

        "oil": [
            "oil",
            "crude",
            "opec",
            "brent",
            "wti",
        ],

        "nvidia": [
            "nvidia",
        ],

        "tsmc": [
            "tsmc",
        ],

        "broadcom": [
            "broadcom",
        ],

        "byd": [
            "byd",
        ],

        "us_canada": [
            "us canada",
            "u.s. canada",
            "canada trade",
            "canada tariffs",
        ],

        "russia_ukraine": [
            "russia",
            "ukraine",
        ],

    }


    for entity, keywords in entity_groups.items():

        if contains_any(
            text,
            keywords
        ):

            entities.append(
                entity
            )


    # --------------------------------------------------------
    # 主题识别
    # --------------------------------------------------------

    topic = ""


    if contains_any(
        text,
        [
            "rate",
            "rate cut",
            "rate hike",
            "hawkish",
            "dovish",
        ]
    ):

        topic = "rate_policy"


    elif contains_any(
        text,
        [
            "sanctions",
            "sanction",
        ]
    ):

        topic = "sanctions"


    elif contains_any(
        text,
        [
            "tariff",
            "tariffs",
            "trade war",
        ]
    ):

        topic = "tariffs"


    elif contains_any(
        text,
        [
            "oil",
            "crude",
            "oil reserves",
        ]
    ):

        topic = "oil"


    elif contains_any(
        text,
        [
            "earnings",
            "quarterly results",
        ]
    ):

        topic = "earnings"


    elif contains_any(
        text,
        [
            "ipo",
            "acquisition",
            "merger",
        ]
    ):

        topic = "capital_event"


    elif contains_any(
        text,
        [
            "military",
            "attack",
            "strike",
            "missile",
            "war",
        ]
    ):

        topic = "military"


    # --------------------------------------------------------
    # 如果没有实体
    # 使用标题作为最后兜底
    # --------------------------------------------------------

    if not entities:

        normalized_title = (
            title
            .replace(
                "the ",
                ""
            )
        )

        return (
            f"{event_type}|"
            f"{topic}|"
            f"{normalized_title}"
        )


    return (
        f"{event_type}|"
        f"{topic}|"
        f"{'|'.join(sorted(entities))}"
    )


# ============================================================
# 同一事件合并
# ============================================================

def merge_duplicate_events(
    news_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    event_groups = {}


    for article in news_list:

        key = build_event_fingerprint(
            article
        )


        if key not in event_groups:

            event_groups[key] = []

        event_groups[key].append(
            article
        )


    merged = []


    for key, articles in event_groups.items():

        # ----------------------------------------------------
        # 最高评分新闻作为主新闻
        # ----------------------------------------------------

        articles.sort(
            key=lambda x: (
                x.get(
                    "score",
                    0
                ),
                x.get(
                    "published_at",
                    datetime.min.replace(
                        tzinfo=timezone.utc
                    )
                ),
            ),
            reverse=True
        )


        primary = dict(
            articles[0]
        )


        # ----------------------------------------------------
        # 收集来源
        # ----------------------------------------------------

        sources = []

        urls = []


        for article in articles:

            source = article.get(
                "source"
            )

            url = article.get(
                "url"
            )


            if source and source not in sources:

                sources.append(
                    source
                )


            if url and url not in urls:

                urls.append(
                    url
                )


        primary["sources"] = sources

        primary["urls"] = urls


        # 主来源 / 主链接
        primary["source"] = (
            sources[0]
            if sources
            else primary.get(
                "source",
                ""
            )
        )

        primary["url"] = (
            urls[0]
            if urls
            else primary.get(
                "url",
                ""
            )
        )


        # ----------------------------------------------------
        # 保存合并信息
        # ----------------------------------------------------

        primary["source_count"] = len(
            sources
        )

        primary["merged_count"] = len(
            articles
        )


        merged.append(
            primary
        )


    return merged


# ============================================================
# 最终筛选
# ============================================================

def select_news(
    news_list: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:

    # ========================================================
    # 1. 市场影响力初筛
    # ========================================================

    relevant_news = [

        article

        for article in news_list

        if article.get(
            "market_relevant",
            True
        ) is not False

    ]


    # ========================================================
    # 2. 评分
    # ========================================================

    scored_news = [

        score_news(
            article
        )

        for article in relevant_news

    ]


    # ========================================================
    # 3. 同一事件合并
    # ========================================================

    merged_news = (
        merge_duplicate_events(
            scored_news
        )
    )


    # ========================================================
    # 4. 按分类分组
    # ========================================================

    grouped = {}


    for article in merged_news:

        category = article.get(
            "category",
            "其他市场事件"
        )


        if category not in VALID_CATEGORIES:

            category = "其他市场事件"


        if category not in grouped:

            grouped[category] = []


        grouped[category].append(
            article
        )


    # ========================================================
    # 5. 分类筛选
    # ========================================================

    final_result = {}


    for category, items in grouped.items():

        items.sort(
            key=lambda x: (
                x.get(
                    "score",
                    0
                ),
                x.get(
                    "published_at",
                    datetime.min.replace(
                        tzinfo=timezone.utc
                    )
                ),
            ),
            reverse=True
        )


        # ----------------------------------------------------
        # >40
        #
        # 全部保留
        # ----------------------------------------------------

        high_weight = [

            item

            for item in items

            if item.get(
                "score",
                0
            ) > HIGH_WEIGHT_THRESHOLD

        ]


        # ----------------------------------------------------
        # <=40
        #
        # 每类最多10条
        # ----------------------------------------------------

        low_weight = [

            item

            for item in items

            if item.get(
                "score",
                0
            ) <= HIGH_WEIGHT_THRESHOLD

        ]


        low_weight = low_weight[
            :LOW_WEIGHT_MAX_PER_CATEGORY
        ]


        selected = (
            high_weight
            + low_weight
        )


        selected.sort(
            key=lambda x: (
                x.get(
                    "score",
                    0
                ),
                x.get(
                    "published_at",
                    datetime.min.replace(
                        tzinfo=timezone.utc
                    )
                ),
            ),
            reverse=True
        )


        if selected:

            final_result[
                category
            ] = selected


    return final_result


# ============================================================
# 调试输出
# ============================================================

def print_news_result(
    result: Dict[str, List[Dict[str, Any]]]
) -> None:

    print(
        "\n"
        + "=" * 70
    )

    print(
        "          全球金融市场重大事件"
    )

    print(
        "=" * 70
    )


    total = 0


    for category, articles in result.items():

        print(
            f"\n【{category}】"
        )


        for index, article in enumerate(
            articles,
            1
        ):

            total += 1


            print(
                f"{index}. "
                f"{article.get('title', '无标题')}"
            )

            print(
                f"   事件类型："
                f"{article.get('event_type', '未知')}"
            )

            print(
                f"   影响范围："
                f"{article.get('impact_scope', 0)}/40"
            )

            print(
                f"   影响程度："
                f"{article.get('impact_degree', 0)}/40"
            )

            print(
                f"   来源可信度："
                f"{article.get('source_credibility', 0)}/20"
            )

            print(
                f"   总分："
                f"{article.get('score', 0)}/100"
            )

            print(
                f"   来源："
                f"{'、'.join(article.get('sources', [article.get('source', '未知')]))}"
            )

            print(
                f"   时间："
                f"{article.get('published', '未知')}"
            )

            print(
                f"   原文："
                f"{article.get('url', '无')}"
            )

            if article.get(
                "merged_count",
                1
            ) > 1:

                print(
                    f"   已合并："
                    f"{article['merged_count']} 条同事件新闻"
                )

            print()


    print(
        "=" * 70
    )

    print(
        f"新闻总数：{total}"
    )

    print(
        "=" * 70
    )
