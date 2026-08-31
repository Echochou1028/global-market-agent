import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

from ai_news_analyzer import analyze_news_list
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
# 4. 交给 AI 判断是否真正具有金融市场影响
# 5. 交给 AI 按“事件本身”进行分类
# 6. 交给 news_scoring.py 执行最终硬规则
#
# news_scoring.py 负责：
#
# 1. 影响范围：40分
# 2. 影响程度：40分
# 3. 来源可信度：20分
# 4. 总分：100分
# 5. 同一事件去重、合并
# 6. >40 分：全部保留
# 7. <=40 分：分类 Top10
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


    # feedparser 时间结构

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
    # 遍历 RSS
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
            # 每个 RSS 最多读取 50 条
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


                # 无法确认时间
                # 不猜测
                if not published_at:
                    continue


                # ------------------------------------------------
                # 时间窗口
                # ------------------------------------------------

                if published_at < since:
                    continue


                # ------------------------------------------------
                # 建立标准新闻对象
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

                    # ==================================================
                    # 以下字段交给 AI / news_scoring.py
                    # ==================================================

                    "category":
                        None,

                    "event_id":
                        None,

                    "event_key":
                        None,

                    "event_type":
                        None,

                    "core_fact":
                        None,

                    "market_impact_reason":
                        None,

                    "market_relevant":
                        None,

                }


                articles.append(
                    article
                )

                source_count += 1


            print(
                f"{source} 获取到 "
                f"{source_count} 条新闻"
            )


        except Exception as e:

            print(
                f"{source} 获取失败：{e}"
            )


    print(
        "\n============================================================"
    )

    print(
        f"新闻采集完成，共获得 "
        f"{len(articles)} 条新闻"
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
    # 从真实 RSS 新闻源获取新闻
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
    # Gemini AI 分析新闻
    #
    # AI负责：
    #
    # 1. 是否真正具有金融市场影响
    # 2. 事件本身是什么
    # 3. 新闻分类
    # 4. 核心事实
    # 5. 同一事件识别依据
    # --------------------------------------------------------

    print(
        "\n============================================================"
    )

    print(
        "进入 AI 新闻事件分析"
    )

    print(
        "============================================================"
    )


    analyzed_news = analyze_news_list(
        raw_news
    )


    # --------------------------------------------------------
    # 第三步
    # 只保留 AI 判断为真正具有金融市场影响的新闻
    #
    # 注意：
    #
    # 这里不是评分。
    #
    # 只是执行“金融市场相关性”判断。
    # --------------------------------------------------------

    market_news = [

        article

        for article in analyzed_news

        if article.get(
            "market_relevant",
            False
        ) is True

    ]


    print(
        "\n============================================================"
    )

    print(
        f"AI判断具有实际金融市场影响的新闻："
        f"{len(market_news)}"
    )

    print(
        "============================================================"
    )


    if not market_news:

        print(
            "\n数据缺失/获取失败："
            "AI分析后没有发现具有实际金融市场影响的新闻"
        )

        return []


    # --------------------------------------------------------
    # 第四步
    # 进入 news_scoring.py
    #
    # news_scoring.py 只执行已经确定的硬规则：
    #
    # 影响范围       40
    # 影响程度       40
    # 来源可信度     20
    #
    # 总分            100
    #
    # >40             全部保留
    #
    # <=40            按分类 Top10
    #
    # 同一事件         去重 / 合并
    # --------------------------------------------------------

    result = select_news(
        market_news
    )


    # --------------------------------------------------------
    # 第五步
    # 将分类结果重新整理成列表
    # --------------------------------------------------------

    final_news = []


    for category, news_list in result.items():

        for article in news_list:

            # 如果评分模块没有分类，
            # 使用 AI 已确定的分类
            article["category"] = (
                article.get(
                    "category"
                )
                or category
            )

            final_news.append(
                article
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
            )
            or datetime.min.replace(
                tzinfo=timezone.utc
            )

        ),

        reverse=True

    )


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
                f"{article.get('core_fact') or article.get('summary', '')}"
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
                f"事件类型："
                f"{article.get('event_type', '未知')}"
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
