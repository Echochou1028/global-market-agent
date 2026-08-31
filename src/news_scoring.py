import re
from collections import defaultdict
from datetime import datetime


# ============================================================
# 全球金融市场日报
# 新闻评分、事件识别、分类、去重与最终筛选模块
#
# 核心原则
#
# 1. 先判断：
#    新闻是否对金融市场具有实际影响力
#
# 2. 再分类：
#    按“事件本身是什么”分类
#    不按关键词命中数量分类
#
# 3. 评分：
#    影响范围     40分
#    影响程度     40分
#    来源可信度   20分
#    总分         100分
#
# 4. 新闻展示：
#    >40分：全部保留
#    <=40分：按分类Top10
#
# 5. 同一事件：
#    去重、合并，不重复占用展示数量
#
# 6. 来源：
#    来源只影响“来源可信度”
#    不决定新闻本身的重要性
#
# 7. 严禁：
#    AI编造新闻、事件、数据、引用
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
    "AI与半导体",
    "公司重大事件",
    "地缘政治与制裁",
    "其他市场事件",

]


# ============================================================
# 来源可信度
#
# 注意：
# 来源只影响20分中的可信度。
#
# 绝不因为来源权威，就自动提高影响范围或影响程度。
# ============================================================

SOURCE_CREDIBILITY = {

    # --------------------------------------------------------
    # 一手官方 / 官方机构
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
    # 权威国际财经媒体
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
# 低价值 / 明显观点型内容识别
#
# 这些内容不是“一看到就删除”。
#
# 只有当文章本身没有形成明确市场事件，
# 且主要属于投资建议、个人观点、市场评论时，
# 才会被大幅降低影响程度。
# ============================================================

OPINION_PATTERNS = [

    r"\btop analysts suggest\b",
    r"\banalysts suggest\b",
    r"\bstocks to buy\b",
    r"\bstocks to watch\b",
    r"\bdividend stocks\b",
    r"\binvesting club\b",
    r"\bwhat we'?re watching\b",
    r"\bmy view\b",
    r"\bopinion\b",
    r"\bcolumn\b",
    r"\bcommentary\b",
    r"\bmarket outlook\b",
    r"\bstrategy\b",
    r"\binvestment strategy\b",

]


# ============================================================
# 明显不是市场事件的内容
# ============================================================

NON_MARKET_PATTERNS = [

    r"\bcelebrity\b",
    r"\bentertainment\b",
    r"\bmovie\b",
    r"\bmusic\b",
    r"\bsports\b",
    r"\btravel\b",
    r"\brestaurant\b",
    r"\bfood\b",
    r"\blifestyle\b",

]


# ============================================================
# 重大市场事件识别
#
# 注意：
# 这里不是简单统计关键词。
#
# 只有“事件动作 + 市场传导逻辑”成立，
# 才认为具有实际金融市场影响。
# ============================================================

MAJOR_EVENT_PATTERNS = [

    # --------------------------------------------------------
    # 宏观 / 央行
    # --------------------------------------------------------

    r"\bfed\b",
    r"\bfederal reserve\b",
    r"\bfomc\b",
    r"\binterest rate\b",
    r"\brate cut\b",
    r"\brate hike\b",
    r"\bmonetary policy\b",
    r"\binflation\b",
    r"\bcpi\b",
    r"\bppi\b",
    r"\bpayroll\b",
    r"\bunemployment\b",
    r"\bgdp\b",
    r"\bcentral bank\b",
    r"\bjobs report\b",

    # --------------------------------------------------------
    # 市场
    # --------------------------------------------------------

    r"\bstock market\b",
    r"\bmarket selloff\b",
    r"\bmarket rally\b",
    r"\bmarket crash\b",
    r"\bequity markets?\b",
    r"\bnasdaq\b",
    r"\bs&p 500\b",
    r"\bdow jones\b",
    r"\bnikkei\b",
    r"\bkospi\b",
    r"\bh[ae]ng seng\b",
    r"\bvix\b",

    # --------------------------------------------------------
    # 公司 / 财报
    # --------------------------------------------------------

    r"\bearnings\b",
    r"\bquarterly results\b",
    r"\brevenue\b",
    r"\bprofit\b",
    r"\bloss\b",
    r"\bguidance\b",
    r"\bforecast\b",
    r"\bacquisition\b",
    r"\bmerger\b",
    r"\btakeover\b",
    r"\bbankruptcy\b",
    r"\bipo\b",
    r"\bceo\b",
    r"\bshares? (rise|fall|slide|surge|jump|drop)\b",

    # --------------------------------------------------------
    # 能源 / 商品
    # --------------------------------------------------------

    r"\boil\b",
    r"\bcrude\b",
    r"\bbrent\b",
    r"\bwti\b",
    r"\bopec\b",
    r"\bgold\b",
    r"\bsilver\b",
    r"\bcopper\b",
    r"\bnatural gas\b",

    # --------------------------------------------------------
    # 外汇 / 债券
    # --------------------------------------------------------

    r"\bdollar\b",
    r"\byen\b",
    r"\byuan\b",
    r"\bforex\b",
    r"\bcurrency\b",
    r"\btreasury yield\b",
    r"\bbond yield\b",
    r"\bbond market\b",

    # --------------------------------------------------------
    # 贸易 / 制裁
    # --------------------------------------------------------

    r"\btariff\b",
    r"\btariffs\b",
    r"\btrade war\b",
    r"\bsanction\b",
    r"\bsanctions\b",
    r"\bexport controls?\b",
    r"\bexport restrictions?\b",

    # --------------------------------------------------------
    # 地缘政治
    # --------------------------------------------------------

    r"\bwar\b",
    r"\barmed conflict\b",
    r"\bmilitary\b",
    r"\bmissile\b",
    r"\battack\b",
    r"\bstrikes?\b",
    r"\bceasefire\b",
    r"\bgeopolitical\b",
    r"\bescalation\b",

]


# ============================================================
# 事件动作
#
# 用来判断：
# “这到底是不是一个真实发生的市场事件？”
# ============================================================

EVENT_ACTION_PATTERNS = [

    r"\bannounces?\b",
    r"\bannounced\b",
    r"\bapproves?\b",
    r"\bapproved\b",
    r"\bgets regulatory nod\b",
    r"\bsigns?\b",
    r"\bstrikes?\b",
    r"\battacks?\b",
    r"\blaunches?\b",
    r"\bimposes?\b",
    r"\blifts?\b",
    r"\braises?\b",
    r"\bcuts?\b",
    r"\bhikes?\b",
    r"\bfalls?\b",
    r"\brises?\b",
    r"\bslides?\b",
    r"\bsurges?\b",
    r"\bdrops?\b",
    r"\breports?\b",
    r"\breported\b",
    r"\bfiles?\b",
    r"\bdefaults?\b",
    r"\bdeclares?\b",
    r"\bconfirms?\b",
    r"\bdenies?\b",
    r"\bprepares?\b",
    r"\bthreatens?\b",

]


# ============================================================
# 文本清洗
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
    ).strip()

    return text


# ============================================================
# 正则匹配
# ============================================================

def regex_match(
    text,
    patterns
):

    text = normalize_text(text)

    for pattern in patterns:

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        ):

            return True

    return False


# ============================================================
# 来源可信度
# ============================================================

def get_source_credibility(source):

    if not source:

        return 0

    source = str(source).strip()

    # 精确匹配
    if source in SOURCE_CREDIBILITY:

        return SOURCE_CREDIBILITY[source]

    # 模糊匹配
    source_lower = source.lower()

    for name, score in SOURCE_CREDIBILITY.items():

        if name.lower() in source_lower:

            return score

    # 未知来源
    # 不猜测，不给予高可信度
    return 0


# ============================================================
# 判断是否属于明显低价值观点内容
# ============================================================

def is_opinion_article(
    title,
    summary
):

    text = normalize_text(
        f"{title} {summary}"
    )

    return regex_match(
        text,
        OPINION_PATTERNS
    )


# ============================================================
# 判断是否明显不是金融市场内容
# ============================================================

def is_non_market_content(
    title,
    summary
):

    text = normalize_text(
        f"{title} {summary}"
    )

    return regex_match(
        text,
        NON_MARKET_PATTERNS
    )


# ============================================================
# 判断是否具有实际市场影响力
# ============================================================
#
# 这里非常重要：
#
# 不是：
#
#     出现 oil = 金融新闻
#     出现 Fed = 重要新闻
#     出现 stock = 高分新闻
#
# 而是：
#
#     是否存在明确事件
#     +
#     是否存在明确市场传导路径
#
# ============================================================

def has_actual_market_impact(
    article
):

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


    if is_non_market_content(
        title,
        summary
    ):

        return False


    # --------------------------------------------------------
    # 必须至少存在市场相关主题
    # --------------------------------------------------------

    market_topic = regex_match(
        text,
        MAJOR_EVENT_PATTERNS
    )

    if not market_topic:

        return False


    # --------------------------------------------------------
    # 判断是否存在真实事件动作
    # --------------------------------------------------------

    event_action = regex_match(
        text,
        EVENT_ACTION_PATTERNS
    )


    # --------------------------------------------------------
    # 观点文章例外处理
    #
    # 如果只是分析、推荐、展望，
    # 没有新的实际事件，
    # 不进入高影响新闻池。
    # --------------------------------------------------------

    if is_opinion_article(
        title,
        summary
    ) and not event_action:

        return False


    # --------------------------------------------------------
    # 有明确市场事件动作
    # --------------------------------------------------------

    if event_action:

        return True


    # --------------------------------------------------------
    # 部分宏观指标本身就是事件
    # --------------------------------------------------------

    macro_event = [

        r"\bcpi\b",
        r"\bppi\b",
        r"\bgdp\b",
        r"\bpayroll\b",
        r"\bunemployment\b",
        r"\binflation\b",
        r"\bfomc\b",

    ]

    if regex_match(
        text,
        macro_event
    ):

        return True


    return False


# ============================================================
# 事件类型判断
# ============================================================
#
# 严格按照“事件本身是什么”
#
# 优先级不是简单关键词数量，
# 而是明确的事件类型。
# ============================================================

def classify_event(
    article
):

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


    # --------------------------------------------------------
    # 1. 宏观经济 / 央行政策
    #
    # 事件本身是：
    # Fed、央行、利率、通胀、就业、GDP等
    # --------------------------------------------------------

    macro_patterns = [

        r"\bfederal reserve\b",
        r"\bfed\b",
        r"\bfomc\b",
        r"\binterest rate\b",
        r"\brate cut\b",
        r"\brate hike\b",
        r"\bmonetary policy\b",
        r"\binflation\b",
        r"\bcpi\b",
        r"\bppi\b",
        r"\bpayroll\b",
        r"\bunemployment\b",
        r"\bgdp\b",
        r"\bcentral bank\b",

    ]

    if regex_match(
        text,
        macro_patterns
    ):

        return "宏观经济与央行政策"


    # --------------------------------------------------------
    # 2. 能源 / 大宗商品
    #
    # 事件本身直接影响油、气、黄金、金属等商品供需。
    # --------------------------------------------------------

    commodity_patterns = [

        r"\boil\b",
        r"\bcrude\b",
        r"\bbrent\b",
        r"\bwti\b",
        r"\bopec\b",
        r"\bnatural gas\b",
        r"\bgold\b",
        r"\bsilver\b",
        r"\bcopper\b",

    ]

    if regex_match(
        text,
        commodity_patterns
    ):

        # 但如果本质是战争本身，
        # 应优先归到地缘政治。
        geopolitical_patterns = [

            r"\bwar\b",
            r"\barmed conflict\b",
            r"\bmilitary\b",
            r"\bmissile\b",
            r"\battack\b",
            r"\bstrike\b",
            r"\bescalation\b",

        ]

        if regex_match(
            text,
            geopolitical_patterns
        ):

            # 如果新闻核心是能源供应 / 油价，
            # 才归能源。
            energy_core = [

                r"\boil hub\b",
                r"\boil reserves\b",
                r"\boil supply\b",
                r"\boil production\b",
                r"\benergy supply\b",
                r"\benergy infrastructure\b",
                r"\bstrait of hormuz\b",
                r"\boil market\b",

            ]

            if regex_match(
                text,
                energy_core
            ):

                return "能源与大宗商品"

            return "地缘政治与制裁"

        return "能源与大宗商品"


    # --------------------------------------------------------
    # 3. AI / 半导体
    # --------------------------------------------------------

    semiconductor_patterns = [

        r"\bartificial intelligence\b",
        r"\bai chip\b",
        r"\bgpu\b",
        r"\bsemiconductor\b",
        r"\bchips?\b",
        r"\bhbm\b",
        r"\boptical networking\b",
        r"\bdata center\b",
        r"\bfoundry\b",
        r"\bnvidia\b",
        r"\bamd\b",
        r"\bbroadcom\b",
        r"\bintel\b",
        r"\btsmc\b",
        r"\basml\b",

    ]

    if regex_match(
        text,
        semiconductor_patterns
    ):

        return "AI与半导体"


    # --------------------------------------------------------
    # 4. 公司重大事件
    #
    # 本质是：
    # 单一或少数公司发生重大经营、财务、管理、
    # IPO、并购、破产等事件。
    # --------------------------------------------------------

    company_patterns = [

        r"\bearnings\b",
        r"\bquarterly results\b",
        r"\brevenue\b",
        r"\bprofit\b",
        r"\bloss\b",
        r"\bguidance\b",
        r"\bacquisition\b",
        r"\bmerger\b",
        r"\btakeover\b",
        r"\bbankruptcy\b",
        r"\bipo\b",
        r"\bceo\b",
        r"\bchief executive\b",
        r"\bregulatory nod\b",

    ]

    if regex_match(
        text,
        company_patterns
    ):

        return "公司重大事件"


    # --------------------------------------------------------
    # 5. 外汇 / 债券
    #
    # 只有当事件核心是：
    # 汇率、美元、日元、人民币、国债、收益率等，
    # 才归此类。
    # --------------------------------------------------------

    fx_bond_patterns = [

        r"\bforex\b",
        r"\bcurrency\b",
        r"\bdollar\b",
        r"\byen\b",
        r"\byuan\b",
        r"\btreasury yield\b",
        r"\bbond yield\b",
        r"\bbond market\b",

    ]

    if regex_match(
        text,
        fx_bond_patterns
    ):

        return "外汇与债券"


    # --------------------------------------------------------
    # 6. 地缘政治 / 制裁
    #
    # 事件本身是：
    # 战争、军事行动、制裁、贸易战、
    # 出口管制、国家关系恶化等。
    # --------------------------------------------------------

    geopolitical_patterns = [

        r"\bwar\b",
        r"\barmed conflict\b",
        r"\bmilitary\b",
        r"\bmissile\b",
        r"\battack\b",
        r"\bstrike\b",
        r"\bceasefire\b",
        r"\bescalation\b",
        r"\bgeopolitical\b",
        r"\bsanction\b",
        r"\bsanctions\b",
        r"\btrade war\b",
        r"\btariff\b",
        r"\btariffs\b",
        r"\bexport controls?\b",
        r"\bexport restrictions?\b",

    ]

    if regex_match(
        text,
        geopolitical_patterns
    ):

        return "地缘政治与制裁"


    # --------------------------------------------------------
    # 7. 全球股市
    #
    # 本质是：
    # 市场指数、整体股市走势、行业市场结构变化。
    # --------------------------------------------------------

    stock_market_patterns = [

        r"\bstock market\b",
        r"\bequity markets?\b",
        r"\bmarket rally\b",
        r"\bmarket selloff\b",
        r"\bmarket crash\b",
        r"\bnasdaq\b",
        r"\bs&p 500\b",
        r"\bdow jones\b",
        r"\bnikkei\b",
        r"\bkospi\b",
        r"\bh[ae]ng seng\b",
        r"\bvix\b",

    ]

    if regex_match(
        text,
        stock_market_patterns
    ):

        return "全球股市"


    # --------------------------------------------------------
    # 8. 其他市场事件
    # --------------------------------------------------------

    return "其他市场事件"


# ============================================================
# 影响范围评分
# ============================================================
#
# 40分
#
# 判断：
# 事件影响的是单一公司、单一行业、单一国家，
# 还是全球主要金融市场。
#
# 不考虑来源。
# 不考虑关键词数量。
# ============================================================

def score_impact_scope(
    article,
    category
):

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


    # --------------------------------------------------------
    # 全球金融市场级
    # --------------------------------------------------------

    global_patterns = [

        r"\bfederal reserve\b",
        r"\bfomc\b",
        r"\bglobal markets?\b",
        r"\bworld economy\b",
        r"\btrade war\b",
        r"\bmajor war\b",
        r"\bstrait of hormuz\b",
        r"\boil supply\b",
        r"\bopec\b",

    ]

    if regex_match(
        text,
        global_patterns
    ):

        return 40


    # --------------------------------------------------------
    # 多国 / 区域级
    # --------------------------------------------------------

    regional_patterns = [

        r"\bus canada\b",
        r"\bchina\b",
        r"\bunited states\b",
        r"\beurope\b",
        r"\basia\b",
        r"\bindia\b",
        r"\bsouth korea\b",
        r"\bjapan\b",
        r"\brussia\b",
        r"\bukraine\b",
        r"\biran\b",

    ]

    if regex_match(
        text,
        regional_patterns
    ):

        return 28


    # --------------------------------------------------------
    # 单一行业 / 公司
    # --------------------------------------------------------

    if category in [

        "公司重大事件",
        "AI与半导体",

    ]:

        return 20


    # --------------------------------------------------------
    # 默认
    # --------------------------------------------------------

    return 10


# ============================================================
# 影响程度评分
# ============================================================
#
# 40分
#
# 判断事件本身可能造成的实际市场冲击。
#
# 关键：
# “有新闻” ≠ “有重大影响”
# ============================================================

def score_impact_degree(
    article,
    category
):

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


    # --------------------------------------------------------
    # 一级重大事件
    # --------------------------------------------------------

    very_high_patterns = [

        r"\bwar\b",
        r"\barmed conflict\b",
        r"\bmajor strikes?\b",
        r"\btrade war\b",
        r"\bfed rate hike\b",
        r"\bfed rate cut\b",
        r"\binterest rate\b",
        r"\bdefault\b",
        r"\bbankruptcy\b",
        r"\bmarket crash\b",

    ]

    if regex_match(
        text,
        very_high_patterns
    ):

        return 36


    # --------------------------------------------------------
    # 明确重大市场事件
    # --------------------------------------------------------

    high_patterns = [

        r"\bsanctions?\b",
        r"\btariffs?\b",
        r"\boil reserves\b",
        r"\boil supply\b",
        r"\bearnings\b",
        r"\bquarterly results\b",
        r"\bipo\b",
        r"\bacquisition\b",
        r"\bmerger\b",
        r"\bceo\b",

    ]

    if regex_match(
        text,
        high_patterns
    ):

        return 30


    # --------------------------------------------------------
    # 一般市场影响
    # --------------------------------------------------------

    medium_patterns = [

        r"\bshares? (rise|fall|slide|surge|jump|drop)\b",
        r"\bstock market\b",
        r"\bmarket rally\b",
        r"\bmarket selloff\b",
        r"\bforecast\b",
        r"\bguidance\b",

    ]

    if regex_match(
        text,
        medium_patterns
    ):

        return 20


    # --------------------------------------------------------
    # 纯观点 / 分析
    #
    # 即便涉及热门股票或Fed，
    # 如果没有新事件，影响程度不得虚高。
    # --------------------------------------------------------

    if is_opinion_article(
        title,
        summary
    ):

        return 5


    return 10


# ============================================================
# 最终评分
# ============================================================

def calculate_score(
    article,
    category
):

    impact_scope = score_impact_scope(
        article,
        category
    )

    impact_degree = score_impact_degree(
        article,
        category
    )

    source_credibility = get_source_credibility(
        article.get(
            "source",
            ""
        )
    )

    # 强制边界
    impact_scope = min(
        max(impact_scope, 0),
        40
    )

    impact_degree = min(
        max(impact_degree, 0),
        40
    )

    source_credibility = min(
        max(source_credibility, 0),
        20
    )

    total_score = (
        impact_scope
        + impact_degree
        + source_credibility
    )

    article["impact_scope"] = impact_scope
    article["impact_degree"] = impact_degree
    article["source_credibility"] = source_credibility
    article["score"] = total_score

    return article


# ============================================================
# 新闻标准化
# ============================================================

def prepare_article(
    article
):

    article = dict(article)

    article.setdefault(
        "category",
        None
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
# 同一事件识别
# ============================================================
#
# 不简单按照标题完全相同判断。
#
# 核心逻辑：
# 同一事件 + 同一主体 + 相似核心词
# 才进行合并。
#
# 不同事件即使都有 Iran / oil / tariff，
# 也不能随意合并。
# ============================================================

def build_event_key(
    article
):

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
    # 提取关键主体
    # --------------------------------------------------------

    entities = [

        "federal reserve",
        "fed",
        "trump",
        "iran",
        "israel",
        "russia",
        "ukraine",
        "china",
        "canada",
        "venezuela",
        "nvidia",
        "byd",
        "hdfc bank",
        "jio platforms",

    ]


    matched_entities = [

        entity
        for entity in entities
        if entity in text

    ]


    # --------------------------------------------------------
    # 核心事件词
    # --------------------------------------------------------

    event_words = [

        "war",
        "strike",
        "strikes",
        "sanctions",
        "sanction",
        "tariff",
        "tariffs",
        "earnings",
        "ipo",
        "ceo",
        "rate hike",
        "rate cut",
        "interest rate",
        "oil reserves",
        "oil supply",
        "trade war",
        "default",
        "bankruptcy",

    ]


    matched_events = [

        word
        for word in event_words
        if word in text

    ]


    if matched_entities and matched_events:

        return (
            matched_entities[0],
            matched_events[0]
        )


    # 没有足够信息时，
    # 使用规范化标题作为保守键。
    #
    # 宁可少合并，也不要错误合并不同事件。
    return (
        title[:180],
    )


# ============================================================
# 同一事件合并
# ============================================================

def merge_same_events(
    articles
):

    groups = defaultdict(list)

    for article in articles:

        key = build_event_key(
            article
        )

        groups[key].append(
            article
        )


    merged = []


    for key, items in groups.items():

        # ----------------------------------------------------
        # 最高分新闻作为主记录
        # ----------------------------------------------------

        items.sort(
            key=lambda x: (
                x.get("score", 0),
                x.get("published_at") or datetime.min
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


        primary["sources"] = sources
        primary["urls"] = urls

        # 保留原始新闻数量
        primary["merged_count"] = len(
            items
        )

        # ----------------------------------------------------
        # 不因为多来源而人为提高评分
        #
        # 主评分仍然来自主新闻本身。
        # ----------------------------------------------------

        merged.append(
            primary
        )


    return merged


# ============================================================
# 低权重分类Top10
# ============================================================

def select_low_score_news(
    articles
):

    category_groups = defaultdict(list)


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

        # ----------------------------------------------------
        # 每类最多10条
        # ----------------------------------------------------

        items.sort(
            key=lambda x: (
                x.get("score", 0),
                x.get("published_at") or datetime.min
            ),
            reverse=True
        )

        selected.extend(
            items[:10]
        )


    return selected


# ============================================================
# 主筛选函数
# ============================================================

def select_news(
    raw_news
):

    print(
        "\n============================================================"
    )

    # --------------------------------------------------------
    # 第一步：
    # 市场实际影响力初筛
    # --------------------------------------------------------

    market_candidates = []


    for raw_article in raw_news:

        article = prepare_article(
            raw_article
        )


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


        # 必须有发布时间
        if not article.get(
            "published_at"
        ):

            continue


        # ----------------------------------------------------
        # 实际金融市场影响力判断
        # ----------------------------------------------------

        if not has_actual_market_impact(
            article
        ):

            continue


        article["market_relevant"] = True


        # ----------------------------------------------------
        # 第二步：
        # 按事件本身分类
        # ----------------------------------------------------

        category = classify_event(
            article
        )

        article["category"] = category


        # ----------------------------------------------------
        # 第三步：
        # 评分
        # ----------------------------------------------------

        article = calculate_score(
            article,
            category
        )


        market_candidates.append(
            article
        )


    print(
        f"市场相关候选新闻："
        f"{len(market_candidates)}"
    )


    # --------------------------------------------------------
    # 第四步：
    # 同一事件合并
    # --------------------------------------------------------

    merged_news = merge_same_events(
        market_candidates
    )


    print(
        f"同一事件合并后："
        f"{len(merged_news)}"
    )


    # --------------------------------------------------------
    # 第五步：
    # 高权重全部保留
    #
    # >40
    # --------------------------------------------------------

    high_score_news = [

        article
        for article in merged_news
        if article.get(
            "score",
            0
        ) > 40

    ]


    # --------------------------------------------------------
    # 第六步：
    # 低权重 <=40
    #
    # 分类Top10
    # --------------------------------------------------------

    low_score_news = [

        article
        for article in merged_news
        if article.get(
            "score",
            0
        ) <= 40

    ]


    low_score_selected = select_low_score_news(
        low_score_news
    )


    print(
        f"高权重新闻（>40）："
        f"{len(high_score_news)}"
    )

    print(
        f"低权重新闻（<=40）："
        f"{len(low_score_selected)}"
    )


    # --------------------------------------------------------
    # 第七步：
    # 合并最终结果
    # --------------------------------------------------------

    final_news = (
        high_score_news
        + low_score_selected
    )


    # --------------------------------------------------------
    # 最终排序
    # --------------------------------------------------------

    final_news.sort(
        key=lambda x: (
            x.get(
                "score",
                0
            ),
            x.get(
                "published_at"
            ) or datetime.min
        ),
        reverse=True
    )


    print(
        f"最终新闻数量："
        f"{len(final_news)}"
    )

    print(
        "============================================================"
    )


    # --------------------------------------------------------
    # 按分类返回
    # --------------------------------------------------------

    result = defaultdict(list)


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


    return dict(result)


# ============================================================
# 调试函数
# ============================================================

def score_single_article(
    article
):

    article = prepare_article(
        article
    )


    if not has_actual_market_impact(
        article
    ):

        article["market_relevant"] = False

        return article


    article["market_relevant"] = True


    category = classify_event(
        article
    )

    article["category"] = category


    calculate_score(
        article,
        category
    )


    return article
