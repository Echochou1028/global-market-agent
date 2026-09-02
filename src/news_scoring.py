from collections import defaultdict
from datetime import datetime


# ============================================================
# 全球金融市场日报
# news_scoring.py
#
# 职责：
# 1. 接收 Groq AI 新闻分析结果
# 2. 执行确定性的评分规则
# 3. 执行同一事件合并
# 4. 执行最终新闻展示规则
# 5. 执行最终排序
#
# 最终评分：
# 影响范围        40分
# 影响程度        40分
# 来源可信度      20分
# ----------------
# 总分            100分
# ============================================================

# ============================================================
# 新闻分类（3类分类基准，与 ai_news_analyzer.py 保持一致）
# ============================================================

CATEGORIES = [
    "宏观、政策与地缘",
    "市场与资产",
    "公司、行业与研报",
]

DEFAULT_CATEGORY = "公司、行业与研报"


# ============================================================
# 来源可信度 (满分 20分)
#
# 根据项目最新确定的四级优先级信源配置：
# - 第一优先级（官方/交易所一手）：20分
# - 第二优先级（全球权威金融媒体）：18 - 19分
# - 第三优先级（国际金融机构）：20分
# - 第四优先级（知名个人）：预留接口（默认不抓取/0分）
# ============================================================

SOURCE_CREDIBILITY = {
    # --------------------------------------------------------
    # 第一优先级：官方 / 交易所一手信息源 (20分)
    # --------------------------------------------------------
    "Federal Reserve": 20,
    "U.S. Treasury": 20,
    "U.S. Department of Treasury": 20,
    "SEC": 20,
    "U.S. Securities and Exchange Commission": 20,
    "BEA": 20,
    "Bureau of Economic Analysis": 20,
    "CSRC": 20,
    "China Securities Regulatory Commission": 20,
    "中国证监会": 20,
    "证监会": 20,
    "HKEX": 20,
    "Hong Kong Exchanges and Clearing": 20,
    "香港交易所": 20,
    "披露易": 20,
    "NYSE": 20,
    "New York Stock Exchange": 20,
    "CME": 20,
    "CME Group": 20,
    "芝加哥商品交易所": 20,
    "CNINFO": 20,
    "巨潮资讯": 20,
    "巨潮资讯网": 20,
    "SSE": 20,
    "Shanghai Stock Exchange": 20,
    "上海证券交易所": 20,
    "上交所": 20,
    "SZSE": 20,
    "Shenzhen Stock Exchange": 20,
    "深圳证券交易所": 20,
    "深交所": 20,
    "BSE": 20,
    "Beijing Stock Exchange": 20,
    "北京证券交易所": 20,
    "北交所": 20,
    # --------------------------------------------------------
    # 第二优先级：全球权威金融媒体 (18-19分)
    # --------------------------------------------------------
    "Reuters": 19,
    "路透社": 19,
    "CNBC": 18,
    "CNBC Markets": 18,
    "CNBC Finance": 18,
    "CNBC World News": 18,
    "CNBC Top News": 18,
    "Xinhua": 18,
    "Xinhua News": 18,
    "新华社": 18,
    "新华网": 18,
    # --------------------------------------------------------
    # 第三优先级：国际金融机构 (20分)
    # --------------------------------------------------------
    "IMF": 20,
    "International Monetary Fund": 20,
    "BIS": 20,
    "Bank for International Settlements": 20,
    "World Bank": 20,
    "世界银行": 20,
    # --------------------------------------------------------
    # 第四优先级：知名个人（预留扩展接口）
    # --------------------------------------------------------
    # "Elon Musk": 10,
    # "Warren Buffett": 10,
}


# 未知来源默认地板分
UNKNOWN_SOURCE_CREDIBILITY = 5


# ============================================================
# 影响范围与程度评分映射
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

IMPACT_DEGREE_SCORES = {
    "very_high": 40,
    "high": 30,
    "medium": 20,
    "low": 10,
}

BROAD_SCOPES = {"global", "multi_region"}
MID_SCOPES = {"regional", "country"}
NARROW_SCOPES = {"industry", "company", "limited"}

LOW_SCORE_TOP_N_PER_CATEGORY = 15


# ============================================================
# 工具函数
# ============================================================

def normalize_text(text):
    if not text:
        return ""
    return str(text).strip()


def get_source_credibility(source):
    """根据信源名称获取可信度评分（支持原生信源与 RSSHub 转制信源的模糊识别）"""
    if not source:
        return 0

    source_clean = normalize_text(source)

    # 1. 精确匹配
    if source_clean in SOURCE_CREDIBILITY:
        return SOURCE_CREDIBILITY[source_clean]

    # 2. 模糊匹配（兼容 RSSHub 抓取后可能包含的中文或变体）
    source_lower = source_clean.lower()
    for name, score in SOURCE_CREDIBILITY.items():
        if name.lower() in source_lower:
            return score

    # 3. 未知来源处理
    return UNKNOWN_SOURCE_CREDIBILITY


def normalize_impact_scope(value):
    if value is None:
        return "limited"

    value = str(value).strip().lower()

    aliases = {
        "global": "global",
        "worldwide": "global",
        "global_market": "global",
        "multi_region": "multi_region",
        "multi-regional": "multi_region",
        "multiple_regions": "multi_region",
        "regional": "regional",
        "country": "country",
        "national": "country",
        "single_country": "country",
        "industry": "industry",
        "sector": "industry",
        "company": "company",
        "single_company": "company",
        "limited": "limited",
        "local": "limited",
    }

    return aliases.get(value, "limited")


def normalize_impact_degree(value):
    if value is None:
        return "low"

    value = str(value).strip().lower()

    aliases = {
        "very_high": "very_high",
        "very-high": "very_high",
        "critical": "very_high",
        "extreme": "very_high",
        "high": "high",
        "major": "high",
        "medium": "medium",
        "moderate": "medium",
        "low": "low",
        "minor": "low",
    }

    return aliases.get(value, "low")


def score_impact_scope(article):
    level = normalize_impact_scope(article.get("impact_scope_level"))
    return IMPACT_SCOPE_SCORES.get(level, 4)


def score_impact_degree(article):
    level = normalize_impact_degree(article.get("impact_degree_level"))
    return IMPACT_DEGREE_SCORES.get(level, 10)


# ============================================================
# 评分计算 (仅用于同档内排序)
# ============================================================

def calculate_score(article):
    impact_scope = score_impact_scope(article)
    impact_degree = score_impact_degree(article)
    source_credibility = get_source_credibility(article.get("source", ""))

    impact_scope = min(max(impact_scope, 0), 40)
    impact_degree = min(max(impact_degree, 0), 40)
    source_credibility = min(max(source_credibility, 0), 20)

    total_score = impact_scope + impact_degree + source_credibility

    article["impact_scope"] = impact_scope
    article["impact_degree"] = impact_degree
    article["source_credibility"] = source_credibility
    article["score"] = total_score

    return article


# ============================================================
# 分层硬规则门槛 (classify_tier)
# ============================================================

def classify_tier(article):
    scope = normalize_impact_scope(article.get("impact_scope_level"))
    degree = normalize_impact_degree(article.get("impact_degree_level"))

    if degree == "very_high":
        return "keep"

    if degree == "high":
        return "keep"

    if degree == "medium":
        if scope in BROAD_SCOPES:
            return "keep"
        return "low_weight"

    if scope in NARROW_SCOPES:
        return "discard"

    return "low_weight"


def prepare_article(article):
    article = dict(article)
    article.setdefault("category", DEFAULT_CATEGORY)
    article.setdefault("event_id", None)
    article.setdefault("market_relevant", False)
    article.setdefault("score", 0)
    return article


def get_event_id(article):
    event_id = article.get("event_id")
    if event_id:
        return normalize_text(event_id).lower()

    title = normalize_text(article.get("title", "")).lower()
    if title:
        return f"title:{title}"

    return None


# ============================================================
# 同事件去重与合并
# ============================================================

def merge_same_events(articles):
    groups = defaultdict(list)

    for article in articles:
        event_id = get_event_id(article)
        if event_id is None:
            event_id = f"article:{id(article)}"
        groups[event_id].append(article)

    merged = []

    for event_id, items in groups.items():
        items.sort(
            key=lambda x: (
                x.get("score", 0),
                x.get("published_at") or datetime.min,
            ),
            reverse=True,
        )

        primary = dict(items[0])
        sources = []
        urls = []

        for item in items:
            source = item.get("source")
            url = item.get("url")

            if source and source not in sources:
                sources.append(source)
            if url and url not in urls:
                urls.append(url)

        primary["sources"] = sources
        primary["urls"] = urls
        primary["merged_count"] = len(items)
        primary["event_id"] = event_id

        merged.append(primary)

    return merged


def select_low_score_news(articles):
    category_groups = defaultdict(list)

    for article in articles:
        category = article.get("category", DEFAULT_CATEGORY)
        category_groups[category].append(article)

    selected = []

    for category, items in category_groups.items():
        items.sort(
            key=lambda x: (
                x.get("score", 0),
                x.get("published_at") or datetime.min,
            ),
            reverse=True,
        )
        selected.extend(items[:LOW_SCORE_TOP_N_PER_CATEGORY])

    return selected


def sort_news(articles):
    return sorted(
        articles,
        key=lambda x: (
            x.get("score", 0),
            x.get("published_at") or datetime.min,
        ),
        reverse=True,
    )


# ============================================================
# 主入口筛选函数
# ============================================================

def select_news(analyzed_news):
    print("\n============================================================")
    print("开始执行新闻硬规则评分与筛选")
    print("============================================================")

    market_candidates = []

    for raw_article in analyzed_news:
        article = prepare_article(raw_article)

        if not article.get("source"):
            continue

        if not article.get("url"):
            continue

        if not article.get("published_at"):
            continue

        if article.get("market_relevant", False) is not True:
            continue

        category = article.get("category")
        if category not in CATEGORIES:
            category = DEFAULT_CATEGORY

        article["category"] = category
        article = calculate_score(article)
        market_candidates.append(article)

    print(f"市场相关候选新闻：{len(market_candidates)}")

    merged_news = merge_same_events(market_candidates)
    print(f"同一事件合并后：{len(merged_news)}")

    keep_news = []
    low_weight_candidates = []
    discarded_count = 0

    for article in merged_news:
        tier = classify_tier(article)

        if tier == "keep":
            keep_news.append(article)
        elif tier == "low_weight":
            low_weight_candidates.append(article)
        else:
            discarded_count += 1

    low_score_selected = select_low_score_news(low_weight_candidates)

    print(f"高权重新闻（keep，无条件保留）：{len(keep_news)}")
    print(f"低权重新闻（每类最多{LOW_SCORE_TOP_N_PER_CATEGORY}条，候选池{len(low_weight_candidates)}条）：{len(low_score_selected)}")
    print(f"直接丢弃（窄范围+低程度）：{discarded_count}")

    final_news = keep_news + low_score_selected
    final_news = sort_news(final_news)

    print(f"最终新闻数量：{len(final_news)}")
    print("============================================================")

    result = defaultdict(list)
    for article in final_news:
        category = article.get("category", DEFAULT_CATEGORY)
        result[category].append(article)

    return dict(result)


def score_single_article(article):
    article = prepare_article(article)

    if article.get("market_relevant", False) is not True:
        article["market_relevant"] = False
        return article

    category = article.get("category", DEFAULT_CATEGORY)
    if category not in CATEGORIES:
        category = DEFAULT_CATEGORY

    article["category"] = category
    article = calculate_score(article)
    article["tier"] = classify_tier(article)

    return article
