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
# v2 改动：
#
# 删掉了本文件里重复的 DECISION_MATRIX / evaluate_tier /
# filter_by_tiered_thresholds ——这套"分层阈值+熔断"逻辑
# 跟 news_scoring.py 的 classify_tier() 完全等价（逐格核对过），
# 但两边参数不一致（这里 LOW_WEIGHT_CATEGORY_LIMIT=5，
# news_scoring.py 是15），叠加执行的结果是"实际按5条生效"，
# 悄悄覆盖了 news_scoring.py 那边调整过的值，且没有任何报错
# 提示这两层在打架。
#
# 分层判定只应该有一处：news_scoring.py 的 select_news()。
# 本文件现在直接使用它的输出，不再做第二遍过滤。
# ============================================================

NEWS_WINDOW_HOURS = 36


# ============================================================
# RSS 新闻源配置
#
# Reuters Business / WSJ Markets 已确认RSS失效，移除。
# 新增信源清单还在核实中（详见对话）。
# ============================================================

NEWS_FEEDS = {
    # 官方/监管一手信源（已核实真实可用）
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
    "SEC": "https://www.sec.gov/news/pressreleases.rss",

    # CNBC 系列
    "CNBC Markets": "https://search.cnbc.com/rs/search/combinedlist/view.xml?partnerId=wrss01&id=15839069",
    "CNBC Finance": "https://search.cnbc.com/rs/search/combinedlist/view.xml?partnerId=wrss01&id=10000664",
    "CNBC World News": "https://search.cnbc.com/rs/search/combinedlist/view.xml?partnerId=wrss01&id=100727362",
    "CNBC Top News": "https://search.cnbc.com/rs/search/combinedlist/view.xml?partnerId=wrss01&id=100003114",

    # 国际权威综合与经济
    "BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "FT World Economy": "https://www.ft.com/world-uk?format=rss",
    "MarketWatch Top Stories": "https://feeds.content.dowjones.io/public/rss/mw_topstories",

    # 高稳定性主流财经信源（替代失效的Reuters Business与WSJ Markets）
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    "Investing.com News": "https://www.investing.com/rss/news.rss",
    "Google News Finance": "https://news.google.com/rss/search?q=when:24h+allinurl:finance+OR+allinurl:markets&ceid=US:en&hl=en-US&gl=US",

    # 待核实：U.S. Treasury / BEA / NYSE / CME / IMF / BIS / World Bank
    # 已确认Treasury有RSS机制，但具体XML地址还没核实到，
    # 下一轮查证后再加，不猜URL。
}


# ============================================================
# 文本清洗
# ============================================================

def clean_text(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ============================================================
# 发布时间解析与格式化
# ============================================================

def parse_publish_time(item):
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
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass

    parsed = getattr(item, "published_parsed", None)
    if parsed:
        try:
            return datetime(
                parsed.tm_year, parsed.tm_mon, parsed.tm_mday,
                parsed.tm_hour, parsed.tm_min, parsed.tm_sec,
                tzinfo=timezone.utc
            )
        except Exception:
            pass

    return None


def format_publish_time(dt):
    if not dt:
        return "时间缺失"
    china_tz = timezone(timedelta(hours=8))
    return dt.astimezone(china_tz).strftime("%Y-%m-%d %H:%M")


# ============================================================
# 获取原始新闻
# ============================================================

def get_raw_news():
    articles = []
    since = datetime.now(timezone.utc) - timedelta(hours=NEWS_WINDOW_HOURS)

    print("\n============================================================")
    print("开始获取全球金融市场新闻")
    print(f"新闻时间窗口：最近 {NEWS_WINDOW_HOURS} 小时")
    print("============================================================")

    for source, url in NEWS_FEEDS.items():
        print(f"\n正在获取新闻源：{source}")
        try:
            # 加入自定义 User-Agent 提升 RSS 抓取稳定性
            feed = feedparser.parse(
                url,
                agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            if getattr(feed, "bozo", False):
                # bozo 为 1 时不一定代表完全失败，仅有轻微 XML 规范警告
                pass

            source_count = 0
            for item in feed.entries[:50]:
                title = getattr(item, "title", "").strip()
                summary = getattr(item, "summary", "").strip()
                link = getattr(item, "link", "").strip()

                if not title or not link:
                    continue

                published_at = parse_publish_time(item)
                if not published_at or published_at < since:
                    continue

                article = {
                    "title": title,
                    "summary": summary,
                    "source": source,
                    "source_type": "major_media",
                    "published": format_publish_time(published_at),
                    "published_at": published_at,
                    "url": link,
                    "category": None,
                    "event_id": None,
                    "event_key": None,
                    "event_type": None,
                    "core_fact": None,
                    "market_impact_reason": None,
                    "market_relevant": None,
                    "impact_scope": None,
                    "impact_degree": None,
                }
                articles.append(article)
                source_count += 1

            print(f"{source} 获取到 {source_count} 条新闻")

        except Exception as e:
            print(f"{source} 获取失败：{e}")

    print("\n============================================================")
    print(f"新闻采集完成，共获得 {len(articles)} 条新闻")
    print("============================================================")

    return articles


# ============================================================
# 获取最终新闻
#
# 分层判定（keep / low_weight / discard）完全交给
# news_scoring.py 的 select_news() 一处完成，本文件不再
# 重复过滤，避免两套阈值互相打架。
# ============================================================

def get_news_data():

    # --------------------------------------------------------
    # 第一步：抓取 RSS 原始新闻
    # --------------------------------------------------------

    raw_news = get_raw_news()

    if not raw_news:
        print("\n数据缺失/获取失败：当前新闻源没有获得有效新闻")
        return []

    # --------------------------------------------------------
    # 第二步：AI 分析新闻
    # --------------------------------------------------------

    print("\n============================================================")
    print("进入 AI 新闻事件分析")
    print("============================================================")

    analyzed_news = analyze_news_list(raw_news)

    # --------------------------------------------------------
    # 第三步：news_scoring.py 执行硬规则评分 +
    # 分层阈值判定（keep / low_weight / discard）+ 事件去重
    #
    # select_news() 返回的已经是最终入选新闻，
    # 按分类分好组的字典。
    # --------------------------------------------------------

    result = select_news(analyzed_news)

    final_news = []

    for category, news_list in result.items():
        for article in news_list:
            article["category"] = article.get("category") or category
            final_news.append(article)

    # --------------------------------------------------------
    # 最终排序（展示用）
    # --------------------------------------------------------

    final_news.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get("published_at") or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True
    )

    print("\n============================================================")
    print(f"最终入选日报新闻数量：{len(final_news)}")
    print("============================================================")

    return final_news


# ============================================================
# 测试运行
# ============================================================

if __name__ == "__main__":
    news = get_news_data()

    print("\n========== 全球重大市场事件 ==========\n")

    if not news:
        print("数据缺失/获取失败：当前没有获得有效新闻")
    else:
        for index, article in enumerate(news, 1):
            print(f"{index}. 【{article.get('category', '未分类')}】")
            print(f"标题：{article.get('title', '')}")
            print(f"核心事实：{article.get('core_fact') or article.get('summary', '')}")
            print(f"来源：{article.get('source', '未知')}")
            print(f"时间：{article.get('published', '时间缺失')}")
            print(f"事件类型：{article.get('event_type', '未知')}")
            print(f"影响范围：{article.get('impact_scope', 0)}")
            print(f"影响程度：{article.get('impact_degree', 0)}")
            print(f"来源可信度：{article.get('source_credibility', 0)}")
            print(f"总分：{article.get('score', 0)}")
            print(f"原文：{article.get('url', '')}")
            print()
