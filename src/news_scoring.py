from collections import defaultdict
from datetime import datetime


# ============================================================
# 全球金融市场日报
# news_scoring.py
#
# 职责：
#
# 1. 接收 Groq AI 新闻分析结果
# 2. 执行确定性的评分规则
# 3. 执行同一事件合并
# 4. 执行最终新闻展示规则
# 5. 执行最终排序
#
# AI负责：
#   新闻理解
#   是否具有金融市场影响
#   事件识别
#   新闻分类
#   影响范围等级
#   影响程度等级
#
# 本文件负责：
#   影响范围评分
#   影响程度评分
#   来源可信度评分
#   同一事件去重
#   新闻筛选
#   最终排序
#
# 最终评分：
#
# 影响范围       40分
# 影响程度       40分
# 来源可信度     20分
# ----------------
# 总分           100分
#
# 注意：
# ❌ 不使用关键词判断新闻重要性
# ❌ 不使用关键词判断新闻分类
# ❌ 不使用关键词判断影响范围
# ❌ 不使用关键词判断影响程度
# ❌ 不使用时效性评分
# ============================================================


# ============================================================
# 新闻分类
# ============================================================

CATEGORIES = [

    "宏观经济与央行政策",
    "全球股市",
    "AI与半导体",
    "能源与大宗商品",
    "外汇与债券",
    "地缘政治与制裁",
    "公司重大事件",
    "其他市场事件",

]


# ============================================================
# 来源可信度
#
# 来源只影响20分。
#
# 来源权威程度：
# 不能改变影响范围
# 不能改变影响程度
# ============================================================

SOURCE_CREDIBILITY = {

    # --------------------------------------------------------
    # 官方机构
    # --------------------------------------------------------

    "Federal Reserve": 20,
    "U.S. Treasury": 20,
    "U.S. Department of Treasury": 20,
    "U.S. Department of Energy": 20,
    "U.S. Department of Commerce": 20,

    "OPEC": 20,

    "ECB": 20,
    "European Central Bank": 20,

    "Bank of Japan": 20,
    "BOJ": 20,

    "Bank of England": 20,

    "People's Bank of China": 20,
    "PBOC": 20,

    "IMF": 20,
    "World Bank": 20,
    "BIS": 20,


    # --------------------------------------------------------
    # 权威财经媒体
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

}


# ============================================================
# 影响范围 → 固定分值
#
# Groq只判断等级。
# Python负责固定换算分数。
# ============================================================

IMPACT_SCOPE_SCORES = {

    "global": 40,
    "multi_region": 32,
    "regional": 24,
    "country": 16,
    "industry": 8,
    "company": 8,
    "limited": 4,

}


# ============================================================
# 影响程度 → 固定分值
#
# Groq只判断等级。
# Python负责固定换算分数。
# ============================================================

IMPACT_DEGREE_SCORES = {

    "very_high": 40,
    "high": 30,
    "medium": 20,
    "low": 10,

}


# ============================================================
# 标准化文本
# ============================================================

def normalize_text(text):

    if not text:

        return ""

    return str(
        text
    ).strip()


# ============================================================
# 来源可信度
# ============================================================

def get_source_credibility(source):

    if not source:

        return 0


    source = normalize_text(
        source
    )


    # 精确匹配
    if source in SOURCE_CREDIBILITY:

        return SOURCE_CREDIBILITY[
            source
        ]


    # 模糊匹配
    source_lower = source.lower()


    for name, score in SOURCE_CREDIBILITY.items():

        if name.lower() in source_lower:

            return score


    # 未知来源
    #
    # 不猜测
    # 不给予默认高分

    return 0


# ============================================================
# 标准化影响范围
# ============================================================

def normalize_impact_scope(value):

    if value is None:

        return "limited"


    value = str(
        value
    ).strip().lower()


    aliases = {

        "global":
            "global",

        "worldwide":
            "global",

        "global_market":
            "global",


        "multi_region":
            "multi_region",

        "multi-regional":
            "multi_region",

        "multiple_regions":
            "multi_region",


        "regional":
            "regional",


        "country":
            "country",

        "national":
            "country",

        "single_country":
            "country",


        "industry":
            "industry",

        "sector":
            "industry",


        "company":
            "company",

        "single_company":
            "company",


        "limited":
            "limited",

        "local":
            "limited",

    }


    return aliases.get(
        value,
        "limited"
    )


# ============================================================
# 标准化影响程度
# ============================================================

def normalize_impact_degree(value):

    if value is None:

        return "low"


    value = str(
        value
    ).strip().lower()


    aliases = {

        "very_high":
            "very_high",

        "very-high":
            "very_high",

        "critical":
            "very_high",

        "extreme":
            "very_high",


        "high":
            "high",

        "major":
            "high",


        "medium":
            "medium",

        "moderate":
            "medium",


        "low":
            "low",

        "minor":
            "low",

    }


    return aliases.get(
        value,
        "low"
    )


# ============================================================
# 影响范围评分
# ============================================================

def score_impact_scope(article):

    level = normalize_impact_scope(
        article.get(
            "impact_scope_level"
        )
    )


    return IMPACT_SCOPE_SCORES.get(
        level,
        4
    )


# ============================================================
# 影响程度评分
# ============================================================

def score_impact_degree(article):

    level = normalize_impact_degree(
        article.get(
            "impact_degree_level"
        )
    )


    return IMPACT_DEGREE_SCORES.get(
        level,
        10
    )


# ============================================================
# 最终评分
#
# 固定公式：
#
# 影响范围       40
# +
# 影响程度       40
# +
# 来源可信度     20
# =
# 总分           100
#
# 不包含时效性评分。
# ============================================================

def calculate_score(article):

    impact_scope = score_impact_scope(
        article
    )


    impact_degree = score_impact_degree(
        article
    )


    source_credibility = get_source_credibility(
        article.get(
            "source",
            ""
        )
    )


    # 强制边界

    impact_scope = min(
        max(
            impact_scope,
            0
        ),
        40
    )


    impact_degree = min(
        max(
            impact_degree,
            0
        ),
        40
    )


    source_credibility = min(
        max(
            source_credibility,
            0
        ),
        20
    )


    total_score = (
        impact_scope
        + impact_degree
        + source_credibility
    )


    article["impact_scope"] = (
        impact_scope
    )

    article["impact_degree"] = (
        impact_degree
    )

    article["source_credibility"] = (
        source_credibility
    )

    article["score"] = (
        total_score
    )


    return article


# ============================================================
# 新闻标准化
# ============================================================

def prepare_article(article):

    article = dict(
        article
    )


    article.setdefault(
        "category",
        "其他市场事件"
    )


    article.setdefault(
        "event_id",
        None
    )


    article.setdefault(
        "market_relevant",
        False
    )


    article.setdefault(
        "score",
        0
    )


    return article


# ============================================================
# AI事件ID标准化
#
# 注意：
#
# ai_news_analyzer.py 已经统一输出 event_id。
#
# 本文件不再使用 event_key。
# ============================================================

def get_event_id(article):

    event_id = article.get(
        "event_id"
    )


    if event_id:

        return normalize_text(
            event_id
        ).lower()


    # --------------------------------------------------------
    # AI没有提供event_id时
    #
    # 不主动猜测事件。
    #
    # 使用标题作为保守唯一标识，
    # 避免错误合并不同事件。
    # --------------------------------------------------------

    title = normalize_text(
        article.get(
            "title",
            ""
        )
    ).lower()


    if title:

        return (
            f"title:{title}"
        )


    return None


# ============================================================
# 同一事件合并
#
# 同一事件判断：
#
# 由 Groq AI 输出 event_id。
#
# 本文件不通过关键词判断。
# ============================================================

def merge_same_events(articles):

    groups = defaultdict(
        list
    )


    for article in articles:

        event_id = get_event_id(
            article
        )


        if event_id is None:

            event_id = (
                f"article:"
                f"{id(article)}"
            )


        groups[
            event_id
        ].append(
            article
        )


    merged = []


    for event_id, items in groups.items():

        # ----------------------------------------------------
        # 主新闻：
        #
        # 优先评分最高
        # 分数相同则选择最新
        # ----------------------------------------------------

        items.sort(

            key=lambda x: (

                x.get(
                    "score",
                    0
                ),

                x.get(
                    "published_at"
                )
                or datetime.min

            ),

            reverse=True

        )


        primary = dict(
            items[0]
        )


        # ----------------------------------------------------
        # 保留多个真实来源
        # ----------------------------------------------------

        sources = []

        urls = []


        for item in items:

            source = item.get(
                "source"
            )

            url = item.get(
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


        primary["sources"] = (
            sources
        )

        primary["urls"] = (
            urls
        )

        primary["merged_count"] = (
            len(items)
        )

        primary["event_id"] = (
            event_id
        )


        merged.append(
            primary
        )


    return merged


# ============================================================
# 低权重新闻选择
#
# score <= 40
#
# 每个分类最多10条。
#
# 不存在总TOP10。
# ============================================================

def select_low_score_news(
    articles
):

    category_groups = defaultdict(
        list
    )


    for article in articles:

        category = article.get(
            "category",
            "其他市场事件"
        )


        category_groups[
            category
        ].append(
            article
        )


    selected = []


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
                or datetime.min

            ),

            reverse=True

        )


        selected.extend(
            items[:10]
        )


    return selected


# ============================================================
# 最终排序
#
# 第一优先级：总分
# 第二优先级：发布时间
# ============================================================

def sort_news(articles):

    return sorted(

        articles,

        key=lambda x: (

            x.get(
                "score",
                0
            ),

            x.get(
                "published_at"
            )
            or datetime.min

        ),

        reverse=True

    )


# ============================================================
# 主筛选函数
#
# 流程：
#
# Groq AI
#    ↓
# 过滤非市场新闻
#    ↓
# 分类校验
#    ↓
# 硬规则评分
#    ↓
# event_id去重
#    ↓
# >40全部保留
#    ↓
# <=40各分类Top10
#    ↓
# 最终排序
# ============================================================

def select_news(
    analyzed_news
):

    print(
        "\n============================================================"
    )

    print(
        "开始执行新闻硬规则评分与筛选"
    )

    print(
        "============================================================"
    )


    # ========================================================
    # 第一步
    # 接收 Groq AI 分析结果
    # ========================================================

    market_candidates = []


    for raw_article in analyzed_news:

        article = prepare_article(
            raw_article
        )


        # ----------------------------------------------------
        # 必须存在真实来源
        # ----------------------------------------------------

        if not article.get(
            "source"
        ):

            continue


        # ----------------------------------------------------
        # 必须存在原文链接
        # ----------------------------------------------------

        if not article.get(
            "url"
        ):

            continue


        # ----------------------------------------------------
        # 必须存在发布时间
        # ----------------------------------------------------

        if not article.get(
            "published_at"
        ):

            continue


        # ----------------------------------------------------
        # AI判断：
        #
        # 是否真正具有金融市场影响
        # ----------------------------------------------------

        if article.get(
            "market_relevant",
            False
        ) is not True:

            continue


        # ----------------------------------------------------
        # AI确定的事件分类
        # ----------------------------------------------------

        category = article.get(
            "category"
        )


        if category not in CATEGORIES:

            category = (
                "其他市场事件"
            )


        article["category"] = (
            category
        )


        # ----------------------------------------------------
        # 执行硬规则评分
        # ----------------------------------------------------

        article = calculate_score(
            article
        )


        market_candidates.append(
            article
        )


    print(
        f"市场相关候选新闻："
        f"{len(market_candidates)}"
    )


    # ========================================================
    # 第二步
    # 同一事件合并
    # ========================================================

    merged_news = merge_same_events(
        market_candidates
    )


    print(
        f"同一事件合并后："
        f"{len(merged_news)}"
    )


    # ========================================================
    # 第三步
    # >40分全部保留
    # ========================================================

    high_score_news = [

        article

        for article in merged_news

        if article.get(
            "score",
            0
        ) > 40

    ]


    # ========================================================
    # 第四步
    # <=40分
    #
    # 各分类最多10条
    # ========================================================

    low_score_news = [

        article

        for article in merged_news

        if article.get(
            "score",
            0
        ) <= 40

    ]


    low_score_selected = (
        select_low_score_news(
            low_score_news
        )
    )


    print(
        f"高权重新闻（>40）："
        f"{len(high_score_news)}"
    )


    print(
        f"低权重新闻（<=40）："
        f"{len(low_score_selected)}"
    )


    # ========================================================
    # 第五步
    # 最终结果
    # ========================================================

    final_news = (

        high_score_news
        + low_score_selected

    )


    final_news = sort_news(
        final_news
    )


    print(
        f"最终新闻数量："
        f"{len(final_news)}"
    )


    print(
        "============================================================"
    )


    # ========================================================
    # 按分类返回
    # ========================================================

    result = defaultdict(
        list
    )


    for article in final_news:

        category = article.get(
            "category",
            "其他市场事件"
        )


        result[
            category
        ].append(
            article
        )


    return dict(
        result
    )


# ============================================================
# 单条新闻调试
# ============================================================

def score_single_article(
    article
):

    article = prepare_article(
        article
    )


    if article.get(
        "market_relevant",
        False
    ) is not True:

        article[
            "market_relevant"
        ] = False

        return article


    category = article.get(
        "category",
        "其他市场事件"
    )


    if category not in CATEGORIES:

        category = (
            "其他市场事件"
        )


    article["category"] = (
        category
    )


    return calculate_score(
        article
    )
