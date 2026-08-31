from typing import List, Dict, Any


# ============================================================
# Global Market Agent
# 新闻评分与筛选核心
#
# 核心规则：
# 1. 影响范围：40分
# 2. 影响程度：40分
# 3. 来源可信度：20分
# 4. 总分：100分
# 5. >40分：全部保留，不限数量
# 6. <=40分：每个分类最多10条
# 7. 同一事件：合并，不重复占用展示数量
# ============================================================


# ------------------------------------------------------------
# 来源可信度
# ------------------------------------------------------------

SOURCE_CREDIBILITY = {
    # 官方一手来源
    "official": 20,

    # 权威国际金融媒体
    "major_media": 18,

    # 国际金融机构 / 研究机构
    "financial_institution": 17,

    # 知名个人 / 专家
    "expert": 12,

    # 其他可验证来源
    "other_verified": 8,
}


# ------------------------------------------------------------
# 新闻分类
# ------------------------------------------------------------

VALID_CATEGORIES = [
    "宏观政策",
    "AI/半导体",
    "全球股市",
    "能源商品",
    "外汇",
    "地缘风险",
    "债券利率",
    "贵金属",
    "其他市场事件",
]


# ------------------------------------------------------------
# 计算总分
# ------------------------------------------------------------

def calculate_score(
    impact_scope: int,
    impact_degree: int,
    source_credibility: int,
) -> int:
    """
    计算新闻总分。

    影响范围：0-40
    影响程度：0-40
    来源可信度：0-20
    """

    impact_scope = max(0, min(40, impact_scope))
    impact_degree = max(0, min(40, impact_degree))
    source_credibility = max(0, min(20, source_credibility))

    return impact_scope + impact_degree + source_credibility


# ------------------------------------------------------------
# 判断新闻是否进入金融市场新闻池
# ------------------------------------------------------------

def is_market_relevant(news: Dict[str, Any]) -> bool:
    """
    新闻必须对金融市场具有实际影响力。

    这里不通过关键词数量判断。
    后续可以由 AI / 规则模型给出 market_relevant。
    """

    return news.get("market_relevant", False) is True


# ------------------------------------------------------------
# 获取来源可信度
# ------------------------------------------------------------

def get_source_credibility(news: Dict[str, Any]) -> int:
    """
    根据来源类型获取可信度。

    注意：
    来源可信度只影响20分，
    不直接决定新闻是否重要。
    """

    source_type = news.get("source_type", "other_verified")

    return SOURCE_CREDIBILITY.get(
        source_type,
        SOURCE_CREDIBILITY["other_verified"]
    )


# ------------------------------------------------------------
# 对单条新闻评分
# ------------------------------------------------------------

def score_news(news: Dict[str, Any]) -> Dict[str, Any]:
    """
    对单条新闻进行评分。

    要求：
        impact_scope: 0-40
        impact_degree: 0-40

    来源可信度由 source_type 自动计算。
    """

    impact_scope = int(news.get("impact_scope", 0))
    impact_degree = int(news.get("impact_degree", 0))

    source_credibility = get_source_credibility(news)

    total_score = calculate_score(
        impact_scope,
        impact_degree,
        source_credibility,
    )

    result = dict(news)

    result["impact_scope"] = max(0, min(40, impact_scope))
    result["impact_degree"] = max(0, min(40, impact_degree))
    result["source_credibility"] = source_credibility
    result["score"] = total_score

    return result


# ------------------------------------------------------------
# 同一事件去重 / 合并
# ------------------------------------------------------------

def merge_duplicate_events(
    news_list: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    按 event_id 合并同一事件。

    event_id 应由上游新闻识别模块生成。

    如果多个新闻属于同一事件：
        - 只保留一个事件
        - 优先保留评分最高的新闻
        - 合并来源
        - 合并原文链接
    """

    events = {}

    for news in news_list:

        event_id = news.get("event_id")

        # 没有 event_id 的新闻暂时不合并
        if not event_id:
            unique_key = (
                "unique_"
                + str(len(events))
                + "_"
                + str(news.get("title", ""))
            )

            events[unique_key] = dict(news)
            continue

        if event_id not in events:
            events[event_id] = dict(news)
            continue

        existing = events[event_id]

        # ----------------------------------------------------
        # 保留评分更高的一条作为主新闻
        # ----------------------------------------------------

        if news.get("score", 0) > existing.get("score", 0):

            primary = dict(news)
            secondary = existing

        else:

            primary = existing
            secondary = news

        # ----------------------------------------------------
        # 合并来源
        # ----------------------------------------------------

        sources = []

        for item in [
            primary.get("source"),
            secondary.get("source"),
        ]:

            if item and item not in sources:
                sources.append(item)

        primary["sources"] = sources

        # ----------------------------------------------------
        # 合并原文链接
        # ----------------------------------------------------

        links = []

        for item in [
            primary.get("url"),
            secondary.get("url"),
        ]:

            if item and item not in links:
                links.append(item)

        primary["urls"] = links

        events[event_id] = primary

    return list(events.values())


# ------------------------------------------------------------
# 新闻排序
# ------------------------------------------------------------

def sort_news(news_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    按总分从高到低排序。
    """

    return sorted(
        news_list,
        key=lambda x: x.get("score", 0),
        reverse=True,
    )


# ------------------------------------------------------------
# 分类
# ------------------------------------------------------------

def group_by_category(
    news_list: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    按事件本身所属分类进行归类。

    注意：
    这里不负责判断分类。

    分类结果应该由上游 AI / 事件分析模块提供：
        news["category"]

    本模块只负责整理。
    """

    grouped = {}

    for category in VALID_CATEGORIES:
        grouped[category] = []

    for news in news_list:

        category = news.get(
            "category",
            "其他市场事件"
        )

        if category not in VALID_CATEGORIES:
            category = "其他市场事件"

        grouped[category].append(news)

    return grouped


# ------------------------------------------------------------
# 最终新闻筛选
# ------------------------------------------------------------

def select_news(
    news_list: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    最终新闻展示规则：

    1. 先过滤不具有金融市场实际影响力的新闻
    2. 对新闻进行评分
    3. 同一事件合并
    4. 按分类整理
    5. >40分：
       全部保留，不受数量限制
    6. <=40分：
       每个分类最多10条
    7. 不足10条不强行补足
    """

    # --------------------------------------------------------
    # 1. 市场影响力初筛
    # --------------------------------------------------------

    relevant_news = [
        news
        for news in news_list
        if is_market_relevant(news)
    ]

    # --------------------------------------------------------
    # 2. 评分
    # --------------------------------------------------------

    scored_news = [
        score_news(news)
        for news in relevant_news
    ]

    # --------------------------------------------------------
    # 3. 同事件合并
    # --------------------------------------------------------

    merged_news = merge_duplicate_events(scored_news)

    # --------------------------------------------------------
    # 4. 分类
    # --------------------------------------------------------

    grouped = group_by_category(merged_news)

    final_result = {}

    # --------------------------------------------------------
    # 5. 每个分类执行展示规则
    # --------------------------------------------------------

    for category, items in grouped.items():

        # 先按评分降序
        items = sort_news(items)

        high_weight = [
            item
            for item in items
            if item.get("score", 0) > 40
        ]

        low_weight = [
            item
            for item in items
            if item.get("score", 0) <= 40
        ]

        # 高权重全部保留
        selected_low_weight = low_weight[:10]

        final_items = high_weight + selected_low_weight

        # 最终再次排序
        final_items = sort_news(final_items)

        if final_items:
            final_result[category] = final_items

    return final_result


# ------------------------------------------------------------
# 调试输出
# ------------------------------------------------------------

def print_news_result(
    result: Dict[str, List[Dict[str, Any]]]
) -> None:

    print("\n")
    print("=" * 70)
    print("          全球金融市场重大事件")
    print("=" * 70)

    total = 0

    for category, news_list in result.items():

        print(f"\n【{category}】")

        for index, news in enumerate(news_list, 1):

            total += 1

            print(
                f"{index}. "
                f"{news.get('title', '无标题')}"
            )

            print(
                f"   评分：{news.get('score', 0)} "
                f"(范围 {news.get('impact_scope', 0)} + "
                f"程度 {news.get('impact_degree', 0)} + "
                f"来源 {news.get('source_credibility', 0)})"
            )

            print(
                f"   来源：{news.get('source', '未知')}"
            )

            print(
                f"   时间：{news.get('published_at', '未知')}"
            )

            print(
                f"   链接：{news.get('url', '无')}"
            )

    print("\n" + "=" * 70)
    print(f"新闻总数：{total}")
    print("=" * 70)
