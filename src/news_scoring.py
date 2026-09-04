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
#
# ------------------------------------------------------------
# 本版改动（v3，筛选机制从"线性加权分数+40分阈值"
# 改为"分层阈值 + 熔断规则"）：
#
# 核心问题：v2 用 impact_scope(40) + impact_degree(40) +
# source_credibility(20) 相加，再拿总分和40分比大小。
# 这是线性加权，天然有个副作用——三个维度可以互相"兑换"，
# 一条 scope小、degree低的新闻，只要来源分够高也能凑够40分；
# 反过来一条 degree=high 的新闻，也可能因为来源不在名单里
# 被压到40分以下。用户明确要求换成更"硬"的机制。
#
# v3 做法：
#
# 1. 新增 classify_tier()，用 (影响范围, 影响程度) 两个维度
#    直接查表判定"保留 / 低权重 / 丢弃"三档，
#    来源可信度完全不参与这个判定——只用于同档位内部排序。
#    具体分层表见 classify_tier() 的实现和注释。
#
# 2. 移除 is_guaranteed_keep + GUARANTEED_KEEP_DEGREE_LEVELS，
#    "very_high无条件保留"现在是 classify_tier() 里分层表的
#    一部分，不再是叠加在总分之外的补丁规则。
#
# 3. score（100分制）仍然保留、仍然计算——但只作为"同一档位
#    内部排序"和最终展示用的数值，不再是决定新闻能不能进
#    日报的门槛。
#
# 4. CATEGORIES 沿用3类，DEFAULT_CATEGORY、
#    LOW_SCORE_TOP_N_PER_CATEGORY(=15)、
#    UNKNOWN_SOURCE_CREDIBILITY(=5) 沿用v2的调整——
#    这几项跟评分本身/展示相关，不受本次筛选机制改动影响。
# ------------------------------------------------------------
# ============================================================


# ============================================================
# 新闻分类（3类分类基准，与 ai_news_analyzer.py 保持一致）
#
# 重要原则：
# "国际 / 中国"不是分类维度，
# 三个分类都同时覆盖国际与中国市场的同类事件。
# ============================================================

CATEGORIES = [

    "宏观、政策与地缘",
    "市场与资产",
    "公司、行业与研报",

]


# ============================================================
# 兜底分类
#
# AI理论上必须返回3类之一，这里只是防御性兜底，
# 正常流程不应该触发。
# ============================================================

DEFAULT_CATEGORY = "公司、行业与研报"


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
    "SEC": 20,
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
# 未知来源默认分
#
# 不在上面名单里的来源，不代表不重要——
# 只是我们没有为它单独定级。
#
# 给一个中性偏低的地板分（5/20），而不是0分：
# 0分会让"来源没被收录"这一个因素，独立决定一条
# impact_degree=high 的新闻是否落入低权重池，
# 这不是我们想要的评分逻辑。
#
# 仍然遵守"不猜测、不给默认高分"的原则——
# 5分远低于已知权威来源的17-20分。
# ============================================================

UNKNOWN_SOURCE_CREDIBILITY = 5


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
# 影响范围分组
#
# 分层判定表把 impact_scope_level 归成三组：
#
# 广  —— global / multi_region
# 中  —— regional / country
# 窄  —— industry / company / limited
#
# 分组只用于 classify_tier() 查表，
# 不影响 score 计算（score仍按 IMPACT_SCOPE_SCORES 逐级计分）。
# ============================================================

BROAD_SCOPES = {"global", "multi_region"}

MID_SCOPES = {"regional", "country"}

NARROW_SCOPES = {"industry", "company", "limited"}


# ============================================================
# 低权重新闻：每个分类的保留上限
#
# 分类从8类合并为3类之后，单个类目覆盖的新闻面变广了，
# 固定10条的上限比合并前更容易把同样值得露出的新闻挤掉，
# 所以上调到15。
# ============================================================

LOW_SCORE_TOP_N_PER_CATEGORY = 15


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
    # 不猜测，不给予默认高分，
    # 但也不再是最惩罚性的0分——
    # 见上方 UNKNOWN_SOURCE_CREDIBILITY 的说明。

    return UNKNOWN_SOURCE_CREDIBILITY


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
# 标准化内容性质
#
# event（具体事件）/ commentary（评论分析类软文）。
#
# 缺失时默认event——保守默认，不因为字段缺失就误伤，
# 跟这个文件里其他字段的默认值取向一致。
# ============================================================

def normalize_content_nature(value):

    if value is None:

        return "event"


    value = str(
        value
    ).strip().lower()


    aliases = {

        "event":
            "event",

        "news_event":
            "event",

        "fact":
            "event",


        "commentary":
            "commentary",

        "opinion":
            "commentary",

        "analysis":
            "commentary",

        "analyst_commentary":
            "commentary",

    }


    return aliases.get(
        value,
        "event"
    )


# ============================================================
# 标准化股市相关度
#
# direct（直接催化剂）/ indirect（间接影响）/ weak（弱相关/噪音）。
#
# 缺失或无法识别时默认indirect——中性值，不会触发classify_tier
# 里的降级判断，跟这个文件其他字段"缺失不误伤"的默认取向一致。
#
# 注意：这个字段只用于分层判定表里的"降级"判断，不参与
# calculate_score的100分制计分——跟content_nature一样，
# 是类别判断，不是拿去加权/相乘的分数，避免重新引入线性加权
# 让各维度互相"兑换"的老问题（比如来源分高就能把低程度新闻
# 顶进高权重区）。
# ============================================================

def normalize_equity_relevance(value):

    if value is None:

        return "indirect"


    value = str(
        value
    ).strip().lower()


    aliases = {

        "direct":
            "direct",

        "indirect":
            "indirect",

        "weak":
            "weak",

        "noise":
            "weak",

    }


    return aliases.get(
        value,
        "indirect"
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
#
# 注意：score只用于同一档位内部排序和最终展示，
# 新闻能不能进日报由 classify_tier() 单独判定，
# 不再依赖这里算出来的分数是否过线。
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
# 分层阈值判定表
#
# 用 (影响范围分组, 影响程度) 两个维度直接查表，
# 判定这条新闻属于 "keep / low_weight / discard" 三档之一。
#
# 来源可信度不参与这个判定——
# 一条新闻该不该进日报，只取决于AI判断的影响范围和影响程度，
# 这也符合项目一直坚持的原则："来源权威不能提高影响范围/程度"，
# 这里做得更彻底：来源干脆不参与"要不要保留"的判断。
#
# ============================================================
# 分层阈值判定表
#
# 用 (影响范围分组, 影响程度) 两个维度直接查表，
# 判定这条新闻属于 "keep / low_weight / discard" 三档之一。
#
# 来源可信度不参与这个判定——
# 一条新闻该不该进日报，只取决于AI判断的影响范围和影响程度，
# 这也符合项目一直坚持的原则："来源权威不能提高影响范围/程度"，
# 这里做得更彻底：来源干脆不参与"要不要保留"的判断。
#
# 分层判定表（v5：medium档收紧 + 加入equity_relevance降级）
#
#                  very_high   high     medium
#   广(global/     keep        keep*    low_weight
#   multi_region)
#   中(regional/   keep        keep*    low_weight
#   country)
#   窄(industry/   keep        keep*    low_weight（degree=low时discard）
#   company/
#   limited)
#
#   * 标了星号的格子，如果 content_nature=commentary（评论/分析类
#     软文，不是具体发生的事件）或者 equity_relevance=weak
#     （跟股票定价关系疏远），降级为low_weight，不再无条件保留。
#     两个条件任一命中就降级。
#     very_high这一行不受两者影响——真正的黑天鹅级别，
#     不该因为报道形式或相关度评级就被压低。
#
#   v5改动：degree=medium不再有"BROAD scope例外"，
#   不管范围是不是全球，medium程度统一进低权重池排队——
#   之前"全球+medium=无条件保留"这个格子太松，大量"油价涨了
#   几美元""某国货币走强"这类日常波动报道能不受限制地
#   涌进日报，收紧之后只有真正high/very_high程度的事件
#   才无条件保留。
#
# 注意：content_nature 和 equity_relevance 都只用于"降级"，
# 不会把本来该进低权重池的新闻"升级"成无条件保留——
# 这两个维度是质量闸门，不是加分项，避免重新引入"某个维度
# 分高就能把新闻顶进高权重区"的线性加权老问题。
#
# 三档含义：
#
# keep       —— 无条件保留，不受分类数量限制
# low_weight —— 进入低权重候选池，按分类Top15筛选
# discard    —— 直接丢弃，不进入任何候选池
#               （只有"窄范围+低程度"这种噪音级组合才会触发）
# ============================================================

def classify_tier(article):

    scope = normalize_impact_scope(
        article.get(
            "impact_scope_level"
        )
    )


    degree = normalize_impact_degree(
        article.get(
            "impact_degree_level"
        )
    )


    content_nature = normalize_content_nature(
        article.get(
            "content_nature"
        )
    )

    equity_relevance = normalize_equity_relevance(
        article.get(
            "equity_relevance"
        )
    )

    is_commentary = content_nature == "commentary"

    is_weak_relevance = equity_relevance == "weak"


    # very_high：任意范围，无条件保留，不受content_nature/
    # equity_relevance影响——真正的黑天鹅级别不该因为
    # 报道形式或相关度评级就被压低
    if degree == "very_high":

        return "keep"


    # high：默认无条件保留，但满足以下任一条件就降级为
    # 低权重池排队，不再自动进日报：
    #   1. content_nature=commentary（评论/分析类软文，
    #      不是具体发生的事件）
    #   2. equity_relevance=weak（跟股票定价关系疏远，
    #      比如非核心官员例行发言、无具体落地政策的框架性讲话）
    if degree == "high":

        if is_commentary or is_weak_relevance:

            return "low_weight"


        return "keep"


    if degree == "medium":

        # v5：不再有BROAD scope例外，medium程度一律进低权重池
        return "low_weight"


    # degree == "low"

    if scope in NARROW_SCOPES:

        return "discard"


    return "low_weight"


# ============================================================
# 新闻标准化
# ============================================================

def prepare_article(article):

    article = dict(
        article
    )


    article.setdefault(
        "category",
        DEFAULT_CATEGORY
    )


    article.setdefault(
        "content_nature",
        "event"
    )


    article.setdefault(
        "equity_relevance",
        "indirect"
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
# 输入：classify_tier() 判定为 low_weight 的候选新闻
#
# 每个分类最多 LOW_SCORE_TOP_N_PER_CATEGORY 条，
# 档位内部按 score（含来源可信度）排序。
#
# 不存在总TOP15，是每个分类各自15条。
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
            DEFAULT_CATEGORY
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
            items[:LOW_SCORE_TOP_N_PER_CATEGORY]
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
# 硬规则评分（仅用于排序展示，不再决定去留）
#    ↓
# event_id去重
#    ↓
# classify_tier() 分层判定：
#   keep        → 无条件保留
#   low_weight  → 各分类Top15
#   discard     → 丢弃
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
                DEFAULT_CATEGORY
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
    # 分层判定：keep / low_weight / discard
    #
    # 用同一个 classify_tier() 判定一次分组，
    # 不用列表成员判断（"in xxx_news"）——
    # 新闻字典按值比较，内容恰好相同的两条不同新闻
    # 会被误判为同一条，导致其中一条哪个池都没进去。
    # ========================================================

    keep_news = []

    low_weight_candidates = []

    discarded_count = 0


    for article in merged_news:

        tier = classify_tier(
            article
        )


        if tier == "keep":

            keep_news.append(
                article
            )


        elif tier == "low_weight":

            low_weight_candidates.append(
                article
            )


        else:

            discarded_count += 1


    # ========================================================
    # 第四步
    # 低权重候选：各分类最多 LOW_SCORE_TOP_N_PER_CATEGORY 条
    # ========================================================

    low_score_selected = (
        select_low_score_news(
            low_weight_candidates
        )
    )


    print(
        f"高权重新闻（keep，无条件保留）："
        f"{len(keep_news)}"
    )


    print(
        f"低权重新闻（每类最多{LOW_SCORE_TOP_N_PER_CATEGORY}条，"
        f"候选池{len(low_weight_candidates)}条）："
        f"{len(low_score_selected)}"
    )


    print(
        f"直接丢弃（窄范围+低程度）："
        f"{discarded_count}"
    )


    # ========================================================
    # 第五步
    # 最终结果
    # ========================================================

    final_news = (

        keep_news
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
            DEFAULT_CATEGORY
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
        DEFAULT_CATEGORY
    )


    if category not in CATEGORIES:

        category = (
            DEFAULT_CATEGORY
        )


    article["category"] = (
        category
    )


    article = calculate_score(
        article
    )


    article["tier"] = classify_tier(
        article
    )


    return article
