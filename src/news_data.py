import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

from ai_news_analyzer import analyze_news_list
from news_scoring import select_news


# ============================================================
# 全球金融市场日报
# 新闻数据采集与分层过滤模块
# ============================================================

NEWS_WINDOW_HOURS = 36

# ============================================================
# RSS 新闻源配置
# ============================================================

NEWS_FEEDS = {
    # CNBC 系列
    "CNBC Markets": "https://www.cnbc.com/id/15839135/device/rss/rss.html",
    "CNBC Finance": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
    "CNBC World News": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
    "CNBC Top News": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    
    # BBC
    "BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    
    # 补充国际主流财经源
    "Reuters Business": "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    "WSJ Markets": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "FT World Economy": "https://www.ft.com/world-uk?format=rss",
    "MarketWatch Top Stories": "https://feeds.content.dowjones.io/public/rss/mw_topstories"
}

# 二维决策矩阵：[scope][degree] -> "keep" | "low_weight" | "discard"
DECISION_MATRIX = {
    "global": {
        "very_high": "keep",
        "high": "keep",
        "medium": "keep",
        "low": "low_weight",
    },
    "multi_region": {
        "very_high": "keep",
        "high": "keep",
        "medium": "keep",
        "low": "low_weight",
    },
    "regional": {
        "very_high": "keep",
        "high": "keep",
        "medium": "low_weight",
        "low": "low_weight",
    },
    "country": {
        "very_high": "keep",
        "high": "keep",
        "medium": "low_weight",
        "low": "low_weight",
    },
    "industry": {
        "very_high": "keep",
        "high": "keep",
        "medium": "low_weight",
        "low": "discard",
    },
    "company": {
        "very_high": "keep",
        "high": "keep",
        "medium": "low_weight",
        "low": "discard",
    },
    "limited": {
        "very_high": "keep",
        "high": "keep",
        "medium": "low_weight",
        "low": "discard",
    },
}

LOW_WEIGHT_CATEGORY_LIMIT = 5  # 低权重池单分类保留上限


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
            feed = feedparser.parse(url)
            if getattr(feed, "bozo", False):
                print(f"警告：{source} RSS解析可能存在异常")

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
# 分层阈值与熔断筛选逻辑
# ============================================================

def evaluate_tier(article):
    """根据 scope × degree 查表判定流向档位，不使用来源可信度"""
    # 安全获取并转换 scope（优先获取 _level 字段，兜底 _scope 字段）
    scope_val = article.get("impact_scope_level") or article.get("impact_scope") or "limited"
    scope = str(scope_val).lower() if isinstance(scope_val, (str, int, float)) else "limited"

    # 安全获取并转换 degree（优先获取 _level 字段，兜底 _degree 字段）
    degree_val = article.get("impact_degree_level") or article.get("impact_degree") or "low"
    degree = str(degree_val).lower() if isinstance(degree_val, (str, int, float)) else "low"

    # 查表获取决策
    scope_dict = DECISION_MATRIX.get(scope, DECISION_MATRIX.get("limited", {}))
    decision = scope_dict.get(degree, "discard")

    return decision


def filter_by_tiered_thresholds(analyzed_news):
    """
    分层阈值过滤逻辑：
    1. keep 档：无条件全额保留
    2. low_weight 档：进入低权重池，按分类限制 Top N（基于 score 降序）
    3. discard 档：直接过滤
    """
    keep_list = []
    low_weight_map = {}  # { category: [article, ...] }

    for article in analyzed_news:
        if not article.get("market_relevant", False):
            continue

        decision = evaluate_tier(article)

        if decision == "keep":
            keep_list.append(article)
        elif decision == "low_weight":
            cat = article.get("category") or "未分类"
            if cat not in low_weight_map:
                low_weight_map[cat] = []
            low_weight_map[cat].append(article)

    # 处理低权重池：按 score 排序并截断
    low_weight_retained = []
    for cat, items in low_weight_map.items():
        items.sort(key=lambda x: x.get("score", 0), reverse=True)
        low_weight_retained.extend(items[:LOW_WEIGHT_CATEGORY_LIMIT])

    total_selected = keep_list + low_weight_retained

    # 熔断保底规则：若极端情况下过滤完一条不剩，退化保留最高分前 5 条
    if not total_selected and analyzed_news:
        print("\n[警告] 触发熔断保护：分层过滤后无保留新闻，执行保底逻辑策略")
        fallback_pool = [a for a in analyzed_news if a.get("market_relevant")]
        fallback_pool.sort(key=lambda x: x.get("score", 0), reverse=True)
        total_selected = fallback_pool[:5]

    return total_selected


# ============================================================
# 获取最终新闻
# ============================================================

def get_news_data():
    # 1. 抓取 RSS 原始新闻
    raw_news = get_raw_news()
    if not raw_news:
        print("\n数据缺失/获取失败：当前新闻源没有获得有效新闻")
        return []

    # 2. AI 分析新闻
    print("\n============================================================")
    print("进入 AI 新闻事件分析")
    print("============================================================")
    analyzed_news = analyze_news_list(raw_news)

    # 3. 经过 news_scoring.py（打分、同一事件去重合并）
    scored_news = select_news(analyzed_news)
    
    # 展平 select_news 输出的分类字典
    flat_scored_news = []
    if isinstance(scored_news, dict):
        for cat, n_list in scored_news.items():
            for art in n_list:
                art["category"] = art.get("category") or cat
                flat_scored_news.append(art)
    else:
        flat_scored_news = scored_news

    # 4. 执行分层阈值 + 熔断规则筛选
    print("\n============================================================")
    print("应用【分层阈值 + 熔断规则】进行精细化筛选")
    print("============================================================")
    filtered_news = filter_by_tiered_thresholds(flat_scored_news)

    # 5. 按照 score 及时间全局降序排列（用于展示）
    filtered_news.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get("published_at") or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True
    )

    print("\n============================================================")
    print(f"最终入选日报新闻数量：{len(filtered_news)}")
    print("============================================================")

    return filtered_news


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
            print(f"范围/程度：{article.get('impact_scope', 'N/A')} / {article.get('impact_degree', 'N/A')}")
            print(f"展示综合得分：{article.get('score', 0)}")
            print(f"原文：{article.get('url', '')}")
            print()
