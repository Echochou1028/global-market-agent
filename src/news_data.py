"""
Global Market Agent
第三部分：全球重大市场事件与政策

功能：
1. 获取上一报告周期至当前时间的金融市场相关新闻
2. 新闻相关性过滤
3. 新闻分类
4. 同一事件去重
5. 重要性评分
6. 全局统一排序
7. 输出 TOP10

真实性原则：
- 新闻必须来自真实媒体或官方机构
- 保留来源、发布时间、原文链接
- 不生成不存在的新闻
- 不使用未经验证的市场传闻
- 数据/新闻获取失败必须明确记录
"""

from __future__ import annotations

import re
import html
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

import feedparser


# ============================================================
# 日志
# ============================================================

logger = logging.getLogger(__name__)


# ============================================================
# 配置
# ============================================================

# 上一报告周期至当前时间。
# 08:15 运行时，主要覆盖前一天 08:15 至当天 08:15。
NEWS_WINDOW_HOURS = 36

# 最终 TOP10
TOP_N = 10

# 新闻池最低候选数量
MAX_CANDIDATES = 100


# ============================================================
# 可信新闻源
# ============================================================

NEWS_SOURCES = [
    {
        "name": "CNBC Finance",
        "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "priority": 9,
    },
    {
        "name": "CNBC World News",
        "url": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
        "priority": 8,
    },
    {
        "name": "CNBC Top News",
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "priority": 8,
    },
    {
        "name": "Federal Reserve",
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "priority": 10,
    },
    {
        "name": "BLS",
        "url": "https://www.bls.gov/feed/bls_latest.rss",
        "priority": 10,
    },
    {
        "name": "BEA",
        "url": "https://www.bea.gov/news/rss.xml",
        "priority": 10,
    },
    {
        "name": "BBC Business",
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "priority": 7,
    },
]


# ============================================================
# 第三部分分类
# ============================================================

CATEGORY_KEYWORDS = {
    "宏观经济与央行政策": [
        "fed",
        "federal reserve",
        "fomc",
        "interest rate",
        "rate cut",
        "rate hike",
        "central bank",
        "ecb",
        "boj",
        "bank of japan",
        "pboc",
        "bank of england",
        "inflation",
        "cpi",
        "ppi",
        "jobs",
        "employment",
        "payroll",
        "unemployment",
        "gdp",
        "retail sales",
        "economic growth",
        "consumer confidence",
        "treasury yield",
        "bond yield",
        "美元",
        "美联储",
        "利率",
        "通胀",
        "就业",
        "非农",
        "gdp",
        "央行",
    ],

    "AI与半导体": [
        "artificial intelligence",
        "artificial-intelligence",
        "ai ",
        "ai model",
        "ai chip",
        "gpu",
        "nvidia",
        "amd",
        "broadcom",
        "tsmc",
        "semiconductor",
        "chip",
        "chips",
        "hbm",
        "memory",
        "foundry",
        "data center",
        "data centre",
        "openai",
        "anthropic",
        "google ai",
        "microsoft ai",
        "ai regulation",
        "chip export",
        "semiconductor export",
        "英伟达",
        "英特尔",
        "台积电",
        "半导体",
        "芯片",
        "人工智能",
    ],

    "能源与大宗商品": [
        "oil",
        "crude",
        "brent",
        "wti",
        "natural gas",
        "gasoline",
        "opec",
        "opec+",
        "gold",
        "silver",
        "copper",
        "commodity",
        "commodities",
        "energy",
        "原油",
        "布伦特",
        "天然气",
        "黄金",
        "白银",
        "铜",
        "大宗商品",
        "能源",
    ],

    "全球金融市场": [
        "stock market",
        "stocks",
        "equities",
        "s&p 500",
        "nasdaq",
        "dow",
        "nikkei",
        "kospi",
        "hang seng",
        "hong kong",
        "china stocks",
        "a-shares",
        "market selloff",
        "market rally",
        "sell-off",
        "rally",
        "volatility",
        "vix",
        "currency",
        "dollar",
        "yen",
        "yuan",
        "forex",
        "market crash",
        "股市",
        "美股",
        "港股",
        "A股",
        "汇率",
        "美元",
        "波动",
        "暴跌",
        "暴涨",
    ],

    "公司重大事件": [
        "earnings",
        "quarterly results",
        "revenue",
        "profit",
        "guidance",
        "forecast",
        "outlook",
        "acquisition",
        "merger",
        "takeover",
        "ipo",
        "bankruptcy",
        "layoffs",
        "shares",
        "stock",
        "nvidia",
        "apple",
        "microsoft",
        "amazon",
        "alphabet",
        "meta",
        "tesla",
        "broadcom",
        "amd",
        "intel",
        "tsmc",
        "财报",
        "业绩",
        "指引",
        "并购",
        "收购",
        "裁员",
        "破产",
    ],

    "地缘政治与制裁": [
        "war",
        "military",
        "missile",
        "attack",
        "strike",
        "conflict",
        "ceasefire",
        "sanctions",
        "tariff",
        "trade war",
        "china",
        "taiwan",
        "ukraine",
        "russia",
        "israel",
        "iran",
        "middle east",
        "north korea",
        "south china sea",
        "export controls",
        "制裁",
        "关税",
        "贸易战",
        "战争",
        "军事",
        "冲突",
        "乌克兰",
        "俄罗斯",
        "伊朗",
        "以色列",
        "台湾",
    ],
}


# ============================================================
# 金融市场相关性关键词
# ============================================================

MARKET_RELEVANCE_KEYWORDS = [
    # 宏观
    "fed",
    "federal reserve",
    "fomc",
    "interest rate",
    "rate cut",
    "rate hike",
    "inflation",
    "cpi",
    "ppi",
    "gdp",
    "employment",
    "payroll",
    "unemployment",
    "central bank",

    # 市场
    "stock",
    "stocks",
    "equity",
    "equities",
    "s&p",
    "nasdaq",
    "dow",
    "nikkei",
    "kospi",
    "hang seng",
    "market",
    "bond",
    "treasury",
    "yield",
    "dollar",
    "forex",
    "currency",
    "vix",
    "volatility",

    # 商品
    "oil",
    "crude",
    "brent",
    "wti",
    "gold",
    "copper",
    "natural gas",
    "opec",

    # 科技
    "nvidia",
    "amd",
    "broadcom",
    "tsmc",
    "intel",
    "semiconductor",
    "chip",
    "artificial intelligence",
    "ai",
    "gpu",
    "hbm",
    "data center",

    # 公司
    "earnings",
    "revenue",
    "profit",
    "guidance",
    "forecast",
    "merger",
    "acquisition",
    "bankruptcy",

    # 地缘
    "war",
    "sanctions",
    "tariff",
    "trade war",
    "ukraine",
    "russia",
    "iran",
    "israel",
    "taiwan",
    "china",

    # 中文
    "美联储",
    "利率",
    "通胀",
    "就业",
    "非农",
    "GDP",
    "股市",
    "美股",
    "港股",
    "A股",
    "黄金",
    "原油",
    "芯片",
    "半导体",
    "人工智能",
    "财报",
    "制裁",
    "关税",
    "战争",
]


# ============================================================
# 重要性关键词
# ============================================================

HIGH_IMPACT_KEYWORDS = [
    "fed",
    "fomc",
    "interest rate",
    "rate cut",
    "rate hike",
    "inflation",
    "cpi",
    "payroll",
    "gdp",
    "central bank",

    "nvidia",
    "amd",
    "broadcom",
    "tsmc",
    "semiconductor",
    "chip export",
    "artificial intelligence",

    "opec",
    "oil",
    "crude",
    "gold",

    "market crash",
    "sell-off",
    "selloff",
    "surge",
    "plunge",
    "record high",
    "record low",

    "war",
    "sanctions",
    "tariff",
    "trade war",
    "military attack",

    "earnings",
    "guidance",
    "acquisition",
    "bankruptcy",

    "美联储",
    "利率",
    "通胀",
    "非农",
    "GDP",
    "芯片",
    "半导体",
    "原油",
    "黄金",
    "暴跌",
    "暴涨",
    "制裁",
    "关税",
    "战争",
]


# ============================================================
# 工具函数
# ============================================================

def clean_text(text: str) -> str:
    """清理 HTML、实体及多余空格。"""

    if not text:
        return ""

    text = html.unescape(text)

    text = re.sub(r"<[^>]+>", " ", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_title(title: str) -> str:
    """
    用于新闻去重。
    不修改最终展示标题。
    """

    title = clean_text(title).lower()

    # 去除常见媒体前缀
    title = re.sub(
        r"^(breaking|update|exclusive|live)\s*[:\-]\s*",
        "",
        title,
    )

    # 去除标点
    title = re.sub(r"[^\w\u4e00-\u9fff]+", " ", title)

    # 删除常见无意义词
    stop_words = {
        "the",
        "a",
        "an",
        "to",
        "of",
        "for",
        "and",
        "in",
        "on",
        "at",
        "says",
        "said",
    }

    words = [
        word
        for word in title.split()
        if word not in stop_words
    ]

    return " ".join(words)


def title_hash(title: str) -> str:
    return hashlib.md5(
        normalize_title(title).encode("utf-8")
    ).hexdigest()


def parse_publish_time(entry) -> Optional[datetime]:
    """
    尽可能从 RSS 中取得真实发布时间。
    """

    candidates = [
        entry.get("published"),
        entry.get("updated"),
        entry.get("created"),
    ]

    for value in candidates:

        if not value:
            continue

        try:
            dt = parsedate_to_datetime(value)

            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return dt.astimezone(timezone.utc)

        except Exception:
            pass

    # feedparser parsed time
    for field in [
        "published_parsed",
        "updated_parsed",
        "created_parsed",
    ]:

        parsed = entry.get(field)

        if parsed:

            try:
                return datetime(
                    parsed.tm_year,
                    parsed.tm_mon,
                    parsed.tm_mday,
                    parsed.tm_hour,
                    parsed.tm_min,
                    parsed.tm_sec,
                    tzinfo=timezone.utc,
                )

            except Exception:
                pass

    return None


def get_entry_url(entry) -> str:
    """
    获取新闻原文链接。
    """

    link = entry.get("link")

    if link:
        return link.strip()

    links = entry.get("links", [])

    for item in links:

        href = item.get("href")

        if href:
            return href.strip()

    return ""


def classify_news(title: str, summary: str) -> str:
    """
    新闻分类。

    分类顺序采用市场影响优先级。
    """

    text = f"{title} {summary}".lower()

    scores = {}

    for category, keywords in CATEGORY_KEYWORDS.items():

        score = 0

        for keyword in keywords:

            if keyword.lower() in text:
                score += 1

        scores[category] = score

    best_category = max(
        scores,
        key=scores.get,
    )

    if scores[best_category] == 0:
        return "其他重大市场事件"

    return best_category


def is_market_relevant(title: str, summary: str) -> bool:
    """
    判断新闻是否与金融市场存在明确关联。

    注意：
    宁缺毋滥。
    """

    text = f"{title} {summary}".lower()

    for keyword in MARKET_RELEVANCE_KEYWORDS:

        if keyword.lower() in text:
            return True

    return False


def calculate_importance(
    title: str,
    summary: str,
    source_priority: int,
    published_at: Optional[datetime],
) -> int:
    """
    重要性评分。

    总分 100：

    市场影响范围      0-30
    市场影响程度      0-25
    时效性            0-20
    确定性            0-15
    来源可信度        0-10
    """

    text = f"{title} {summary}".lower()

    # --------------------------------------------------------
    # 1. 市场影响范围：0-30
    # --------------------------------------------------------

    impact_scope = 5

    broad_keywords = [
        "global",
        "world",
        "fed",
        "fomc",
        "central bank",
        "interest rate",
        "tariff",
        "trade war",
        "war",
        "sanctions",
        "opec",
        "gdp",
        "inflation",
        "美联储",
        "央行",
        "关税",
        "战争",
        "制裁",
    ]

    scope_hits = sum(
        1
        for keyword in broad_keywords
        if keyword.lower() in text
    )

    if scope_hits >= 3:
        impact_scope = 30
    elif scope_hits == 2:
        impact_scope = 25
    elif scope_hits == 1:
        impact_scope = 18
    else:
        impact_scope = 10

    # --------------------------------------------------------
    # 2. 影响程度：0-25
    # --------------------------------------------------------

    impact_level = 5

    high_hits = sum(
        1
        for keyword in HIGH_IMPACT_KEYWORDS
        if keyword.lower() in text
    )

    if high_hits >= 4:
        impact_level = 25
    elif high_hits >= 3:
        impact_level = 22
    elif high_hits >= 2:
        impact_level = 18
    elif high_hits >= 1:
        impact_level = 12
    else:
        impact_level = 5

    # --------------------------------------------------------
    # 3. 时效性：0-20
    # --------------------------------------------------------

    timeliness = 5

    if published_at:

        now = datetime.now(timezone.utc)

        hours = (
            now - published_at
        ).total_seconds() / 3600

        if hours <= 6:
            timeliness = 20
        elif hours <= 12:
            timeliness = 18
        elif hours <= 24:
            timeliness = 15
        elif hours <= 36:
            timeliness = 10
        else:
            timeliness = 3

    # --------------------------------------------------------
    # 4. 确定性：0-15
    # --------------------------------------------------------

    certainty = 10

    uncertain_words = [
        "may",
        "might",
        "could",
        "reportedly",
        "sources say",
        "rumor",
        "rumoured",
        "rumored",
        "可能",
        "据传",
        "传闻",
    ]

    uncertain_hits = sum(
        1
        for keyword in uncertain_words
        if keyword.lower() in text
    )

    if uncertain_hits >= 2:
        certainty = 2
    elif uncertain_hits == 1:
        certainty = 5
    else:
        certainty = 15

    # --------------------------------------------------------
    # 5. 来源可信度：0-10
    # --------------------------------------------------------

    source_score = min(
        10,
        max(
            5,
            source_priority,
        ),
    )

    total = (
        impact_scope
        + impact_level
        + timeliness
        + certainty
        + source_score
    )

    return min(100, total)


def create_event(
    entry,
    source: Dict,
) -> Optional[Dict]:
    """
    将 RSS entry 转换成标准事件结构。
    """

    title = clean_text(
        entry.get("title", "")
    )

    summary = clean_text(
        entry.get("summary", "")
        or entry.get("description", "")
    )

    url = get_entry_url(entry)

    published_at = parse_publish_time(entry)

    if not title or not url:
        return None

    if not is_market_relevant(
        title,
        summary,
    ):
        return None

    category = classify_news(
        title,
        summary,
    )

    score = calculate_importance(
        title,
        summary,
        source["priority"],
        published_at,
    )

    return {
        "category": category,
        "title": title,
        "fact": summary,
        "impact": "",
        "source": source["name"],
        "published_at": published_at,
        "url": url,
        "score": score,
        "dedup_key": title_hash(title),
    }


# ============================================================
# 获取 RSS 新闻
# ============================================================

def fetch_feed(
    source: Dict,
    since: datetime,
) -> List[Dict]:

    logger.info(
        "正在获取新闻源：%s",
        source["name"],
    )

    events = []

    try:

        feed = feedparser.parse(
            source["url"]
        )

        if getattr(
            feed,
            "bozo",
            False,
        ):
            logger.warning(
                "新闻源解析异常：%s",
                source["name"],
            )

        for entry in feed.entries:

            published_at = parse_publish_time(
                entry
            )

            # 没有真实发布时间：
            # 不猜测，不使用。
            if published_at is None:
                logger.warning(
                    "新闻缺少明确发布时间，跳过：%s",
                    entry.get("title", ""),
                )
                continue

            if published_at < since:
                continue

            event = create_event(
                entry,
                source,
            )

            if event:
                events.append(event)

    except Exception as exc:

        logger.warning(
            "新闻源获取失败：%s | %s",
            source["name"],
            exc,
        )

    logger.info(
        "%s 获取到 %d 条候选新闻",
        source["name"],
        len(events),
    )

    return events


# ============================================================
# 新闻去重
# ============================================================

def deduplicate_events(
    events: List[Dict],
) -> List[Dict]:

    grouped = {}

    for event in events:

        key = event["dedup_key"]

        if key not in grouped:

            grouped[key] = event

        else:

            old = grouped[key]

            # 同一事件：
            # 保留评分更高的来源。
            if event["score"] > old["score"]:
                grouped[key] = event

    return list(
        grouped.values()
    )


# ============================================================
# 二次相似标题去重
# ============================================================

def title_similarity_key(
    title: str,
) -> set:

    normalized = normalize_title(
        title
    )

    return set(
        normalized.split()
    )


def merge_similar_events(
    events: List[Dict],
) -> List[Dict]:

    result = []

    for event in events:

        current_words = title_similarity_key(
            event["title"]
        )

        duplicate = False

        for existing in result:

            existing_words = title_similarity_key(
                existing["title"]
            )

            if not current_words or not existing_words:
                continue

            intersection = (
                current_words
                & existing_words
            )

            union = (
                current_words
                | existing_words
            )

            similarity = (
                len(intersection)
                / len(union)
            )

            # 标题高度相似，视为同一事件
            if similarity >= 0.65:

                duplicate = True

                if (
                    event["score"]
                    > existing["score"]
                ):
                    result.remove(existing)
                    result.append(event)

                break

        if not duplicate:
            result.append(event)

    return result


# ============================================================
# 时间格式化
# ============================================================

def format_datetime(
    dt: Optional[datetime],
) -> str:

    if dt is None:
        return "时间缺失"

    # 报告统一显示北京时间
    china_tz = timezone(
        timedelta(hours=8)
    )

    dt = dt.astimezone(
        china_tz
    )

    return dt.strftime(
        "%Y-%m-%d %H:%M"
    )


# ============================================================
# 主函数
# ============================================================

def get_major_market_events(
    hours: int = NEWS_WINDOW_HOURS,
    top_n: int = TOP_N,
) -> List[Dict]:

    logger.info(
        "============================================================"
    )

    logger.info(
        "开始获取全球重大市场事件"
    )

    logger.info(
        "新闻时间窗口：最近 %d 小时",
        hours,
    )

    since = (
        datetime.now(timezone.utc)
        - timedelta(hours=hours)
    )

    all_events = []

    # --------------------------------------------------------
    # 1. 获取所有新闻源
    # --------------------------------------------------------

    for source in NEWS_SOURCES:

        events = fetch_feed(
            source,
            since,
        )

        all_events.extend(
            events
        )

    logger.info(
        "原始新闻池：%d 条",
        len(all_events),
    )

    if not all_events:

        logger.warning(
            "新闻池为空：数据缺失/获取失败"
        )

        return []

    # --------------------------------------------------------
    # 2. 第一轮去重
    # --------------------------------------------------------

    events = deduplicate_events(
        all_events
    )

    logger.info(
        "第一次去重后：%d 条",
        len(events),
    )

    # --------------------------------------------------------
    # 3. 相似标题去重
    # --------------------------------------------------------

    events = merge_similar_events(
        events
    )

    logger.info(
        "第二次去重后：%d 条",
        len(events),
    )

    # --------------------------------------------------------
    # 4. 统一排序
    # --------------------------------------------------------

    events.sort(
        key=lambda x: (
            x["score"],
            x["published_at"]
            or datetime.min.replace(
                tzinfo=timezone.utc
            ),
        ),
        reverse=True,
    )

    # --------------------------------------------------------
    # 5. TOP10
    # --------------------------------------------------------

    top_events = events[
        :top_n
    ]

    # --------------------------------------------------------
    # 6. 输出标准字段
    # --------------------------------------------------------

    result = []

    for index, event in enumerate(
        top_events,
        start=1,
    ):

        result.append(
            {
                "rank": index,
                "category": event[
                    "category"
                ],
                "title": event[
                    "title"
                ],
                "fact": event[
                    "fact"
                ],
                "impact": event[
                    "impact"
                ],
                "source": event[
                    "source"
                ],
                "published_at": format_datetime(
                    event[
                        "published_at"
                    ]
                ),
                "url": event[
                    "url"
                ],
                "score": event[
                    "score"
                ],
            }
        )

    logger.info(
        "最终 TOP%d：%d 条",
        top_n,
        len(result),
    )

    return result


# ============================================================
# 独立测试
# ============================================================

if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    events = get_major_market_events()

    print()
    print(
        "========== TOP10重大市场事件 =========="
    )

    if not events:

        print(
            "数据缺失/获取失败：当前没有获得有效新闻"
        )

    else:

        for event in events:

            print()
            print(
                f'{event["rank"]}. '
                f'【{event["category"]}】'
            )

            print(
                f'标题：{event["title"]}'
            )

            print(
                f'核心事实：{event["fact"]}'
            )

            print(
                f'来源：{event["source"]}'
            )

            print(
                f'时间：{event["published_at"]}'
            )

            print(
                f'重要性评分：{event["score"]}'
            )

            print(
                f'原文：{event["url"]}'
            )
