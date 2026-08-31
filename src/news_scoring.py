# ============================================================
# src/news_scoring.py
# 全球金融市场日报 Agent
#
# 新闻筛选 / 分类 / 去重 / 重要性评分 / 展示规则
#
# 核心基准：
# 1. 先筛选：只保留对金融市场具有实际影响力的信息
# 2. 再分类：按照“事件本身是什么”进行分类
# 3. 评分：
#       影响范围   40分
#       影响程度   40分
#       来源可信度 20分
#       总分       100分
# 4. 取消 TOP10 总量限制
# 5. Score > 40：全部保留
# 6. Score <= 40：按照分类执行 Top10
# 7. 不足10条：有几条展示几条
# 8. 同一事件：去重、合并
# 9. 来源不决定重要性，只影响可信度20分
# 10. 新闻必须来自真实媒体 / 官方机构
# 11. 无法验证的数据：明确标记“数据缺失/获取失败”
# 12. 严禁 AI 编造新闻、行情、事件或引用
# ============================================================

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher

import feedparser


# ============================================================
# 基础配置
# ============================================================

NEWS_WINDOW_HOURS = 36

# 低权重新闻每个分类最多展示10条
LOW_WEIGHT_CATEGORY_LIMIT = 10

# 高权重阈值
HIGH_WEIGHT_THRESHOLD = 40


# ============================================================
# RSS 新闻源
# ============================================================

NEWS_FEEDS = {
    "CNBC Markets":
        "https://www.cnbc.com/id/15839135/device/rss/rss.html",

    "CNBC Finance":
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",

    "CNBC World News":
        "https://www.cnbc.com/id/100727362/device/rss/rss.html",

    "CNBC Top News":
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",

    "BBC Business":
        "https://feeds.bbci.co.uk/news/business/rss.xml",
}


# ============================================================
# 来源可信度
#
# 注意：
# 来源可信度只负责20分。
# 不能因为来源权威，就自动认为新闻重要。
# ============================================================

SOURCE_CREDIBILITY_SCORE = {

    # --------------------------------------------------------
    # 官方 / 一手机构
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
    # 权威财经媒体
    # --------------------------------------------------------

    "Reuters": 18,
    "Bloomberg": 18,
    "CNBC Finance": 18,
    "CNBC Markets": 18,
    "Financial Times": 18,
    "Wall Street Journal": 18,
    "新华社": 18,

    "CNBC World News": 17,
    "CNBC Top News": 17,
    "BBC Business": 17,

    # --------------------------------------------------------
    # 国际金融机构
    # --------------------------------------------------------

    "IMF": 19,
    "BIS": 19,
    "World Bank": 19,
}


DEFAULT_SOURCE_CREDIBILITY = 10


# ============================================================
# 新闻分类
#
# 分类原则：
# “这条新闻本质上发生了什么？”
#
# 而不是：
# “这条新闻里出现了什么关键词？”
# ============================================================

CATEGORIES = [
    "宏观经济与央行政策",
    "AI与半导体",
    "全球金融市场",
    "能源与大宗商品",
    "公司重大事件",
    "地缘政治与制裁",
]


# ============================================================
# 文本清洗
# ============================================================

def clean_text(text):
    """
    清洗标题 / 摘要。

    注意：
    清洗只是为了文本判断，
    不用于计算关键词命中数量。
    """

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
# 完整词匹配
# ============================================================

def contains_phrase(text, phrase):
    """
    判断文本是否包含一个完整事件短语。

    这里只用于事件识别，
    不统计命中次数。
    """

    text = clean_text(text)
    phrase = clean_text(phrase)

    if not text or not phrase:
        return False

    if " " in phrase:
        return phrase in text

    return re.search(
        rf"\b{re.escape(phrase)}\b",
        text
    ) is not None


def contains_any(text, phrases):
    return any(
        contains_phrase(text, phrase)
        for phrase in phrases
    )


# ============================================================
# 发布时间解析
# ============================================================

def parse_publish_time(item):
    """
    尝试从 RSS 获取真实发布时间。

    无法解析时返回 None。
    不猜测时间。
    """

    candidates = [
        getattr(item, "published", ""),
        getattr(item, "updated", ""),
    ]

    for value in candidates:

        if not value:
            continue

        try:
            dt = parsedate_to_datetime(value)

            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(
                timezone.utc
            )

        except Exception:
            continue

    parsed = getattr(
        item,
        "published_parsed",
        None
    )

    if parsed:

        try:
            return datetime(
                parsed.tm_year,
                parsed.tm_mon,
                parsed.tm_mday,
                parsed.tm_hour,
                parsed.tm_min,
                parsed.tm_sec,
                tzinfo=timezone.utc
            )

        except Exception:
            pass

    return None


# ============================================================
# 时间格式
# ============================================================

def format_publish_time(dt):

    if not dt:
        return "时间缺失"

    china_tz = timezone(
        timedelta(hours=8)
    )

    return dt.astimezone(
        china_tz
    ).strftime(
        "%Y-%m-%d %H:%M"
    )


# ============================================================
# 明确排除：
# 这些不是“实际发生的重大市场事件”
#
# 注意：
# 不是看到这些词就全部删除。
# 只有当文章本身属于评论 / 投资建议 / 展望等内容时才排除。
# ============================================================

OPINION_PATTERNS = [

    "op-ed",
    "op ed",
    "opinion",
    "commentary",
    "editorial",
    "column",

    "stock picks",
    "stocks to watch",
    "top stock",
    "dividend stocks",
    "investing club",

    "trading strategy",
    "investment strategy",

    "market outlook",
    "investment outlook",
    "investor outlook",

    "what we're watching",
    "what we are watching",
    "week ahead",

    "why investors",
    "why markets",
    "what we learned",
    "what we know",
    "what to know",
    "the big lesson",
]


def is_opinion_or_strategy(title, summary=""):

    title_clean = clean_text(title)
    summary_clean = clean_text(summary)

    # 标题命中评论型表达时，优先判断为评论/策略文章
    if contains_any(
        title_clean,
        OPINION_PATTERNS
    ):
        return True

    # 只有标题明确表现为观点型内容时，
    # 才进一步检查摘要。
    if contains_any(
        summary_clean,
        [
            "investment strategy",
            "trading strategy",
            "stock picks",
            "dividend stocks",
            "market outlook",
            "investor outlook",
        ]
    ):
        return True

    return False


# ============================================================
# 金融市场实际影响判断
#
# 这里不是“关键词越多越重要”。
#
# 判断逻辑是：
# 文章是否描述一个已经发生 / 已确认 / 正在发生的
# 会改变以下因素的事件：
#
# - 利率预期
# - 通胀预期
# - 经济增长预期
# - 企业盈利
# - 商品供需
# - 汇率
# - 债券收益率
# - 股票估值
# - 资本流动
# - 风险偏好
# - 制裁 / 贸易政策
# - 地缘风险
# ============================================================

def is_market_relevant(title, summary=""):

    title_clean = clean_text(title)
    summary_clean = clean_text(summary)

    text = f"{title_clean} {summary_clean}"

    # --------------------------------------------------------
    # 1. 宏观政策 / 数据
    # --------------------------------------------------------

    macro_event = contains_any(
        text,
        [
            "fed decision",
            "fed meeting",
            "fomc",
            "interest rate decision",
            "rate decision",
            "rate hike",
            "rate cut",
            "central bank decision",

            "inflation data",
            "cpi report",
            "ppi report",
            "jobs report",
            "payroll report",
            "employment report",
            "gdp report",

            "central bank",
            "federal reserve",

            "treasury yield",
            "bond yield",
        ]
    )

    if macro_event:
        return True

    # --------------------------------------------------------
    # 2. 贸易 / 制裁 / 地缘
    # --------------------------------------------------------

    geopolitical_event = contains_any(
        text,
        [
            "sanctions imposed",
            "new sanctions",
            "sanctions announced",
            "export controls",
            "export restrictions",

            "tariff imposed",
            "tariffs imposed",
            "new tariffs",
            "trade agreement",
            "trade deal",

            "war",
            "military attack",
            "missile attack",
            "airstrike",
            "air strikes",
            "invasion",
            "ceasefire",
            "armed conflict",
        ]
    )

    if geopolitical_event:
        return True

    # --------------------------------------------------------
    # 3. 能源 / 大宗商品
    # --------------------------------------------------------

    commodity_event = contains_any(
        text,
        [
            "opec decision",
            "opec meeting",
            "oil production",
            "oil supply",
            "oil output",
            "crude production",

            "gold price",
            "silver price",
            "copper price",

            "oil surged",
            "oil plunged",
            "oil prices",
            "crude prices",

            "brent",
            "wti",
        ]
    )

    if commodity_event:
        return True

    # --------------------------------------------------------
    # 4. 公司真实重大事件
    # --------------------------------------------------------

    company_event = contains_any(
        text,
        [
            "earnings report",
            "quarterly earnings",
            "quarterly results",
            "financial results",

            "revenue rose",
            "revenue fell",
            "profit rose",
            "profit fell",

            "guidance raised",
            "guidance lowered",
            "guidance cut",

            "acquisition announced",
            "merger announced",
            "takeover announced",

            "bankruptcy filed",
            "ipo approved",
            "ipo launched",

            "regulatory approval",
        ]
    )

    if company_event:
        return True

    # --------------------------------------------------------
    # 5. AI / 半导体产业重大事件
    # --------------------------------------------------------

    technology_event = contains_any(
        text,
        [
            "chip export",
            "semiconductor export",
            "chip restrictions",
            "semiconductor restrictions",

            "chip shortage",
            "chip supply",

            "new gpu",
            "new ai chip",

            "semiconductor investment",
            "semiconductor plant",

            "foundry investment",

            "nvidia earnings",
            "tsmc earnings",
            "broadcom earnings",
            "amd earnings",
        ]
    )

    if technology_event:
        return True

    # --------------------------------------------------------
    # 6. 明确的市场价格剧烈变化
    #
    # 注意：
    # 单纯“某股票上涨”不一定是重大新闻。
    # 必须是具有明显市场意义的价格变化。
    # --------------------------------------------------------

    market_event = contains_any(
        text,
        [
            "market crash",
            "market selloff",
            "market rout",

            "stocks plunged",
            "stocks surged",
            "stocks tumbled",

            "index plunged",
            "index surged",

            "record high",
            "record low",

            "vix surged",
            "volatility spike",
        ]
    )

    if market_event:
        return True

    return False


# ============================================================
# 事件类型识别
#
# 核心：
# 不是“出现 Nvidia 就归 AI”
# 而是判断文章描述的核心事件。
# ============================================================

def identify_event_type(article):

    title = clean_text(
        article.get("title", "")
    )

    summary = clean_text(
        article.get("summary", "")
    )

    text = f"{title} {summary}"

    # --------------------------------------------------------
    # 第一优先级：真实宏观政策 / 数据事件
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "fed decision",
            "fed meeting",
            "fomc",
            "rate decision",
            "rate hike",
            "rate cut",
            "central bank decision",

            "cpi report",
            "ppi report",
            "jobs report",
            "payroll report",
            "employment report",
            "gdp report",
        ]
    ):
        return "宏观政策或经济数据事件"

    # --------------------------------------------------------
    # 第二优先级：地缘 / 制裁 / 贸易政策
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "new sanctions",
            "sanctions imposed",
            "sanctions announced",
            "export controls",
            "export restrictions",

            "new tariffs",
            "tariffs imposed",
            "trade agreement",
            "trade deal",

            "military attack",
            "missile attack",
            "airstrike",
            "air strikes",
            "invasion",
            "ceasefire",
            "armed conflict",
            "war",
        ]
    ):
        return "地缘政治、贸易或制裁事件"

    # --------------------------------------------------------
    # 第三优先级：能源 / 商品
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "opec decision",
            "oil production",
            "oil supply",
            "oil output",
            "crude production",
            "oil prices",
            "crude prices",
            "gold price",
            "silver price",
            "copper price",
        ]
    ):
        return "能源与大宗商品事件"

    # --------------------------------------------------------
    # 第四优先级：公司重大资本事件
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "acquisition announced",
            "merger announced",
            "takeover announced",
            "bankruptcy filed",
            "ipo approved",
            "ipo launched",
            "regulatory approval",
        ]
    ):
        return "公司重大资本事件"

    # --------------------------------------------------------
    # 第五优先级：公司财报 / 经营事件
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "earnings report",
            "quarterly earnings",
            "quarterly results",
            "financial results",

            "guidance raised",
            "guidance lowered",
            "guidance cut",

            "revenue rose",
            "revenue fell",
            "profit rose",
            "profit fell",
        ]
    ):
        return "公司财报或经营事件"

    # --------------------------------------------------------
    # 第六优先级：AI / 半导体产业事件
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "chip export",
            "semiconductor export",
            "chip restrictions",
            "semiconductor restrictions",
            "chip shortage",
            "chip supply",
            "new gpu",
            "new ai chip",
            "semiconductor investment",
            "semiconductor plant",
            "foundry investment",
        ]
    ):
        return "AI与半导体产业事件"

    # --------------------------------------------------------
    # 第七优先级：市场价格事件
    # --------------------------------------------------------

    if contains_any(
        text,
        [
            "market crash",
            "market selloff",
            "market rout",
            "stocks plunged",
            "stocks surged",
            "stocks tumbled",
            "index plunged",
            "index surged",
            "record high",
            "record low",
            "vix surged",
            "volatility spike",
        ]
    ):
        return "重大金融市场价格事件"

    # --------------------------------------------------------
    # 默认
    # --------------------------------------------------------

    return "一般金融市场信息"


# ============================================================
# 分类
#
# 分类顺序体现“事件本身”的优先级。
# ============================================================

def classify_news(title, summary=""):

    article = {
        "title": title,
        "summary": summary,
    }

    event_type = identify_event_type(
        article
    )

    # --------------------------------------------------------
    # 宏观
    # --------------------------------------------------------

    if event_type == "宏观政策或经济数据事件":
        return "宏观经济与央行政策"

    # --------------------------------------------------------
    # 地缘
    # --------------------------------------------------------

    if event_type == "地缘政治、贸易或制裁事件":
        return "地缘政治与制裁"

    # --------------------------------------------------------
    # 能源
    # --------------------------------------------------------

    if event_type == "能源与大宗商品事件":
        return "能源与大宗商品"

    # --------------------------------------------------------
    # 公司
    # --------------------------------------------------------

    if event_type in [
        "公司重大资本事件",
        "公司财报或经营事件",
    ]:
        return "公司重大事件"

    # --------------------------------------------------------
    # AI / 半导体
    # --------------------------------------------------------

    if event_type == "AI与半导体产业事件":
        return "AI与半导体"

    # --------------------------------------------------------
    # 市场
    # --------------------------------------------------------

    if event_type == "重大金融市场价格事件":
        return "全球金融市场"

    return "全球金融市场"


# ============================================================
# 影响范围评分
#
# 40分满分
#
# 判断：
# - 影响多少市场
# - 影响多少国家 / 地区
# - 是否跨资产类别
# - 是否影响全球资金风险偏好
#
# 不是关键词数量。
# ============================================================

def calculate_impact_scope(article):

    event_type = identify_event_type(
        article
    )

    title = clean_text(
        article.get("title", "")
    )

    summary = clean_text(
        article.get("summary", "")
    )

    text = f"{title} {summary}"

    # --------------------------------------------------------
    # 全球央行 / 全球宏观
    # --------------------------------------------------------

    if event_type == "宏观政策或经济数据事件":

        if contains_any(
            text,
            [
                "federal reserve",
                "fed",
                "fomc",
                "global",
                "world economy",
            ]
        ):
            return 40

        return 36

    # --------------------------------------------------------
    # 重大地缘 / 制裁 / 全球贸易
    # --------------------------------------------------------

    if event_type == "地缘政治、贸易或制裁事件":

        if contains_any(
            text,
            [
                "iran",
                "israel",
                "russia",
                "ukraine",
                "china",
                "united states",
                "global trade",
                "trade war",
                "strait of hormuz",
            ]
        ):
            return 38

        return 34

    # --------------------------------------------------------
    # 能源 / 大宗
    # --------------------------------------------------------

    if event_type == "能源与大宗商品事件":
        return 34

    # --------------------------------------------------------
    # 公司重大资本事件
    # --------------------------------------------------------

    if event_type == "公司重大资本事件":
        return 30

    # --------------------------------------------------------
    # 公司财报
    # --------------------------------------------------------

    if event_type == "公司财报或经营事件":

        # 全球核心公司
        if contains_any(
            text,
            [
                "nvidia",
                "apple",
                "microsoft",
                "amazon",
                "alphabet",
                "google",
                "meta",
                "tesla",
                "broadcom",
                "tsmc",
                "asml",
            ]
        ):
            return 30

        return 25

    # --------------------------------------------------------
    # AI / 半导体产业
    # --------------------------------------------------------

    if event_type == "AI与半导体产业事件":
        return 30

    # --------------------------------------------------------
    # 市场价格
    # --------------------------------------------------------

    if event_type == "重大金融市场价格事件":
        return 32

    return 15


# ============================================================
# 影响程度评分
#
# 40分满分
#
# 判断事件是否真正改变：
# - 利率预期
# - 盈利预期
# - 估值
# - 商品供需
# - 汇率
# - 资本流向
# - 风险偏好
#
# 不是“标题看起来很严重”。
# ============================================================

def calculate_impact_degree(article):

    event_type = identify_event_type(
        article
    )

    title = clean_text(
        article.get("title", "")
    )

    summary = clean_text(
        article.get("summary", "")
    )

    text = f"{title} {summary}"

    # --------------------------------------------------------
    # 央行政策 / 利率
    # --------------------------------------------------------

    if event_type == "宏观政策或经济数据事件":

        if contains_any(
            text,
            [
                "rate decision",
                "rate hike",
                "rate cut",
                "fomc",
                "fed decision",
            ]
        ):
            return 40

        if contains_any(
            text,
            [
                "cpi report",
                "jobs report",
                "payroll report",
                "gdp report",
            ]
        ):
            return 36

        return 30

    # --------------------------------------------------------
    # 地缘 / 制裁
    # --------------------------------------------------------

    if event_type == "地缘政治、贸易或制裁事件":

        if contains_any(
            text,
            [
                "military attack",
                "missile attack",
                "airstrike",
                "war",
                "invasion",
            ]
        ):
            return 40

        if contains_any(
            text,
            [
                "new sanctions",
                "sanctions imposed",
                "new tariffs",
                "tariffs imposed",
                "export controls",
            ]
        ):
            return 36

        return 30

    # --------------------------------------------------------
    # 能源
    # --------------------------------------------------------

    if event_type == "能源与大宗商品事件":

        if contains_any(
            text,
            [
                "oil supply",
                "oil production",
                "opec decision",
            ]
        ):
            return 36

        return 30

    # --------------------------------------------------------
    # 公司重大资本事件
    # --------------------------------------------------------

    if event_type == "公司重大资本事件":
        return 34

    # --------------------------------------------------------
    # 公司财报
    # --------------------------------------------------------

    if event_type == "公司财报或经营事件":

        if contains_any(
            text,
            [
                "guidance lowered",
                "guidance cut",
                "profit fell",
                "revenue fell",
            ]
        ):
            return 34

        if contains_any(
            text,
            [
                "guidance raised",
                "profit rose",
                "revenue rose",
            ]
        ):
            return 30

        return 28

    # --------------------------------------------------------
    # AI / 半导体
    # --------------------------------------------------------

    if event_type == "AI与半导体产业事件":
        return 32

    # --------------------------------------------------------
    # 市场价格
    # --------------------------------------------------------

    if event_type == "重大金融市场价格事件":

        if contains_any(
            text,
            [
                "market crash",
                "market rout",
                "market selloff",
            ]
        ):
            return 38

        return 30

    return 10


# ============================================================
# 来源可信度
# ============================================================

def calculate_source_credibility(article):

    source = article.get(
        "source",
        ""
    )

    return SOURCE_CREDIBILITY_SCORE.get(
        source,
        DEFAULT_SOURCE_CREDIBILITY
    )


# ============================================================
# 总评分
#
# 40 + 40 + 20 = 100
# ============================================================

def calculate_score(article):

    scope = calculate_impact_scope(
        article
    )

    degree = calculate_impact_degree(
        article
    )

    credibility = calculate_source_credibility(
        article
    )

    score = (
        scope
        + degree
        + credibility
    )

    return max(
        0,
        min(
            100,
            score
        )
    )


# ============================================================
# 事件画像
# ============================================================

def build_event_profile(article):

    event_type = identify_event_type(
        article
    )

    category = classify_news(
        article.get("title", ""),
        article.get("summary", "")
    )

    scope = calculate_impact_scope(
        article
    )

    degree = calculate_impact_degree(
        article
    )

    credibility = calculate_source_credibility(
        article
    )

    score = (
        scope
        + degree
        + credibility
    )

    return {
        "category": category,
        "event_type": event_type,
        "impact_scope": scope,
        "impact_degree": degree,
        "source_credibility": credibility,
        "score": score,
    }


# ============================================================
# 新闻去重
#
# 原则：
# 1. 标题高度相似 → 去重
# 2. 同一事件核心实体 + 事件动作 → 去重
#
# 注意：
# 不因为两篇文章都提到 Fed / Iran / Nvidia 就直接认为
# 是同一事件。
# ============================================================

def normalize_event_title(title):

    text = clean_text(title)

    remove_words = [
        "breaking",
        "live",
        "update",
        "latest",
        "cnbc daily open",
        "analyst roundup",
    ]

    for word in remove_words:
        text = text.replace(
            word,
            " "
        )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


def title_similarity(title_a, title_b):

    a = normalize_event_title(
        title_a
    )

    b = normalize_event_title(
        title_b
    )

    if not a or not b:
        return 0

    return SequenceMatcher(
        None,
        a,
        b
    ).ratio()


def extract_event_signature(article):

    title = clean_text(
        article.get("title", "")
    )

    summary = clean_text(
        article.get("summary", "")
    )

    text = f"{title} {summary}"

    # --------------------------------------------------------
    # 重大事件实体
    # --------------------------------------------------------

    entities = [
        "federal reserve",
        "fed",
        "fomc",

        "nvidia",
        "amd",
        "broadcom",
        "tsmc",
        "asml",

        "apple",
        "microsoft",
        "amazon",
        "google",
        "alphabet",
        "meta",
        "tesla",

        "iran",
        "israel",
        "russia",
        "ukraine",
        "china",
        "taiwan",
        "venezuela",

        "oil",
        "brent",
        "wti",
        "opec",

        "gold",
        "copper",

        "canada",
        "united states",
    ]

    entity = None

    for item in entities:

        if contains_phrase(
            text,
            item
        ):
            entity = item
            break

    event_type = identify_event_type(
        article
    )

    # --------------------------------------------------------
    # 事件动作
    # --------------------------------------------------------

    actions = [

        "rate hike",
        "rate cut",
        "rate decision",

        "sanctions",
        "tariffs",
        "export controls",

        "attack",
        "airstrike",
        "missile",
        "war",
        "ceasefire",

        "earnings",
        "guidance",

        "acquisition",
        "merger",
        "takeover",
        "bankruptcy",
        "ipo",

        "oil production",
        "oil supply",

        "market selloff",
        "market crash",
        "record high",
        "record low",
    ]

    action = None

    for item in actions:

        if contains_phrase(
            text,
            item
        ):
            action = item
            break

    return (
        event_type,
        entity,
        action
    )


def is_duplicate_event(
    article,
    existing_articles,
    similarity_threshold=0.86
):

    title = article.get(
        "title",
        ""
    )

    event_type, entity, action = (
        extract_event_signature(
            article
        )
    )

    for existing in existing_articles:

        existing_title = existing.get(
            "title",
            ""
        )

        # ----------------------------------------------------
        # 第一层：标题高度相似
        # ----------------------------------------------------

        similarity = title_similarity(
            title,
            existing_title
        )

        if similarity >= similarity_threshold:
            return True

        # ----------------------------------------------------
        # 第二层：同一事件画像
        # ----------------------------------------------------

        existing_event_type, existing_entity, existing_action = (
            extract_event_signature(
                existing
            )
        )

        if (
            event_type
            == existing_event_type
            and entity
            and entity == existing_entity
            and action
            and action == existing_action
        ):
            return True

    return False


# ============================================================
# 同一事件合并
#
# 不重复占用展示数量。
#
# 规则：
# - 保留评分最高的版本
# - 如果另一来源提供不同信息，可合并来源
# - 原文链接全部保留
# ============================================================

def merge_duplicate_event(base, duplicate):

    # --------------------------------------------------------
    # 来源
    # --------------------------------------------------------

    base_source = base.get(
        "source",
        ""
    )

    duplicate_source = duplicate.get(
        "source",
        ""
    )

    sources = []

    if base_source:
        sources.append(
            base_source
        )

    if duplicate_source:
        sources.append(
            duplicate_source
        )

    base["sources"] = list(
        dict.fromkeys(sources)
    )

    # --------------------------------------------------------
    # 原文链接
    # --------------------------------------------------------

    urls = []

    if base.get("url"):
        urls.append(
            base["url"]
        )

    if duplicate.get("url"):
        urls.append(
            duplicate["url"]
        )

    base["urls"] = list(
        dict.fromkeys(urls)
    )

    # --------------------------------------------------------
    # 来源字段保持主要来源
    # --------------------------------------------------------

    if (
        duplicate.get("score", 0)
        > base.get("score", 0)
    ):
        base["source"] = duplicate.get(
            "source",
            base.get("source", "")
        )

        base["url"] = duplicate.get(
            "url",
            base.get("url", "")
        )

        base["title"] = duplicate.get(
            "title",
            base.get("title", "")
        )

        base["summary"] = duplicate.get(
            "summary",
            base.get("summary", "")
        )

        base["published"] = duplicate.get(
            "published",
            base.get("published", "")
        )

        base["published_at"] = duplicate.get(
            "published_at",
            base.get("published_at")
        )

        base["score"] = duplicate.get(
            "score",
            base.get("score", 0)
        )

        base["impact_scope"] = duplicate.get(
            "impact_scope",
            base.get("impact_scope", 0)
        )

        base["impact_degree"] = duplicate.get(
            "impact_degree",
            base.get("impact_degree", 0)
        )

        base["source_credibility"] = duplicate.get(
            "source_credibility",
            base.get("source_credibility", 0)
        )

    return base


# ============================================================
# 处理单条新闻
# ============================================================

def process_article(article):

    title = article.get(
        "title",
        ""
    ).strip()

    summary = article.get(
        "summary",
        ""
    ).strip()

    source = article.get(
        "source",
        ""
    ).strip()

    url = article.get(
        "url",
        ""
    ).strip()

    # --------------------------------------------------------
    # 基础真实性要求
    # --------------------------------------------------------

    if not title:
        return None

    if not url:
        return None

    if not source:
        return None

    # --------------------------------------------------------
    # 市场相关性
    # --------------------------------------------------------

    if not is_market_relevant(
        title,
        summary
    ):
        return None

    # --------------------------------------------------------
    # 评论 / 投资建议 / 策略
    #
    # 注意：
    # 如果未来增加“高影响力研究/观点”正式来源，
    # 可以在这里单独放行。
    # 当前 RSS 来源主要用于真实事件新闻。
    # --------------------------------------------------------

    if is_opinion_or_strategy(
        title,
        summary
    ):
        return None

    # --------------------------------------------------------
    # 分类
    # --------------------------------------------------------

    category = classify_news(
        title,
        summary
    )

    # --------------------------------------------------------
    # 构建文章
    # --------------------------------------------------------

    article["category"] = category

    profile = build_event_profile(
        article
    )

    article["event_type"] = profile[
        "event_type"
    ]

    article["impact_scope"] = profile[
        "impact_scope"
    ]

    article["impact_degree"] = profile[
        "impact_degree"
    ]

    article["source_credibility"] = profile[
        "source_credibility"
    ]

    article["score"] = profile[
        "score"
    ]

    return article


# ============================================================
# 获取 RSS 新闻
# ============================================================

def fetch_news():

    articles = []

    since = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            hours=NEWS_WINDOW_HOURS
        )
    )

    print(
        "\n============================================================"
    )

    print(
        "开始获取全球金融市场新闻"
    )

    print(
        f"新闻时间窗口：最近 "
        f"{NEWS_WINDOW_HOURS} 小时"
    )

    print(
        "============================================================"
    )

    for source, url in NEWS_FEEDS.items():

        print(
            f"\n正在获取新闻源：{source}"
        )

        try:

            feed = feedparser.parse(
                url
            )

            source_count = 0

            for item in feed.entries[:50]:

                title = getattr(
                    item,
                    "title",
                    ""
                ).strip()

                summary = getattr(
                    item,
                    "summary",
                    ""
                ).strip()

                link = getattr(
                    item,
                    "link",
                    ""
                ).strip()

                if not title or not link:
                    continue

                published_at = parse_publish_time(
                    item
                )

                # ------------------------------------------------
                # 没有时间：
                # 不猜测
                # ------------------------------------------------

                if not published_at:
                    continue

                # ------------------------------------------------
                # 时间窗口
                # ------------------------------------------------

                if published_at < since:
                    continue

                article = {
                    "title": title,
                    "summary": summary,
                    "source": source,
                    "published_at": published_at,
                    "published": format_publish_time(
                        published_at
                    ),
                    "url": link,
                }

                processed = process_article(
                    article
                )

                if processed is None:
                    continue

                articles.append(
                    processed
                )

                source_count += 1

            print(
                f"{source} 获取到 "
                f"{source_count} 条有效新闻"
            )

        except Exception as e:

            print(
                f"{source} 获取失败：{e}"
            )

    return articles


# ============================================================
# 去重 + 合并
# ============================================================

def deduplicate_articles(articles):

    merged_articles = []

    for article in articles:

        duplicate_index = None

        for index, existing in enumerate(
            merged_articles
        ):

            if is_duplicate_event(
                article,
                [existing]
            ):
                duplicate_index = index
                break

        if duplicate_index is None:

            article["sources"] = [
                article.get(
                    "source",
                    ""
                )
            ]

            article["urls"] = [
                article.get(
                    "url",
                    ""
                )
            ]

            merged_articles.append(
                article
            )

        else:

            merged_articles[
                duplicate_index
            ] = merge_duplicate_event(
                merged_articles[
                    duplicate_index
                ],
                article
            )

    return merged_articles


# ============================================================
# 展示规则
#
# 最重要的地方：
#
# Score > 40
#     → 全部保留
#
# Score <= 40
#     → 按分类最多10条
#
# 不足10条
#     → 有几条展示几条
#
# 不再存在：
#     TOP10总量限制
# ============================================================

def select_display_news(articles):

    high_weight = [
        article
        for article in articles
        if article.get(
            "score",
            0
        ) > HIGH_WEIGHT_THRESHOLD
    ]

    low_weight = [
        article
        for article in articles
        if article.get(
            "score",
            0
        ) <= HIGH_WEIGHT_THRESHOLD
    ]

    # --------------------------------------------------------
    # 高权重：
    # 不限制数量
    # --------------------------------------------------------

    high_weight.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get(
                "published_at",
                datetime.min.replace(
                    tzinfo=timezone.utc
                )
            )
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # 低权重：
    # 每个分类最多10条
    # --------------------------------------------------------

    category_buckets = {}

    for article in low_weight:

        category = article.get(
            "category",
            "全球金融市场"
        )

        if category not in category_buckets:
            category_buckets[category] = []

        category_buckets[
            category
        ].append(article)

    low_weight_selected = []

    for category, items in category_buckets.items():

        items.sort(
            key=lambda x: (
                x.get("score", 0),
                x.get(
                    "published_at",
                    datetime.min.replace(
                        tzinfo=timezone.utc
                    )
                )
            ),
            reverse=True
        )

        selected = items[
            :LOW_WEIGHT_CATEGORY_LIMIT
        ]

        low_weight_selected.extend(
            selected
        )

    # --------------------------------------------------------
    # 最终排序
    # --------------------------------------------------------

    final_articles = (
        high_weight
        + low_weight_selected
    )

    final_articles.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get(
                "published_at",
                datetime.min.replace(
                    tzinfo=timezone.utc
                )
            )
        ),
        reverse=True
    )

    return final_articles


# ============================================================
# 主函数
# ============================================================

def get_news_data():

    # --------------------------------------------------------
    # 1. 获取新闻
    # --------------------------------------------------------

    articles = fetch_news()

    print(
        "\n============================================================"
    )

    print(
        f"新闻采集完成，共获得 "
        f"{len(articles)} 条候选新闻"
    )

    print(
        "============================================================"
    )

    # --------------------------------------------------------
    # 2. 同一事件去重 / 合并
    # --------------------------------------------------------

    articles = deduplicate_articles(
        articles
    )

    print(
        f"去重 / 合并后："
        f"{len(articles)} 条"
    )

    # --------------------------------------------------------
    # 3. 按重要性排序
    # --------------------------------------------------------

    articles.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get(
                "published_at",
                datetime.min.replace(
                    tzinfo=timezone.utc
                )
            )
        ),
        reverse=True
    )

    # --------------------------------------------------------
    # 4. 应用展示规则
    # --------------------------------------------------------

    final_articles = select_display_news(
        articles
    )

    high_count = len([
        article
        for article in final_articles
        if article.get(
            "score",
            0
        ) > HIGH_WEIGHT_THRESHOLD
    ])

    low_count = len(
        final_articles
    ) - high_count

    print(
        "\n============================================================"
    )

    print(
        "新闻展示规则"
    )

    print(
        "============================================================"
    )

    print(
        f"高权重新闻（>{HIGH_WEIGHT_THRESHOLD}）："
        f"{high_count} 条"
    )

    print(
        f"低权重新闻（≤{HIGH_WEIGHT_THRESHOLD}）："
        f"{low_count} 条"
    )

    print(
        "低权重规则：每个分类最多10条"
    )

    print(
        f"最终展示："
        f"{len(final_articles)} 条"
    )

    print(
        "============================================================"
    )

    return final_articles


# ============================================================
# 测试输出
# ============================================================

if __name__ == "__main__":

    news = get_news_data()

    print(
        "\n========== 全球重大市场事件 ==========\n"
    )

    if not news:

        print(
            "数据缺失/获取失败："
            "当前没有获得有效新闻"
        )

    else:

        for index, article in enumerate(
            news,
            1
        ):

            print(
                f"{index}. "
                f"【{article.get('category', '全球金融市场')}】"
            )

            print(
                f"标题："
                f"{article.get('title', '')}"
            )

            print(
                f"核心事实："
                f"{article.get('summary', '')}"
            )

            print(
                f"事件类型："
                f"{article.get('event_type', '')}"
            )

            print(
                f"来源："
                f"{article.get('source', '')}"
            )

            print(
                f"时间："
                f"{article.get('published', '时间缺失')}"
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
                f"原文："
                f"{article.get('url', '')}"
            )

            # 如果同一事件经过多个来源验证，
            # 输出全部来源
            if len(
                article.get("sources", [])
            ) > 1:

                print(
                    f"交叉验证来源："
                    f"{', '.join(article['sources'])}"
                )

            print()
