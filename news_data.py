import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

from ai_news_analyzer import analyze_news_list
from news_scoring import select_news

# ============================================================
# 全局默认 User-Agent (作为全局兜底)
# ============================================================
feedparser.USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ============================================================
# 全球金融市场日报
# 新闻数据采集模块
#
# 本文件职责：
# 1. 从真实新闻源获取新闻（针对不同源使用定制 Request Headers）
# 2. 解析新闻基本信息
# 3. 过滤时间窗口
# 4. 交给 AI 判断是否真正具有金融市场影响
# 5. 交给 AI 按“事件本身”进行分类
# 6. 交给 news_scoring.py 执行最终硬规则
# ============================================================


# ============================================================
# 新闻时间窗口
# ============================================================

NEWS_WINDOW_HOURS = 36


# ============================================================
# RSS 新闻源配置（支持为特定源指定独立的 Request Headers）
# ============================================================

NEWS_FEEDS = {
    # WSJ 换成稳定公开的 RSS 接口，并补充 Referer
    "WSJ Markets": {
        "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", 
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.wsj.com/"
        }
    },
    
   "Reuters Business": {
        "url": "https://news.google.com/rss/search?q=when:24h+allinurl:reuters.com/business&hl=en-US&gl=US&ceid=US:en",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
    },

    "CNBC Markets": {
        "url": "https://www.cnbc.com/id/15839135/device/rss/rss.html",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        }
    },

    "CNBC Finance": {
        "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        }
    },

    "CNBC World News": {
        "url": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        }
    },

    "CNBC Top News": {
        "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        }
    },

    "BBC Business": {
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        }
    },
}


# ============================================================
# 文本清洗
# ============================================================

def clean_text(text):
    """
    清洗新闻文本。
    当前主要用于后续新闻处理。
    不改变新闻原始标题、摘要和原文链接。
    """

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
    """
    尝试从 RSS 新闻条目中获取发布时间。
    优先使用 published / updated，如果无法解析，再使用 feedparser 的时间结构。
    无法确认时间时返回 None。
    """

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

    # --------------------------------------------------------
    # feedparser 时间结构
    # --------------------------------------------------------

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
    """
    将 UTC 时间转换为北京时间。
    """

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
    """
    从真实 RSS 新闻源获取原始新闻。

    本函数只负责：
    - 获取新闻（传入特定的 Request Headers）
    - 基础字段解析
    - 时间过滤
    """

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
    # 遍历 RSS 配置
    # ========================================================

    for source, config in NEWS_FEEDS.items():

        print(
            f"\n正在获取新闻源：{source}"
        )

        # ----------------------------------------------------
        # 解析配置：兼容字典配置与纯字符串 URL 配置
        # ----------------------------------------------------
        if isinstance(config, dict):
            url = config.get("url", "")
            headers = config.get("headers", {})
        else:
            url = config
            headers = {}

        if not url:
            print(f"错误：新闻源 {source} 未配置有效 URL")
            continue

        try:

            # 关键改进：传入 request_headers 定制请求头
            feed = feedparser.parse(
                url,
                request_headers=headers
            )

            if getattr(
                feed,
                "bozo",
                False
            ):

                print(
                    f"警告：{source} RSS解析可能存在格式异常 (bozo=1)"
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

                published_at = parse_publish_time(
                    item
                )

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

                    # AI 分析字段
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
    """
    获取最终新闻数据。
    """

    # --------------------------------------------------------
    # 第一步：从真实 RSS 新闻源获取新闻
    # --------------------------------------------------------

    raw_news = get_raw_news()

    if not raw_news:

        print(
            "\n数据缺失/获取失败："
            "当前新闻源没有获得有效新闻"
        )

        return []

    # --------------------------------------------------------
    # 第二步：AI 分析新闻
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

    try:

        analyzed_news = analyze_news_list(
            raw_news
        )

    except Exception as e:

        print(
            "\n数据缺失/获取失败："
            f"AI新闻分析失败：{e}"
        )

        return []

    if not analyzed_news:

        print(
            "\n数据缺失/获取失败："
            "AI分析没有返回有效新闻"
        )

        return []

    # --------------------------------------------------------
    # 第三步：只保留 AI 判断为真正具有金融市场影响的新闻
    # --------------------------------------------------------

    market_news = []
    for article in analyzed_news:
        if isinstance(article, dict) and article.get("market_relevant") is True:
            market_news.append(article)

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
    # 第四步：进入 news_scoring.py
    # --------------------------------------------------------

    try:

        result = select_news(
            market_news
        )

    except Exception as e:

        print(
            "\n数据缺失/获取失败："
            f"新闻评分模块执行失败：{e}"
        )

        return []

    if not result or not isinstance(result, dict):

        print(
            "\n数据缺失/获取失败："
            "新闻评分模块没有返回有效结果"
        )

        return []

    # --------------------------------------------------------
    # 第五步：整理与排序（带防御防崩溃逻辑）
    # --------------------------------------------------------

    final_news = []

    for category, news_list in result.items():

        if not news_list or not isinstance(news_list, list):
            continue

        for article in news_list:

            if not isinstance(
                article,
                dict
            ):
                continue

            article["category"] = (
                article.get(
                    "category"
                )
                or category
            )

            final_news.append(
                article
            )

    def safe_score(x):
        try:
            return float(x.get("score", 0) or 0)
        except (ValueError, TypeError):
            return 0.0

    def safe_time(x):
        published_at = x.get("published_at")
        if isinstance(published_at, datetime):
            return published_at
        return datetime.min.replace(tzinfo=timezone.utc)

    final_news.sort(
        key=lambda x: (
            safe_score(x),
            safe_time(x)
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
# 测试入口
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
                f"市场影响原因："
                f"{article.get('market_impact_reason', '')}"
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
                f"事件标识："
                f"{article.get('event_key', '未知')}"
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
