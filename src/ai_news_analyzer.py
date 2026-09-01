import json
import os

from openai import OpenAI


# ============================================================
# Groq AI 新闻分析层
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
#
# 核心架构：
#
# 新闻
# ↓
# 本地预处理
# ↓
# Groq 一次批量分析
# ↓
# 结构化 JSON
# ↓
# 本地去重 / 评分 / 排序
# ↓
# 最终日报
# ============================================================


# ============================================================
# Groq 模型
# ============================================================

GROQ_MODEL = "openai/gpt-oss-120b"


# ============================================================
# 初始化 Groq
# ============================================================

def get_client():

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:

        raise RuntimeError(
            "GROQ_API_KEY 未配置"
        )

    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1"
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

六、输出原则

你将一次性分析多条新闻。

必须按照输入新闻的 id 返回对应分析结果。

必须返回合法 JSON。

禁止输出 Markdown。

禁止输出解释文字。

禁止输出 ```json。

只允许返回 JSON 数组。
"""


# ============================================================
# 新闻预处理
# ============================================================

def prepare_articles(articles):

    prepared = []

    for index, article in enumerate(
        articles,
        1
    ):

        prepared.append({

            "id": index,

            "title":
                article.get(
                    "title",
                    ""
                ),

            "summary":
                article.get(
                    "summary",
                    ""
                ),

            "source":
                article.get(
                    "source",
                    ""
                ),

            "url":
                article.get(
                    "url",
                    ""
                )
        })

    return prepared


# ============================================================
# 批量分析
# ============================================================

def analyze_news_list(
    articles
):

    if not articles:

        return []


    client = get_client()


    prepared_articles = prepare_articles(
        articles
    )


    print(
        "\n============================================================"
    )

    print(
        "开始使用 Groq AI 批量分析新闻事件"
    )

    print(
        f"待分析新闻：{len(articles)} 条"
    )

    print(
        "分析模式：全量批量分析"
    )

    print(
        "============================================================"
    )


    # --------------------------------------------------------
    # 将所有新闻一次性组成一个 JSON 输入
    # --------------------------------------------------------

    articles_json = json.dumps(
        prepared_articles,
        ensure_ascii=False
    )


    prompt = f"""
请一次性分析下面全部新闻。

输入新闻数量：
{len(prepared_articles)}

新闻数据：

{articles_json}


请对每一条新闻进行分析。

必须返回一个 JSON 数组。

每一个数组元素必须包含：

{{
    "id": 1,
    "market_relevant": true,
    "event_type": "事件本身是什么",
    "category": "分类",
    "core_fact": "只根据新闻内容提取核心事实",
    "market_impact_reason": "为什么该事件可能影响金融市场",
    "event_key": "用于判断同一事件的简短事件标识"
}}


严格要求：

1. id 必须与输入新闻的 id 完全一致。

2. 每一条输入新闻都必须返回一个分析结果。

3. 不允许遗漏任何 id。

4. 不允许增加输入中不存在的 id。

5. market_relevant 必须是 true 或 false。

6. 如果没有明确金融市场影响，
   market_relevant 必须为 false。

7. category 必须从以下分类中选择：

宏观经济与央行政策
全球股市
AI与半导体
能源与大宗商品
外汇与债券
地缘政治与制裁
公司重大事件
其他市场事件

8. category 必须依据事件本身决定，
   不能依据关键词机械分类。

9. core_fact 只能使用输入新闻中的事实。

10. 不允许补充新闻中没有出现的信息。

11. event_key 用于识别同一事件。

12. 不要进行任何评分。

13. 不要输出 Markdown。

14. 不要输出 ```json。

15. 只返回合法 JSON 数组。
"""


    # ========================================================
    # 调用 Groq
    # ========================================================

    try:

        response = client.chat.completions.create(

            model=GROQ_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            temperature=0,

            response_format={
                "type": "json_object"
            }
        )


    except Exception as e:

        print(
            f"\nGroq AI 批量分析失败：{e}"
        )

        # ----------------------------------------------------
        # AI失败时绝不猜测
        # ----------------------------------------------------

        for article in articles:

            article[
                "market_relevant"
            ] = False

            article[
                "ai_analysis_failed"
            ] = True

        return articles


    # ========================================================
    # 获取 AI 返回结果
    # ========================================================

    text = response.choices[0].message.content.strip()


    # ========================================================
    # 清理 Markdown
    # ========================================================

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


    # ========================================================
    # 解析 JSON
    # ========================================================

    try:

        result = json.loads(
            text
        )

    except json.JSONDecodeError:

        print(
            "\nGroq 返回结果不是合法 JSON："
        )

        print(text)

        for article in articles:

            article[
                "market_relevant"
            ] = False

            article[
                "ai_analysis_failed"
            ] = True

        return articles


    # ========================================================
    # 兼容 JSON object
    #
    # 因为 response_format=json_object
    # 要求模型返回 object。
    #
    # 因此允许以下形式：
    #
    # {
    #     "results": [...]
    # }
    #
    # 或：
    #
    # {
    #     "articles": [...]
    # }
    # ========================================================

    if isinstance(
        result,
        dict
    ):

        if isinstance(
            result.get("results"),
            list
        ):

            result = result["results"]

        elif isinstance(
            result.get("articles"),
            list
        ):

            result = result["articles"]

        else:

            print(
                "\nGroq 返回 JSON object，但没有找到 results/articles 数组。"
            )

            for article in articles:

                article[
                    "market_relevant"
                ] = False

                article[
                    "ai_analysis_failed"
                ] = True

            return articles


    if not isinstance(
        result,
        list
    ):

        print(
            "\nGroq 返回的数据结构不是 JSON 数组。"
        )

        for article in articles:

            article[
                "market_relevant"
            ] = False

            article[
                "ai_analysis_failed"
            ] = True

        return articles


    # ========================================================
    # 建立 AI 分析结果索引
    # ========================================================

    result_map = {}

    for item in result:

        if not isinstance(
            item,
            dict
        ):

            continue

        item_id = item.get(
            "id"
        )

        if item_id is None:

            continue

        result_map[
            str(item_id)
        ] = item


    # ========================================================
    # 将 AI 结果重新写回原始新闻
    # ========================================================

    analyzed = []


    for index, article in enumerate(
        articles,
        1
    ):

        ai_result = result_map.get(
            str(index)
        )


        if not ai_result:

            print(
                f"[{index}/{len(articles)}] "
                f"AI分析结果缺失："
                f"{article.get('title', '')}"
            )

            article[
                "market_relevant"
            ] = False

            article[
                "ai_analysis_failed"
            ] = True

            analyzed.append(
                article
            )

            continue


        # ----------------------------------------------------
        # 写入分析结果
        # ----------------------------------------------------

        article.update({

            "market_relevant":
                ai_result.get(
                    "market_relevant",
                    False
                ),

            "event_type":
                ai_result.get(
                    "event_type",
                    ""
                ),

            "category":
                ai_result.get(
                    "category",
                    ""
                ),

            "core_fact":
                ai_result.get(
                    "core_fact",
                    ""
                ),

            "market_impact_reason":
                ai_result.get(
                    "market_impact_reason",
                    ""
                ),

            "event_key":
                ai_result.get(
                    "event_key",
                    ""
                )
        })


        article[
            "ai_analysis_failed"
        ] = False


        analyzed.append(
            article
        )


        print(
            f"[{index}/{len(articles)}] "
            f"{article.get('title', '')}"
        )

        print(
            f"  金融市场相关："
            f"{article.get('market_relevant')}"
        )

        print(
            f"  分类："
            f"{article.get('category')}"
        )

        print(
            f"  事件："
            f"{article.get('event_type')}"
        )


    # ========================================================
    # 完成
    # ========================================================

    print(
        "\n============================================================"
    )

    print(
        f"Groq 批量新闻分析完成：{len(analyzed)} 条"
    )

    print(
        "AI调用方式：全量批量分析"
    )

    print(
        "============================================================"
    )


    return analyzed


# ============================================================
# 单条测试
# ============================================================

def analyze_news(
    article
):

    results = analyze_news_list(
        [article]
    )

    if results:

        return results[0]

    return {
        "market_relevant": False,
        "ai_analysis_failed": True
    }


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
