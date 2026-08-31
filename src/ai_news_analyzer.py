import json
import os

from google import genai


# ============================================================
# Google Gemini AI 新闻分析层
#
# 本文件职责：
#
# 1. 判断新闻是否真正具有金融市场影响
# 2. 判断“事件本身是什么”
# 3. 确定新闻分类
# 4. 判断同一事件关系
# 5. 提取事件核心事实
#
# 本文件不负责：
#
# 1. 最终评分
# 2. TOP10
# 3. 新闻数量限制
# 4. 来源可信度评分
#
# 上述硬规则由 news_scoring.py 执行。
# ============================================================


# ============================================================
# Gemini 模型
# ============================================================

GEMINI_MODEL = "gemini-3.6-flash"


# ============================================================
# 初始化 Gemini
# ============================================================

def get_client():

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:

        raise RuntimeError(
            "GEMINI_API_KEY 未配置"
        )

    return genai.Client(
        api_key=api_key
    )


# ============================================================
# AI 系统规则
# ============================================================

SYSTEM_PROMPT = """
你是“全球金融市场日报 Agent”的新闻事件分析引擎。

你的任务不是判断新闻“看起来重要不重要”，
而是判断新闻事件本身是否对金融市场具有实际影响。

必须严格遵守以下原则：

一、金融市场相关性

只有对金融市场具有实际影响力的信息才进入最终新闻池。

可能影响以下市场的事件可以进入候选池：

- 全球股票市场
- 债券市场
- 外汇市场
- 能源市场
- 贵金属及大宗商品市场
- AI / 半导体产业链
- 重要上市公司
- 全球宏观经济
- 央行政策
- 国际贸易
- 制裁
- 地缘政治

普通社会新闻、娱乐、体育、生活方式新闻，
如果没有明确金融市场影响，必须判定为 false。

二、分类原则

必须按照“事件本身是什么”进行分类。

绝对不能因为文章中出现某个关键词，
就机械地按照关键词分类。

例如：

Fed加息决定
→ 宏观经济与央行政策

某公司公布财报
→ 公司重大事件

美国与加拿大提高关税
→ 地缘政治与制裁

伊朗冲突导致霍尔木兹海峡运输风险
如果核心事件是军事冲突
→ 地缘政治与制裁

如果核心事件明确是原油供应受到影响，
且文章主要讨论原油市场冲击
→ 能源与大宗商品

分类必须由事件本身决定。

允许使用以下分类：

1. 宏观经济与央行政策
2. 全球股市
3. AI与半导体
4. 能源与大宗商品
5. 外汇与债券
6. 地缘政治与制裁
7. 公司重大事件
8. 其他市场事件

三、事实原则

只能根据新闻提供的信息进行判断。

绝对禁止：

- 编造新闻
- 编造数据
- 编造公司事件
- 编造政策
- 编造市场行情
- 编造来源
- 编造引用

如果新闻无法确认事实，
必须降低可信判断，
不能自行补充事实。

四、来源原则

新闻来源可能包括：

- 官方机构
- 央行
- 政府部门
- 国际金融机构
- 权威金融媒体
- 主流国际媒体

来源本身不能决定新闻是否重要。

来源只影响后续的“来源可信度”评分。

五、分析目标

对于每条新闻：

1. 判断是否真正具有金融市场影响
2. 判断事件本身是什么
3. 确定分类
4. 提取核心事实
5. 判断是否可能与其他新闻属于同一事件

不要进行最终分数计算。

最终评分由程序执行。
"""


# ============================================================
# 单条新闻分析
# ============================================================

def analyze_news(article):

    client = get_client()

    title = article.get(
        "title",
        ""
    )

    summary = article.get(
        "summary",
        ""
    )

    source = article.get(
        "source",
        ""
    )

    url = article.get(
        "url",
        ""
    )

    prompt = f"""
请分析下面这条真实新闻。

标题：
{title}

新闻摘要：
{summary}

来源：
{source}

原文链接：
{url}

请严格返回 JSON。

JSON 格式：

{{
    "market_relevant": true,
    "event_type": "事件本身是什么",
    "category": "分类",
    "core_fact": "只根据新闻内容提取核心事实",
    "market_impact_reason": "为什么该事件可能影响金融市场",
    "event_key": "用于判断同一事件的简短事件标识"
}}

要求：

1. market_relevant 必须是 true 或 false。
2. 如果没有明确金融市场影响，market_relevant 必须为 false。
3. category 必须从以下分类中选择：

宏观经济与央行政策
全球股市
AI与半导体
能源与大宗商品
外汇与债券
地缘政治与制裁
公司重大事件
其他市场事件

4. category 必须依据事件本身决定，而不是关键词。
5. core_fact 不允许编造新闻中没有出现的事实。
6. event_key 用于识别同一事件。
7. 不要评分。
8. 不要输出 Markdown。
9. 只返回合法 JSON。
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            SYSTEM_PROMPT,
            prompt
        ]
    )

    text = response.text.strip()

    # --------------------------------------------------------
    # 清理可能出现的 Markdown JSON
    # --------------------------------------------------------

    if text.startswith("```"):

        text = text.replace(
            "```json",
            ""
        )

        text = text.replace(
            "```",
            ""
        )

        text = text.strip()

    try:

        result = json.loads(
            text
        )

    except json.JSONDecodeError:

        raise ValueError(
            f"Gemini 返回的不是合法 JSON：{text}"
        )

    return result


# ============================================================
# 批量分析新闻
# ============================================================

def analyze_news_list(
    articles
):

    analyzed = []

    print(
        "\n============================================================"
    )

    print(
        "开始使用 Gemini AI 分析新闻事件"
    )

    print(
        f"待分析新闻：{len(articles)} 条"
    )

    print(
        "============================================================"
    )

    for index, article in enumerate(
        articles,
        1
    ):

        try:

            result = analyze_news(
                article
            )

            article.update(
                result
            )

            analyzed.append(
                article
            )

            print(
                f"[{index}/{len(articles)}] "
                f"{article.get('title', '')}"
            )

            print(
                f"  金融市场相关："
                f"{result.get('market_relevant')}"
            )

            print(
                f"  分类："
                f"{result.get('category')}"
            )

            print(
                f"  事件："
                f"{result.get('event_type')}"
            )

        except Exception as e:

            print(
                f"[{index}/{len(articles)}] "
                f"AI分析失败：{e}"
            )

            # AI 分析失败时，
            # 绝不猜测，不编造
            article["market_relevant"] = False
            article["ai_analysis_failed"] = True

            analyzed.append(
                article
            )

    print(
        "\n============================================================"
    )

    print(
        f"AI 新闻分析完成：{len(analyzed)} 条"
    )

    print(
        "============================================================"
    )

    return analyzed


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":

    test_article = {

        "title":
            "Fed keeps interest rates unchanged",

        "summary":
            "The Federal Reserve kept interest rates unchanged.",

        "source":
            "CNBC Finance",

        "url":
            "https://example.com"

    }

    result = analyze_news(
        test_article
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=4
        )
    )
