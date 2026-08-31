import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

from news_scoring import select_news


# ============================================================
# 全球金融市场日报
# 新闻数据采集模块
#
# 本文件职责：
#
# 1. 从真实新闻源获取新闻
# 2. 解析新闻基本信息
# 3. 过滤时间窗口
# 4. 进行金融市场相关性初筛
# 5. 输出标准新闻数据
#
# news_scoring.py 负责：
#
# 1. 事件识别
# 2. 新闻分类
# 3. 同一事件去重 / 合并
# 4. 影响范围评分
# 5. 影响程度评分
# 6. 来源可信度评分
# 7. 总分计算
# 8. >40分全部保留
# 9. <=40分按分类最多10条
#
# 核心原则：
#
# 先筛选：
#     只采集对金融市场具有实际影响力的信息
#
# 再分类：
#     按“事件本身是什么”确定分类
#
# 再评分：
#     影响范围 40
#     影响程度 40
#     来源可信度 20
#
# 来源不决定新闻重要性。
#
# ============================================================


# ============================================================
# 新闻时间窗口
# ============================================================

NEWS_WINDOW_HOURS = 36


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
# 文本清洗
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = text.lower()

    # 删除 HTML
    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    # 删除 URL
    text = re.sub(
        r"https?://\S+",
        "",
        text
    )

    # 删除特殊字符
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
# 发布时间解析
# ============================================================

def parse_publish_time(item):

    candidates = [

        getattr(
            item,
            "published",
            ""
        ),

        getattr(
            item,
            "updated",
            ""
        ),

    ]

    for value in candidates:

        if not value:
            continue

        try:

            dt = parsedate_to_datetime(
                value
            )

            if dt.tzinfo is None:

                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt.astimezone(
                timezone.utc
            )

        except Exception:

            pass


    # ========================================================
    # feedparser parsed time
    # ========================================================

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
# 金融市场相关性初筛关键词
#
# 注意：
#
# 这里只负责从 RSS 海量内容中找到“可能与金融市场
# 有关”的候选新闻。
#
# 不在这里判断：
#
# - 新闻是否重大
# - 新闻影响范围
# - 新闻影响程度
# - 新闻最终评分
# - 新闻最终分类
#
# 这些全部交给 news_scoring.py。
# ============================================================

MARKET_RELEVANCE_KEYWORDS = [

    # --------------------------------------------------------
    # 宏观经济 / 央行
    # --------------------------------------------------------

    "fed",
    "federal reserve",
    "fomc",
    "interest rate",
    "rate cut",
    "rate hike",
    "inflation",
    "cpi",
    "ppi",
    "payroll",
    "employment",
    "unemployment",
    "gdp",
    "central bank",
    "monetary policy",
    "fiscal policy",

    # --------------------------------------------------------
    # 股票市场
    # --------------------------------------------------------

    "stock market",
    "stocks",
    "equity",
    "equities",
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
    "shares",

    # --------------------------------------------------------
    # AI / 半导体
    # --------------------------------------------------------

    "artificial intelligence",
    "ai model",
    "ai chip",
    "gpu",
    "semiconductor",
    "chip",
    "chips",
    "memory",
    "hbm",
    "optical",
    "optical networking",
    "data center",
    "data centre",
    "foundry",

    "nvidia",
    "amd",
    "broadcom",
    "intel",
    "tsmc",
    "asml",

    # --------------------------------------------------------
    # 公司重大事件
    # --------------------------------------------------------

    "earnings",
    "quarterly results",
    "revenue",
    "profit",
    "guidance",
    "forecast",
    "acquisition",
    "merger",
    "takeover",
    "bankruptcy",
    "ipo",

    # --------------------------------------------------------
    # 能源 / 商品
    # --------------------------------------------------------

    "oil",
    "crude",
    "brent",
    "wti",
    "opec",
    "gold",
    "silver",
    "copper",
    "natural gas",
    "commodity",
    "commodities",

    # --------------------------------------------------------
    # 外汇 / 债券
    # --------------------------------------------------------

    "dollar",
    "yen",
    "yuan",
    "forex",
    "currency",
    "treasury",
    "bond",
    "yield",

    # --------------------------------------------------------
    # 国际贸易 / 制裁
    # --------------------------------------------------------

    "tariff",
    "tariffs",
    "trade war",
    "sanction",
    "sanctions",
    "export controls",
    "export restriction",

    # --------------------------------------------------------
    # 地缘政治
    # --------------------------------------------------------

    "war",
    "conflict",
    "military",
    "missile",
    "attack",
    "strike",
    "ceasefire",
    "geopolitical",

    "iran",
    "israel",
    "russia",
    "ukraine",
    "taiwan",
    "middle east",

]


# ============================================================
# 明显非金融内容
#
# 注意：
# 这里只排除明显与金融市场无关的内容。
#
# 不再把：
#
# analysis
# opinion
# outlook
# forecast
#
# 等直接排除。
#
# 因为高影响力研究 / 观点仍然允许进入候选池，
# 最终是否保留由 news_scoring.py 判断。
# ============================================================

EXCLUDE_KEYWORDS = [

    # 娱乐
    "celebrity",
    "entertainment",
    "movie",
    "music",
    "sports",

    # 生活方式
    "travel",
    "food",
    "restaurant",
    "lifestyle",

]


# ============================================================
# 关键词匹配
# ============================================================

def contains_keyword(
    text,
    keyword
):

    text = clean_text(text)

    keyword = clean_text(keyword)

    if not text or not keyword:

        return False

    # 多词关键词
    if " " in keyword:

        return keyword in text

    # 单词关键词使用完整单词
    pattern = rf"\b{re.escape(keyword)}\b"

    return re.search(
        pattern,
        text
    ) is not None


# ============================================================
# 判断是否明显非金融内容
# ============================================================

def is_excluded(
    title,
    summary=""
):

    text = clean_text(
        f"{title} {summary}"
    )

    for keyword in EXCLUDE_KEYWORDS:

        if contains_keyword(
            text,
            keyword
        ):

            return True

    return False


# ============================================================
# 判断是否可能与金融市场相关
#
# 重要：
#
# 这里是“候选池初筛”，不是最终重要性判断。
#
# ============================================================

def is_market_relevant(
    title,
    summary=""
):

    text = clean_text(
        f"{title} {summary}"
    )

    # --------------------------------------------------------
    # 第一层：明显非金融内容
    # --------------------------------------------------------

    if is_excluded(
        title,
        summary
    ):

        return False


    # --------------------------------------------------------
    # 第二层：金融市场相关关键词
    # --------------------------------------------------------

    for keyword in MARKET_RELEVANCE_KEYWORDS:

        if contains_keyword(
            text,
            keyword
        ):

            return True


    return False


# ============================================================
# 获取原始新闻
# ============================================================

def get_raw_news():

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


    # ========================================================
    # 遍历 RSS 新闻源
    # ========================================================

    for source, url in NEWS_FEEDS.items():

        print(
            f"\n正在获取新闻源：{source}"
        )

        try:

            feed = feedparser.parse(
                url
            )


            if getattr(
                feed,
                "bozo",
                False
            ):

                print(
                    f"警告：{source} RSS解析异常"
                )


            source_count = 0


            # ------------------------------------------------
            # 最多读取前50条
            # ------------------------------------------------

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


                # ------------------------------------------------
                # 基础字段检查
                # ------------------------------------------------

                if not title:

                    continue

                if not link:

                    continue


                # ------------------------------------------------
                # 发布时间
                # ------------------------------------------------

                published_at = (
                    parse_publish_time(
                        item
                    )
                )


                # ------------------------------------------------
                # 无法确认发布时间
                #
                # 不猜测
                # ------------------------------------------------

                if not published_at:

                    continue


                # ------------------------------------------------
                # 时间窗口
                # ------------------------------------------------

                if published_at < since:

                    continue


                # ------------------------------------------------
                # 市场相关性初筛
                # ------------------------------------------------

                if not is_market_relevant(
                    title,
                    summary
                ):

                    continue


                # ------------------------------------------------
                # 标准新闻对象
                # ------------------------------------------------

                article = {

                    "title":
                        title,

                    "summary":
                        summary,

                    "source":
                        source,

                    "source_type":
                        "major_media",

                    "published":
                        format_publish_time(
                            published_at
                        ),

                    "published_at":
                        published_at,

                    "url":
                        link,

                    # 后续由 news_scoring.py 确定
                    "category":
                        None,

                    # 后续由 news_scoring.py 确定
                    "event_id":
                        None,

                    # 候选池标记
                    "market_relevant":
                        True,

                }


                articles.append(
                    article
                )

                source_count += 1


            print(
                f"{source} 获取到 "
                f"{source_count} 条候选新闻"
            )


        except Exception as e:

            print(
                f"{source} 获取失败：{e}"
            )


    # ========================================================
    # 采集结果
    # ========================================================

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


    return articles


# ============================================================
# 获取最终新闻
# ============================================================

def get_news_data():

    # --------------------------------------------------------
    # 第一步
    # 获取真实新闻
    # --------------------------------------------------------

    raw_news = get_raw_news()


    if not raw_news:

        print(
            "\n数据缺失/获取失败："
            "当前新闻源没有获得有效新闻"
        )

        return []


    # --------------------------------------------------------
    # 第二步
    # 进入统一评分 / 事件识别 / 分类模块
    # --------------------------------------------------------

    try:

        result = select_news(
            raw_news
        )

    except Exception as e:

        print(
            "\n新闻评分模块执行失败："
            f"{e}"
        )

        print(
            "数据缺失/获取失败："
            "无法生成最终新闻结果"
        )

        return []


    # --------------------------------------------------------
    # 第三步
    # 整理分类结果
    #
    # select_news() 返回：
    #
    # {
    #     "宏观经济与央行政策": [...],
    #     "AI与半导体": [...],
    #     ...
    # }
    #
    # --------------------------------------------------------

    final_news = []


    if not result:

        print(
            "\n数据缺失/获取失败："
            "评分模块没有返回有效新闻"
        )

        return []


    for category, news_list in result.items():

        if not news_list:

            continue


        for article in news_list:

            article["category"] = category

            final_news.append(
                article
            )


    # --------------------------------------------------------
    # 最终排序
    #
    # 第一排序：
    #     总分
    #
    # 第二排序：
    #     发布时间
    #
    # 高分优先
    # 同分情况下最新优先
    # --------------------------------------------------------

    final_news.sort(
        key=lambda x: (
            x.get(
                "score",
                0
            ),

            x.get(
                "published_at"
            ) or datetime.min.replace(
                tzinfo=timezone.utc
            )

        ),
        reverse=True
    )


    # --------------------------------------------------------
    # 输出统计
    # --------------------------------------------------------

    print(
        "\n============================================================"
    )

    print(
        f"最终新闻数量："
        f"{len(final_news)}"
    )

    print(
        "============================================================"
    )


    return final_news


# ============================================================
# 测试
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
                f"【{article.get('category', '未分类')}】"
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
                f"来源："
                f"{article.get('source', '未知')}"
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

            print()
