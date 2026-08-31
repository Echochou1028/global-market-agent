import re
from collections import defaultdict
from difflib import SequenceMatcher


# ============================================================
# 全球金融市场日报
# 新闻评分、分类、去重与筛选模块
#
# 最终规则：
#
# 1. 只保留对金融市场具有实际影响力的信息
#
# 2. 分类依据：
#    按“事件本身是什么”分类
#    不按照关键词命中数量决定分类
#
# 3. 评分：
#    影响范围      0-40
#    影响程度      0-40
#    来源可信度    0-20
#    总分          0-100
#
# 4. 取消 TOP10 总量限制
#
# 5. 高权重：
#    >40 分全部保留
#
# 6. 低权重：
#    <=40 分
#    按分类分别执行 Top10
#
# 7. 不足10条：
#    有几条展示几条
#    不强行补足
#
# 8. 同一事件：
#    去重、合并
#    不重复占用展示数量
#
# 9. 来源：
#    来源只影响“来源可信度”20分
#    来源本身不能决定新闻重要性
#
# 10. 真实数据原则：
#     不编造新闻
#     不编造评分依据之外的事实
#     保留真实来源和原文链接
#
# ============================================================


# ============================================================
# 分类
# ============================================================

CATEGORIES = [
    "宏观经济与央行政策",
    "全球股市",
    "能源与大宗商品",
    "外汇与债券",
    "地缘政治与制裁",
    "AI与半导体",
    "公司重大事件",
    "其他市场事件",
]


# ============================================================
# 来源可信度
#
# 注意：
# 来源只决定20分以内的可信度。
# 不决定影响范围和影响程度。
# ============================================================

SOURCE_CREDIBILITY = {

    # 权威财经媒体
    "CNBC Markets": 18,
    "CNBC Finance": 18,
    "CNBC World News": 17,
    "CNBC Top News": 17,

    # 国际主流媒体
    "BBC Business": 17,

}


DEFAULT_SOURCE_CREDIBILITY = 12


# ============================================================
# 文本标准化
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text).lower()

    # 删除 HTML
    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    # 删除 URL
    text = re.sub(
        r"https?://\S+",
        " ",
        text
    )

    # 统一标点
    text = re.sub(
        r"[^a-z0-9\u4e00-\u9fff\s]",
        " ",
        text
    )

    # 合并空格
    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


# ============================================================
# 判断关键词
#
# 这里只用于辅助识别“事件主题”
# 不用于统计关键词命中数量评分。
# ============================================================

def contains_any(text, keywords):

    text = normalize_text(text)

    for keyword in keywords:

        keyword = normalize_text(keyword)

        if not keyword:
            continue

        if keyword in text:
            return True

    return False


# ============================================================
# 分类规则
#
# 重要：
#
# 不是：
#     命中几个关键词 = 哪个分类
#
# 而是：
#     根据标题 + 核心事实判断事件的主要性质。
#
# 顺序体现事件性质的优先级。
# ============================================================


# ------------------------------------------------------------
# 1. 宏观经济与央行政策
# ------------------------------------------------------------

MACRO_KEYWORDS = [

    "federal reserve",
    "fed",
    "fomc",
    "central bank",
    "interest rate",
    "rate cut",
    "rate hike",
    "monetary policy",
    "inflation",
    "cpi",
    "ppi",
    "payroll",
    "employment",
    "unemployment",
    "gdp",
    "economic growth",
    "economic outlook",
    "jobs report",
    "nonfarm payroll",
    "treasury yields",
]


# ------------------------------------------------------------
# 2. AI与半导体
# ------------------------------------------------------------

AI_SEMICONDUCTOR_KEYWORDS = [

    "artificial intelligence",
    "ai",
    "gpu",
    "semiconductor",
    "semiconductors",
    "chip",
    "chips",
    "hbm",
    "memory",
    "optical networking",
    "optical",
    "data center",
    "data centre",
    "foundry",

    "nvidia",
    "amd",
    "broadcom",
    "intel",
    "tsmc",
    "asml",
    "micron",
    "qualcomm",
]


# ------------------------------------------------------------
# 3. 能源与大宗商品
# ------------------------------------------------------------

ENERGY_COMMODITY_KEYWORDS = [

    "oil",
    "crude",
    "brent",
    "wti",
    "opec",
    "natural gas",
    "gas prices",
    "gold",
    "silver",
    "copper",
    "commodity",
    "commodities",
    "metal prices",
    "oil reserves",
    "oil supply",
    "oil production",
    "energy market",
]


# ------------------------------------------------------------
# 4. 外汇与债券
# ------------------------------------------------------------

FX_BOND_KEYWORDS = [

    "dollar",
    "usd",
    "yen",
    "yuan",
    "renminbi",
    "euro",
    "pound",
    "sterling",
    "forex",
    "foreign exchange",
    "currency",
    "treasury",
    "bond",
    "bonds",
    "bond yield",
    "bond yields",
]


# ------------------------------------------------------------
# 5. 地缘政治与制裁
# ------------------------------------------------------------

GEOPOLITICAL_KEYWORDS = [

    "war",
    "conflict",
    "military",
    "missile",
    "attack",
    "strikes",
    "strike",
    "ceasefire",
    "geopolitical",

    "sanction",
    "sanctions",
    "export controls",
    "export restriction",

    "trade war",
    "tariff",
    "tariffs",
    "trade dispute",

    "iran",
    "israel",
    "russia",
    "ukraine",
    "taiwan",
    "middle east",

    "hormuz",
    "strait of hormuz",
]


# ------------------------------------------------------------
# 6. 公司重大事件
# ------------------------------------------------------------

COMPANY_KEYWORDS = [

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
    "initial public offering",
    "ceo",
    "chief executive",
    "executive exit",
    "regulatory approval",
    "regulatory nod",
    "shares rise",
    "shares fall",
    "shares slide",
    "shares surge",
]


# ------------------------------------------------------------
# 7. 全球股市
# ------------------------------------------------------------

EQUITY_KEYWORDS = [

    "stock market",
    "stocks",
    "equity",
    "equities",
    "shares",
    "nasdaq",
    "s&p 500",
    "dow jones",
    "nikkei",
    "kospi",
    "hang seng",
    "vix",
    "market rally",
    "market selloff",
    "selloff",
    "sell-off",
    "market crash",
]


# ============================================================
# 事件性质识别
# ============================================================

def classify_event(article):

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


    # ========================================================
    # 第一优先级：
    # 事件明确属于宏观政策 / 央行
    # ========================================================

    if contains_any(
        text,
        MACRO_KEYWORDS
    ):

        return "宏观经济与央行政策"


    # ========================================================
    # 第二优先级：
    # AI / 半导体产业事件
    #
    # 注意：
    # 如果文章只是泛泛讨论科技股，
    # 不一定属于这里。
    # ========================================================

    if contains_any(
        text,
        AI_SEMICONDUCTOR_KEYWORDS
    ):

        # 必须具有明确 AI / 半导体事件属性
        if contains_any(
            text,
            [
                "nvidia",
                "amd",
                "broadcom",
                "intel",
                "tsmc",
                "asml",
                "micron",
                "qualcomm",
                "semiconductor",
                "chip",
                "gpu",
                "hbm",
                "artificial intelligence",
                "ai chip",
                "data center",
            ]
        ):

            return "AI与半导体"


    # ========================================================
    # 第三优先级：
    # 能源 / 大宗商品
    # ========================================================

    if contains_any(
        text,
        ENERGY_COMMODITY_KEYWORDS
    ):

        return "能源与大宗商品"


    # ========================================================
    # 第四优先级：
    # 外汇 / 债券
    # ========================================================

    if contains_any(
        text,
        FX_BOND_KEYWORDS
    ):

        return "外汇与债券"


    # ========================================================
    # 第五优先级：
    # 地缘政治 / 制裁 / 贸易
    # ========================================================

    if contains_any(
        text,
        GEOPOLITICAL_KEYWORDS
    ):

        return "地缘政治与制裁"


    # ========================================================
    # 第六优先级：
    # 公司重大事件
    # ========================================================

    if contains_any(
        text,
        COMPANY_KEYWORDS
    ):

        return "公司重大事件"


    # ========================================================
    # 第七优先级：
    # 全球股市
    # ========================================================

    if contains_any(
        text,
        EQUITY_KEYWORDS
    ):

        return "全球股市"


    # ========================================================
    # 无法准确归类
    # ========================================================

    return "其他市场事件"


# ============================================================
# 判断是否具有实际金融市场影响
#
# 注意：
#
# 这是“市场影响力初筛”，
# 不是最终评分。
#
# 不能因为来源权威就直接进入。
# ============================================================


MARKET_IMPACT_KEYWORDS = [

    # 宏观
    "fed",
    "federal reserve",
    "fomc",
    "central bank",
    "interest rate",
    "rate cut",
    "rate hike",
    "inflation",
    "cpi",
    "ppi",
    "payroll",
    "employment",
    "gdp",

    # 市场
    "stock market",
    "stocks",
    "equities",
    "shares",
    "nasdaq",
    "s&p 500",
    "dow jones",
    "nikkei",
    "kospi",
    "hang seng",
    "vix",

    # 公司
    "earnings",
    "profit",
    "revenue",
    "guidance",
    "ipo",
    "acquisition",
    "merger",
    "bankruptcy",
    "ceo",
    "shares rise",
    "shares fall",
    "shares slide",
    "shares surge",

    # AI
    "nvidia",
    "amd",
    "broadcom",
    "semiconductor",
    "chip",
    "gpu",
    "hbm",
    "artificial intelligence",

    # 能源
    "oil",
    "crude",
    "brent",
    "wti",
    "opec",
    "natural gas",
    "gold",
    "silver",
    "copper",

    # 外汇债券
    "dollar",
    "yen",
    "yuan",
    "forex",
    "currency",
    "treasury",
    "bond",
    "yield",

    # 国际贸易
    "tariff",
    "tariffs",
    "trade war",
    "sanctions",
    "export controls",

    # 地缘
    "war",
    "conflict",
    "military",
    "attack",
    "strike",
    "ceasefire",
    "iran",
    "israel",
    "russia",
    "ukraine",
    "taiwan",
    "middle east",
    "hormuz",
]


def is_market_impactful(article):

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
    # 明显具有金融市场事件特征
    # --------------------------------------------------------

    return contains_any(
        text,
        MARKET_IMPACT_KEYWORDS
    )


# ============================================================
# 影响范围评分
#
# 0-40
#
# 重点看：
# 事件影响到多少市场 / 国家 / 资产类别。
#
# 不看来源。
# 不统计关键词数量。
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


    # 全球级宏观政策
    if contains_any(
        text,
        [
            "federal reserve",
            "fed",
            "fomc",
            "global economy",
            "global markets",
            "world economy",
        ]
    ):

        return 40


    # 全球性战争 / 大规模地缘冲突
    if contains_any(
        text,
        [
            "war",
            "iran",
            "hormuz",
            "russia",
            "ukraine",
            "middle east",
        ]
    ):

        return 40


    # 跨国贸易政策
    if contains_any(
        text,
        [
            "trade war",
            "tariffs",
            "sanctions",
            "export controls",
        ]
    ):

        return 40


    # 能源供给 / 国际大宗商品
    if contains_any(
        text,
        [
            "oil",
            "crude",
            "brent",
            "wti",
            "opec",
            "oil supply",
            "oil reserves",
        ]
    ):

        return 40


    # 全球AI / 半导体龙头
    if contains_any(
        text,
        [
            "nvidia",
            "tsmc",
            "broadcom",
            "semiconductor",
            "gpu",
            "hbm",
        ]
    ):

        return 28


    # 大型公司重大事件
    if contains_any(
        text,
        [
            "ipo",
            "acquisition",
            "merger",
            "bankruptcy",
            "earnings",
            "ceo",
        ]
    ):

        return 28


    # 一般股票市场事件
    if contains_any(
        text,
        EQUITY_KEYWORDS
    ):

        return 20


    # 一般金融事件
    return 10


# ============================================================
# 影响程度评分
#
# 0-40
#
# 核心原则：
#
# 影响范围 ≠ 影响程度
#
# 影响范围：
#     波及多大范围
#
# 影响程度：
#     对相关市场造成多强的实际冲击
#
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
    # 已经出现明确军事冲突 / 实际袭击
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "exchange strikes",
            "actual strikes",
            "armed conflict",
            "military strikes",
            "missile attack",
            "major attack",
        ]
    ):

        return 36


    # --------------------------------------------------------
    # 重大贸易战 / 关税冲击
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "trade war",
            "new tariff",
            "tariff walls",
            "tariffs",
        ]
    ):

        return 36


    # --------------------------------------------------------
    # 重大央行政策变化
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "rate hike",
            "rate cut",
            "hawkish",
            "dovish",
            "monetary policy",
            "fed policy",
        ]
    ):

        return 32


    # --------------------------------------------------------
    # 能源供应重大变化
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "oil supply",
            "oil reserves",
            "opec",
            "strategic oil",
            "hormuz",
        ]
    ):

        return 30


    # --------------------------------------------------------
    # 公司重大业绩 / 管理层变化
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "earnings",
            "financial results",
            "bankruptcy",
            "acquisition",
            "merger",
            "surprise exit",
            "ceo",
        ]
    ):

        return 30


    # --------------------------------------------------------
    # 一般市场价格变化
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "shares slide",
            "shares fall",
            "shares surge",
            "shares rise",
            "market selloff",
            "market rally",
        ]
    ):

        return 20


    # --------------------------------------------------------
    # 分析 / 观点类
    #
    # 如果只是分析未来可能影响，
    # 不能给过高影响程度。
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "analyst",
            "analysts",
            "analysis",
            "analyst roundup",
            "look to the fed for clues",
            "watching",
            "outlook",
        ]
    ):

        return 10


    return 10


# ============================================================
# 来源可信度
#
# 0-20
#
# 来源只影响这一项。
# ============================================================

def score_source_credibility(article):

    source = article.get(
        "source",
        ""
    )

    score = SOURCE_CREDIBILITY.get(
        source,
        DEFAULT_SOURCE_CREDIBILITY
    )

    return min(
        max(
            int(score),
            0
        ),
        20
    )


# ============================================================
# 总分
# ============================================================

def calculate_score(article):

    scope = score_impact_scope(
        article
    )

    degree = score_impact_degree(
        article
    )

    credibility = score_source_credibility(
        article
    )

    total = (
        scope
        + degree
        + credibility
    )

    return {

        "impact_scope":
            scope,

        "impact_degree":
            degree,

        "source_credibility":
            credibility,

        "score":
            min(
                total,
                100
            ),

    }


# ============================================================
# 标题相似度
# ============================================================

def title_similarity(
    title_a,
    title_b
):

    a = normalize_text(
        title_a
    )

    b = normalize_text(
        title_b
    )

    if not a or not b:

        return 0.0

    return SequenceMatcher(
        None,
        a,
        b
    ).ratio()


# ============================================================
# 事件关键词
#
# 仅用于判断“是否可能是同一事件”
# 不用于评分。
# ============================================================

EVENT_KEYWORDS = [

    "fed",
    "federal reserve",
    "rate hike",
    "rate cut",

    "iran",
    "hormuz",
    "israel",
    "russia",
    "ukraine",

    "trade war",
    "tariffs",
    "sanctions",

    "oil",
    "opec",
    "venezuela",

    "nvidia",
    "amd",
    "broadcom",
    "tsmc",

    "byd",

    "ipo",
    "jio",

    "hdfc",
    "ceo",

]


def extract_event_keywords(article):

    text = normalize_text(
        f"{article.get('title', '')} "
        f"{article.get('summary', '')}"
    )

    result = set()

    for keyword in EVENT_KEYWORDS:

        keyword_normalized = normalize_text(
            keyword
        )

        if keyword_normalized in text:

            result.add(
                keyword_normalized
            )

    return result


# ============================================================
# 判断是否为同一事件
# ============================================================

def is_same_event(
    article_a,
    article_b
):

    # --------------------------------------------------------
    # 标题高度相似
    # --------------------------------------------------------

    similarity = title_similarity(
        article_a.get(
            "title",
            ""
        ),
        article_b.get(
            "title",
            ""
        )
    )

    if similarity >= 0.78:

        return True


    # --------------------------------------------------------
    # 共同事件关键词
    # --------------------------------------------------------

    keywords_a = extract_event_keywords(
        article_a
    )

    keywords_b = extract_event_keywords(
        article_b
    )

    common = (
        keywords_a
        & keywords_b
    )


    # 至少两个共同事件特征
    # 才认为可能是同一事件
    if len(common) >= 2:

        # 标题或摘要至少有一定相似性
        text_a = normalize_text(
            f"{article_a.get('title', '')} "
            f"{article_a.get('summary', '')}"
        )

        text_b = normalize_text(
            f"{article_b.get('title', '')} "
            f"{article_b.get('summary', '')}"
        )

        text_similarity = SequenceMatcher(
            None,
            text_a,
            text_b
        ).ratio()

        if text_similarity >= 0.30:

            return True


    return False


# ============================================================
# 同一事件合并
# ============================================================

def merge_same_events(articles):

    if not articles:

        return []


    groups = []


    for article in articles:

        matched_group = None


        for group in groups:

            representative = group[0]

            if is_same_event(
                article,
                representative
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

        # ----------------------------------------------------
        # 选择最优代表新闻
        #
        # 优先：
        # 1. 来源可信度
        # 2. 发布时间
        #
        # 不使用“来源决定重要性”
        # ----------------------------------------------------

        representative = max(
            group,
            key=lambda x: (
                score_source_credibility(x),
                x.get(
                    "published_at"
                )
            )
        )


        # ----------------------------------------------------
        # 保留所有真实来源
        # ----------------------------------------------------

        sources = []

        urls = []


        for item in group:

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


        representative = dict(
            representative
        )


        representative[
            "sources"
        ] = sources


        representative[
            "source_urls"
        ] = urls


        representative[
            "event_sources_count"
        ] = len(
            group
        )


        merged.append(
            representative
        )


    return merged


# ============================================================
# 对新闻进行评分
# ============================================================

def score_articles(articles):

    scored = []


    for article in articles:

        article = dict(
            article
        )


        scores = calculate_score(
            article
        )


        article.update(
            scores
        )


        scored.append(
            article
        )


    return scored


# ============================================================
# 最终筛选
# ============================================================

def select_news(
    raw_news
):

    if not raw_news:

        return {
            category: []
            for category in CATEGORIES
        }


    # ========================================================
    # 第一步
    # 市场影响力初筛
    # ========================================================

    market_news = []


    for article in raw_news:

        if not is_market_impactful(
            article
        ):

            continue

        market_news.append(
            article
        )


    print(
        f"\n市场相关候选新闻："
        f"{len(market_news)}"
    )


    # ========================================================
    # 第二步
    # 同一事件合并
    # ========================================================

    merged_news = merge_same_events(
        market_news
    )


    print(
        f"同一事件合并后："
        f"{len(merged_news)}"
    )


    # ========================================================
    # 第三步
    # 事件分类
    #
    # 注意：
    # 分类不参与评分。
    # ========================================================

    for article in merged_news:

        article[
            "category"
        ] = classify_event(
            article
        )


    # ========================================================
    # 第四步
    # 三维评分
    # ========================================================

    scored_news = score_articles(
        merged_news
    )


    # ========================================================
    # 第五步
    # 分离高权重 / 低权重
    # ========================================================

    high_weight = []

    low_weight = []


    for article in scored_news:

        score = article.get(
            "score",
            0
        )


        if score > 40:

            high_weight.append(
                article
            )

        else:

            low_weight.append(
                article
            )


    print(
        f"高权重新闻（>40）："
        f"{len(high_weight)}"
    )

    print(
        f"低权重新闻（<=40）："
        f"{len(low_weight)}"
    )


    # ========================================================
    # 第六步
    # 高权重全部保留
    #
    # 绝对没有总量TOP10。
    # ========================================================

    final_news = list(
        high_weight
    )


    # ========================================================
    # 第七步
    # 低权重按分类 Top10
    #
    # 每个分类最多10条。
    # 不足10条不补。
    # ========================================================

    low_by_category = defaultdict(
        list
    )


    for article in low_weight:

        category = article.get(
            "category",
            "其他市场事件"
        )

        low_by_category[
            category
        ].append(
            article
        )


    for category, articles in low_by_category.items():

        articles.sort(
            key=lambda x: (
                x.get(
                    "score",
                    0
                ),
                x.get(
                    "published_at"
                )
            ),
            reverse=True
        )


        final_news.extend(
            articles[:10]
        )


    # ========================================================
    # 第八步
    # 最终按总分排序
    # ========================================================

    final_news.sort(
        key=lambda x: (
            x.get(
                "score",
                0
            ),
            x.get(
                "published_at"
            )
        ),
        reverse=True
    )


    # ========================================================
    # 第九步
    # 按分类返回
    # ========================================================

    result = {

        category: []

        for category in CATEGORIES

    }


    for article in final_news:

        category = article.get(
            "category",
            "其他市场事件"
        )


        if category not in result:

            result[
                "其他市场事件"
            ].append(
                article
            )

        else:

            result[
                category
            ].append(
                article
            )


    print(
        f"最终新闻数量："
        f"{len(final_news)}"
    )


    return result


# ============================================================
# 调试函数
# ============================================================

def validate_result(result):

    all_news = []


    for category, articles in result.items():

        for article in articles:

            all_news.append(
                article
            )


    errors = []


    # --------------------------------------------------------
    # 检查总分
    # --------------------------------------------------------

    for article in all_news:

        score = article.get(
            "score",
            0
        )

        scope = article.get(
            "impact_scope",
            0
        )

        degree = article.get(
            "impact_degree",
            0
        )

        credibility = article.get(
            "source_credibility",
            0
        )


        if scope < 0 or scope > 40:

            errors.append(
                f"影响范围分数异常："
                f"{article.get('title')}"
            )


        if degree < 0 or degree > 40:

            errors.append(
                f"影响程度分数异常："
                f"{article.get('title')}"
            )


        if credibility < 0 or credibility > 20:

            errors.append(
                f"来源可信度分数异常："
                f"{article.get('title')}"
            )


        if score != (
            scope
            + degree
            + credibility
        ):

            errors.append(
                f"总分计算错误："
                f"{article.get('title')}"
            )


        if score > 100:

            errors.append(
                f"总分超过100："
                f"{article.get('title')}"
            )


        if not article.get(
            "source"
        ):

            errors.append(
                f"新闻缺少来源："
                f"{article.get('title')}"
            )


        if not article.get(
            "url"
        ):

            errors.append(
                f"新闻缺少原文链接："
                f"{article.get('title')}"
            )


    # --------------------------------------------------------
    # 检查低权重分类数量
    # --------------------------------------------------------

    for category, articles in result.items():

        low_count = sum(
            1
            for article in articles
            if article.get(
                "score",
                0
            ) <= 40
        )


        if low_count > 10:

            errors.append(
                f"{category} "
                f"低权重新闻超过10条"
            )


    if errors:

        print(
            "\n========== 新闻规则校验 =========="
        )

        for error in errors:

            print(
                f"ERROR: {error}"
            )

        return False


    print(
        "\n========== 新闻规则校验 =========="
    )

    print(
        "PASS：所有新闻符合最终筛选规则"
    )

    return True
