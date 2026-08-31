from typing import List, Dict, Any
from datetime import datetime, timezone


# ============================================================
# Global Market Agent
# 新闻评分与筛选核心 V2
#
# ============================================================
#
# 【最高优先级规则】
#
# 1. 先筛选：
#    只保留对金融市场具有实际影响力的信息。
#
# 2. 再分类：
#    按“事件本身是什么”确定分类。
#    不以关键词命中数量决定分类。
#
# 3. 评分：
#    影响范围：40分
#    影响程度：40分
#    来源可信度：20分
#    总分：100分
#
# 4. 取消 TOP10 总量限制
#
# 5. >40：
#    高权重新闻全部保留，不受数量限制。
#
# 6. <=40：
#    低权重新闻按分类最多10条。
#
# 7. 不足10条：
#    有几条展示几条，不强行补足。
#
# 8. 同一事件：
#    去重、合并，不重复占用展示数量。
#
# 9. 来源：
#    一手官方源：事实确认
#    权威媒体：事件发现、背景、交叉验证
#    国际金融机构：权威研究
#    知名个人：扩展接口
#
# 10. 来源不决定重要性。
#
# 11. 高影响力研报/观点可以进入新闻池，
#     前提仍然是对金融市场具有实际影响力。
#
# 12. 新闻必须来自真实媒体/官方机构。
#
# 13. 每条新闻必须保留来源名称 + 原文链接。
#
# 14. 无法验证的数据：
#     明确标记“数据缺失/获取失败”。
#
# 15. 严禁 AI 编造新闻、行情、事件或引用。
#
# ============================================================


# ============================================================
# 基础配置
# ============================================================

HIGH_WEIGHT_THRESHOLD = 40

LOW_WEIGHT_MAX_PER_CATEGORY = 10


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
#
# 注意：
# 来源可信度只占20分。
#
# 来源权威 ≠ 新闻重要。
# ============================================================

SOURCE_CREDIBILITY_SCORE = {

    # --------------------------------------------------------
    # 官方一手来源
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 权威金融媒体
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 国际金融机构
    # --------------------------------------------------------

    "IMF": 19,
    "BIS": 19,
    "World Bank": 19,

}


# ============================================================
# 来源类型默认可信度
# ============================================================

SOURCE_TYPE_SCORE = {

    "official": 20,

    "major_media": 18,

    "financial_institution": 19,

    "expert": 12,

    "other_verified": 8,

}


# ============================================================
# 工具函数
# ============================================================

def clamp(
    value: int,
    minimum: int,
    maximum: int,
) -> int:

    return max(
        minimum,
        min(
            maximum,
            int(value),
        ),
    )


def clean_text(text: Any) -> str:

    if not text:

        return ""

    return str(text).lower().strip()


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

    source_type = article.get(
        "source_type",
        "other_verified"
    )


    # 已知具体来源
    if source in SOURCE_CREDIBILITY_SCORE:

        return SOURCE_CREDIBILITY_SCORE[source]


    # 来源类型
    return SOURCE_TYPE_SCORE.get(
        source_type,
        SOURCE_TYPE_SCORE["other_verified"],
    )


# ============================================================
# 事件画像
# ============================================================
#
# 注意：
#
# 这一层不是通过“命中多少关键词”计算分数。
#
# 关键词只用于辅助识别事件语义。
#
# 真正决定评分的是：
#
#     这个事件本身是什么？
#     它可能影响哪些市场？
#     它会不会改变政策预期？
#     它会不会改变资产价格？
#     它会不会改变资金流向？
#     它会不会改变企业盈利预期？
#
# ============================================================

def build_event_profile(
    article: Dict[str, Any]
) -> Dict[str, Any]:

    title = clean_text(
        article.get("title", "")
    )

    summary = clean_text(
        article.get("summary", "")
    )

    text = f"{title} {summary}"

    category = article.get(
        "category"
    )


    # --------------------------------------------------------
    # 如果上游已经识别事件类型，优先使用
    # --------------------------------------------------------

    supplied_event_type = article.get(
        "event_type"
    )

    if supplied_event_type:

        return {

            "category": category,

            "event_type":
                supplied_event_type,

        }


    # --------------------------------------------------------
    # 事件识别
    #
    # 注意：
    # 这是“事件语义识别”，不是关键词数量评分。
    # --------------------------------------------------------

    event_type = "一般市场事件"


    # --------------------------------------------------------
    # 央行 / 宏观政策
    # --------------------------------------------------------

    if any(
        phrase in text
        for phrase in [

            "rate decision",
            "rate cut",
            "rate hike",
            "interest rate decision",
            "fed decision",
            "fomc",
            "central bank decision",

        ]
    ):

        event_type = "重大货币政策事件"


    # --------------------------------------------------------
    # 重大宏观数据
    # --------------------------------------------------------

    elif any(
        phrase in text
        for phrase in [

            "cpi",
            "ppi",
            "payroll",
            "nonfarm payroll",
            "unemployment rate",
            "gdp",
            "inflation data",

        ]
    ):

        event_type = "重大宏观数据事件"


    # --------------------------------------------------------
    # 重大地缘事件
    # --------------------------------------------------------

    elif any(
        phrase in text
        for phrase in [

            "military attack",
            "missile attack",
            "invasion",
            "war",
            "ceasefire",
            "military conflict",

        ]
    ):

        event_type = "重大地缘事件"


    # --------------------------------------------------------
    # 制裁 / 贸易政策
    # --------------------------------------------------------

    elif any(
        phrase in text
        for phrase in [

            "sanctions",
            "tariffs",
            "trade restrictions",
            "export controls",
            "export ban",

        ]
    ):

        event_type = "重大贸易或制裁事件"


    # --------------------------------------------------------
    # 公司资本事件
    # --------------------------------------------------------

    elif any(
        phrase in text
        for phrase in [

            "acquisition",
            "merger",
            "takeover",
            "bankruptcy",
            "ipo",

        ]
    ):

        event_type = "重大公司资本事件"


    # --------------------------------------------------------
    # 公司财报
    # --------------------------------------------------------

    elif any(
        phrase in text
        for phrase in [

            "earnings",
            "quarterly results",
            "revenue",
            "profit",
            "guidance",

        ]
    ):

        event_type = "重大财报或经营事件"


    # --------------------------------------------------------
    # 能源供需 / 产量事件
    # --------------------------------------------------------

    elif any(
        phrase in text
        for phrase in [

            "opec",
            "oil production",
            "oil supply",
            "crude production",
            "oil output",

        ]
    ):

        event_type = "重大能源供需事件"


    # --------------------------------------------------------
    # 市场剧烈波动
    # --------------------------------------------------------

    elif any(
        phrase in text
        for phrase in [

            "market crash",
            "market selloff",
            "selloff",
            "sell-off",
            "market plunge",
            "market surge",
            "record high",
            "record low",

        ]
    ):

        event_type = "重大市场价格变化"


    # --------------------------------------------------------
    # 研究 / 观点
    # --------------------------------------------------------

    elif any(
        phrase in title
        for phrase in [

            "analysis",
            "outlook",
            "forecast",
            "opinion",

        ]
    ):

        event_type = "研究或市场观点"


    return {

        "category":
            category,

        "event_type":
            event_type,

    }


# ============================================================
# 分类
# ============================================================
#
# 核心原则：
#
# 分类应该描述“发生了什么事件”。
#
# 不是：
#     出现 oil → 能源
#
# 而是：
#     OPEC决定削减产量
#     → 能源与大宗商品
#
#     伊朗发动军事攻击导致霍尔木兹海峡运输风险上升
#     → 地缘政治与制裁
#
#     Fed宣布降息
#     → 宏观经济与央行政策
#
# ============================================================

def classify_news(
    article: Dict[str, Any]
) -> str:

    supplied_category = article.get(
        "category"
    )

    if supplied_category in VALID_CATEGORIES:

        return supplied_category


    profile = build_event_profile(
        article
    )

    event_type = profile[
        "event_type"
    ]


    if event_type in [

        "重大货币政策事件",
        "重大宏观数据事件",

    ]:

        return "宏观经济与央行政策"


    if event_type in [

        "重大地缘事件",
        "重大贸易或制裁事件",

    ]:

        return "地缘政治与制裁"


    if event_type == "重大能源供需事件":

        return "能源与大宗商品"


    if event_type in [

        "重大公司资本事件",
        "重大财报或经营事件",

    ]:

        return "公司重大事件"


    if event_type == "重大市场价格变化":

        return "全球金融市场"


    title = clean_text(
        article.get("title", "")
    )

    summary = clean_text(
        article.get("summary", "")
    )

    text = f"{title} {summary}"


    # AI / 半导体事件
    if any(
        phrase in text
        for phrase in [

            "artificial intelligence",
            "ai model",
            "ai chip",
            "gpu",
            "semiconductor",
            "nvidia",
            "amd",
            "broadcom",
            "tsmc",
            "asml",
            "hbm",
            "memory",
            "optical networking",
            "data center",

        ]
    ):

        return "AI与半导体"


    # 外汇事件
    if any(
        phrase in text
        for phrase in [

            "forex",
            "currency",
            "dollar",
            "yen",
            "yuan",
            "exchange rate",

        ]
    ):

        return "外汇"


    # 债券 / 利率市场
    if any(
        phrase in text
        for phrase in [

            "treasury yield",
            "bond yield",
            "bond market",
            "treasury market",

        ]
    ):

        return "债券与利率"


    # 贵金属
    if any(
        phrase in text
        for phrase in [

            "gold price",
            "gold futures",
            "silver price",

        ]
    ):

        return "贵金属"


    return "其他市场事件"


# ============================================================
# 影响范围评分
# ============================================================
#
# 最高40分。
#
# 判断：
#
# 1. 是否影响全球市场
# 2. 是否影响多个国家
# 3. 是否影响多个资产类别
# 4. 是否影响多个行业
# 5. 是否影响全球资金流向
#
# ============================================================

def calculate_impact_scope(
    article: Dict[str, Any]
) -> int:

    # 如果未来接入 AI 事件分析模块，
    # 可以直接使用其结构化判断。

    supplied = article.get(
        "impact_scope"
    )

    if supplied is not None:

        return clamp(
            supplied,
            0,
            40,
        )


    profile = build_event_profile(
        article
    )

    event_type = profile[
        "event_type"
    ]

    category = classify_news(
        article
    )


    # --------------------------------------------------------
    # 全球性政策 / 宏观事件
    # --------------------------------------------------------

    if event_type == "重大货币政策事件":

        return 40


    if event_type == "重大宏观数据事件":

        return 36


    # --------------------------------------------------------
    # 全球重大地缘事件
    # --------------------------------------------------------

    if event_type == "重大地缘事件":

        return 38


    # --------------------------------------------------------
    # 全球贸易 / 制裁
    # --------------------------------------------------------

    if event_type == "重大贸易或制裁事件":

        return 35


    # --------------------------------------------------------
    # 能源供需
    # --------------------------------------------------------

    if event_type == "重大能源供需事件":

        return 34


    # --------------------------------------------------------
    # 公司重大资本事件
    # --------------------------------------------------------

    if event_type == "重大公司资本事件":

        return 28


    # --------------------------------------------------------
    # 重大财报
    # --------------------------------------------------------

    if event_type == "重大财报或经营事件":

        if category == "AI与半导体":

            return 30

        return 26


    # --------------------------------------------------------
    # 市场价格变化
    # --------------------------------------------------------

    if event_type == "重大市场价格变化":

        return 30


    # --------------------------------------------------------
    # AI / 半导体
    # --------------------------------------------------------

    if category == "AI与半导体":

        return 24


    # --------------------------------------------------------
    # 全球金融市场
    # --------------------------------------------------------

    if category == "全球金融市场":

        return 24


    # --------------------------------------------------------
    # 外汇
    # --------------------------------------------------------

    if category == "外汇":

        return 24


    # --------------------------------------------------------
    # 债券
    # --------------------------------------------------------

    if category == "债券与利率":

        return 24


    # --------------------------------------------------------
    # 贵金属
    # --------------------------------------------------------

    if category == "贵金属":

        return 20


    return 15


# ============================================================
# 影响程度评分
# ============================================================
#
# 最高40分。
#
# 判断事件是否：
#
# - 改变政策预期
# - 改变利率预期
# - 改变资产估值
# - 改变企业盈利预期
# - 改变商品供需
# - 改变资金流向
# - 改变风险偏好
#
# ============================================================

def calculate_impact_degree(
    article: Dict[str, Any]
) -> int:

    supplied = article.get(
        "impact_degree"
    )

    if supplied is not None:

        return clamp(
            supplied,
            0,
            40,
        )


    profile = build_event_profile(
        article
    )

    event_type = profile[
        "event_type"
    ]


    if event_type == "重大货币政策事件":

        return 40


    if event_type == "重大宏观数据事件":

        return 34


    if event_type == "重大地缘事件":

        return 38


    if event_type == "重大贸易或制裁事件":

        return 34


    if event_type == "重大能源供需事件":

        return 34


    if event_type == "重大公司资本事件":

        return 34


    if event_type == "重大财报或经营事件":

        return 30


    if event_type == "重大市场价格变化":

        return 32


    if event_type == "研究或市场观点":

        return 20


    return 10


# ============================================================
# 总分
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

    total = (
        scope
        + degree
        + credibility
    )

    return clamp(
        total,
        0,
        100,
    )


# ============================================================
# 单条新闻标准化
# ============================================================

def score_news(
    article: Dict[str, Any]
) -> Dict[str, Any]:

    result = dict(
        article
    )


    # 分类
    result["category"] = classify_news(
        result
    )


    # 事件类型
    profile = build_event_profile(
        result
    )

    result["event_type"] = profile[
        "event_type"
    ]


    # 三项评分
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


    # 总分
    result["score"] = (
        result["impact_scope"]
        + result["impact_degree"]
        + result["source_credibility"]
    )


    return result


# ============================================================
# 同一事件识别
# ============================================================
#
# 当前阶段：
#
# 如果上游已经提供 event_id，
# 直接使用。
#
# 如果没有 event_id，
# 使用标题 / 来源 / 事件类型建立临时事件键。
#
# 后续接入 AI 事件识别后，
# 这里可以升级为真正的语义事件聚类。
#
# ============================================================

def get_event_key(
    article: Dict[str, Any]
) -> str:

    event_id = article.get(
        "event_id"
    )

    if event_id:

        return str(
            event_id
        )


    # 如果未来上游提供 canonical_event
    canonical_event = article.get(
        "canonical_event"
    )

    if canonical_event:

        return clean_text(
            canonical_event
        )


    # 当前阶段使用标题作为最后兜底
    title = clean_text(
        article.get("title", "")
    )

    category = clean_text(
        article.get("category", "")
    )

    return f"{category}|{title}"


# ============================================================
# 合并来源
# ============================================================

def merge_sources(
    primary: Dict[str, Any],
    secondary: Dict[str, Any]
) -> Dict[str, Any]:

    result = dict(
        primary
    )


    sources = []

    for article in [
        primary,
        secondary,
    ]:

        source = article.get(
            "source"
        )

        if source and source not in sources:

            sources.append(
                source
            )


    result["sources"] = sources


    # --------------------------------------------------------
    # 原文链接
    # --------------------------------------------------------

    urls = []

    for article in [
        primary,
        secondary,
    ]:

        url = article.get(
            "url"
        )

        if url and url not in urls:

            urls.append(
                url
            )


    result["urls"] = urls


    # 主链接必须保留
    if urls:

        result["url"] = urls[0]


    return result


# ============================================================
# 同事件合并
# ============================================================

def merge_duplicate_events(
    news_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:

    events = {}


    for article in news_list:

        key = get_event_key(
            article
        )


        if key not in events:

            events[key] = dict(
                article
            )

            continue


        existing = events[key]


        # ----------------------------------------------------
        # 评分最高者作为主新闻
        # ----------------------------------------------------

        if article.get(
            "score",
            0
        ) > existing.get(
            "score",
            0
        ):

            primary = article
            secondary = existing

        else:

            primary = existing
            secondary = article


        events[key] = merge_sources(
            primary,
            secondary
        )


    return list(
        events.values()
    )


# ============================================================
# 市场影响力初筛
# ============================================================
#
# 注意：
#
# 这是“是否值得进入新闻池”的判断，
# 不是关键词数量判断。
#
# 当前 RSS 阶段：
#
# news_data.py 已经完成基础市场相关性初筛，
# 因此这里默认 market_relevant=True。
#
# 后续接入 AI 判断后，可以直接使用：
#
# article["market_relevant"] = True / False
#
# ============================================================

def is_market_relevant(
    article: Dict[str, Any]
) -> bool:

    value = article.get(
        "market_relevant"
    )

    if value is False:

        return False


    return True


# ============================================================
# 最终新闻筛选
# ============================================================
#
# 最核心的展示规则：
#
#                 所有候选新闻
#                       ↓
#                市场影响力初筛
#                       ↓
#                     评分
#                       ↓
#                  同事件合并
#                       ↓
#                    按分类
#                       ↓
#          ┌────────────┴────────────┐
#          ↓                         ↓
#       >40分                      <=40分
#          ↓                         ↓
#      全部保留                  每类最多10条
#          ↓                         ↓
#          └────────────┬────────────┘
#                       ↓
#                    最终新闻
#
# ============================================================

def select_news(
    news_list: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:


    # --------------------------------------------------------
    # 1. 市场影响力初筛
    # --------------------------------------------------------

    relevant_news = [

        article

        for article in news_list

        if is_market_relevant(
            article
        )

    ]


    # --------------------------------------------------------
    # 2. 评分
    # --------------------------------------------------------

    scored_news = [

        score_news(
            article
        )

        for article in relevant_news

    ]


    # --------------------------------------------------------
    # 3. 同一事件合并
    # --------------------------------------------------------

    merged_news = (
        merge_duplicate_events(
            scored_news
        )
    )


    # --------------------------------------------------------
    # 4. 按分类整理
    # --------------------------------------------------------

    grouped = {}

    for category in VALID_CATEGORIES:

        grouped[category] = []


    for article in merged_news:

        category = article.get(
            "category",
            "其他市场事件"
        )

        if category not in VALID_CATEGORIES:

            category = "其他市场事件"


        grouped[category].append(
            article
        )


    # --------------------------------------------------------
    # 5. 分类执行展示规则
    # --------------------------------------------------------

    final_result = {}


    for category, items in grouped.items():

        if not items:

            continue


        # ----------------------------------------------------
        # 按分数排序
        # ----------------------------------------------------

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
        # 高权重
        #
        # >40
        #
        # 全部保留
        # ----------------------------------------------------

        high_weight = [

            article

            for article in items

            if article.get(
                "score",
                0
            ) > HIGH_WEIGHT_THRESHOLD

        ]


        # ----------------------------------------------------
        # 低权重
        #
        # <=40
        #
        # 每类最多10条
        # ----------------------------------------------------

        low_weight = [

            article

            for article in items

            if article.get(
                "score",
                0
            ) <= HIGH_WEIGHT_THRESHOLD

        ]


        low_weight = low_weight[
            :LOW_WEIGHT_MAX_PER_CATEGORY
        ]


        # ----------------------------------------------------
        # 合并
        # ----------------------------------------------------

        selected = (
            high_weight
            + low_weight
        )


        # ----------------------------------------------------
        # 最终排序
        # ----------------------------------------------------

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


    for category, news_list in result.items():

        print(
            f"\n【{category}】"
        )


        for index, article in enumerate(
            news_list,
            1
        ):

            total += 1


            print(
                f"{index}. "
                f"{article.get('title', '无标题')}"
            )


            print(
                "   "
                f"影响范围："
                f"{article.get('impact_scope', 0)}/40"
            )


            print(
                "   "
                f"影响程度："
                f"{article.get('impact_degree', 0)}/40"
            )


            print(
                "   "
                f"来源可信度："
                f"{article.get('source_credibility', 0)}/20"
            )


            print(
                "   "
                f"总分："
                f"{article.get('score', 0)}/100"
            )


            print(
                "   "
                f"事件类型："
                f"{article.get('event_type', '未知')}"
            )


            print(
                "   "
                f"来源："
                f"{article.get('source', '未知')}"
            )


            print(
                "   "
                f"时间："
                f"{article.get('published', '未知')}"
            )


            print(
                "   "
                f"链接："
                f"{article.get('url', '无')}"
            )


    print(
        "\n"
        + "=" * 70
    )

    print(
        f"新闻总数：{total}"
    )

    print(
        "=" * 70
    )
