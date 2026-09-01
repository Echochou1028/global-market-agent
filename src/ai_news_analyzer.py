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
# 最终评分、去重、排序等硬规则由本地 Python 执行。
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
# 本地严格校验
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

============================================================
一、金融市场相关性
============================================================

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
如果没有明确金融市场影响，
必须判定为 false。

============================================================
二、分类原则
============================================================

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

伊朗冲突导致霍尔木兹海峡运输风险：

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

============================================================
三、事实原则
============================================================

只能根据输入新闻提供的信息进行判断。

绝对禁止：

- 编造新闻
- 编造数据
- 编造公司事件
- 编造政策
- 编造市场行情
- 编造来源
- 编造引用
- 使用输入新闻之外的知识补充事实

如果新闻内容不足以确认某个事实，
不得自行推测。

============================================================
四、来源原则
============================================================

新闻来源可能包括：

- 官方机构
- 央行
- 政府部门
- 国际金融机构
- 权威金融媒体
- 主流国际媒体

来源本身不能决定新闻是否重要。

来源只作为后续“来源可信度”评分的依据。

============================================================
五、分析目标
============================================================

对于每条新闻：

1. 判断是否真正具有金融市场影响
2. 判断事件本身是什么
3. 确定分类
4. 提取核心事实
5. 说明为什么可能影响金融市场
6. 生成用于本地去重的 event_key

不要进行任何最终分数计算。

============================================================
六、输出规则
============================================================

你将一次性分析多条新闻。

必须按照输入新闻的 id 返回对应分析结果。

必须：

- 返回所有输入 id
- 不遗漏任何 id
- 不增加不存在的 id
- 每个 id 只能出现一次
- id 必须保持与输入完全一致
- 不输出 Markdown
- 不输出解释文字
- 不输出 ```json
- 只返回合法 JSON object

JSON object 必须使用：

{
    "results": [...]
}

results 必须是数组。

============================================================
七、重要约束
============================================================

不要因为新闻数量较多而省略新闻。

不要合并不同新闻。

即使多条新闻可能属于同一事件，
也必须分别返回对应 id 的分析结果。

event_key 用于后续本地程序判断是否属于同一事件。

不要进行评分。

不要决定 TOP10。

不要删除新闻。

最终新闻筛选、去重、评分、排序由本地程序完成。
"""


# ============================================================
# 允许的新闻分类
# ============================================================

VALID_CATEGORIES = {
    "宏观经济与央行政策",
    "全球股市",
    "AI与半导体",
    "能源与大宗商品",
    "外汇与债券",
    "地缘政治与制裁",
    "公司重大事件",
    "其他市场事件"
}


# ============================================================
# 新闻预处理
# ============================================================

def prepare_articles(articles):

    prepared = []

    for index, article in enumerate(articles, 1):

        prepared.append({

            "id": index,

            "title": article.get(
                "title",
                ""
            ),

            "summary": article.get(
                "summary",
                ""
            ),

            "source": article.get(
                "source",
                ""
            ),

            "url": article.get(
                "url",
                ""
            )
        })

    return prepared


# ============================================================
# AI失败处理
# ============================================================

def mark_analysis_failed(articles):

    for article in articles:

        article["market_relevant"] = False

        article["ai_analysis_failed"] = True

    return articles


# ============================================================
# 校验 AI 返回结果
# ============================================================

def validate_results(
    result,
    expected_ids
):

    # --------------------------------------------------------
    # 必须是 object
    # --------------------------------------------------------

    if not isinstance(
        result,
        dict
    ):

        raise ValueError(
            "Groq 返回结果不是 JSON object"
        )


    # --------------------------------------------------------
    # 必须存在 results
    # --------------------------------------------------------

    results = result.get(
        "results"
    )

    if not isinstance(
        results,
        list
    ):

        raise ValueError(
            "Groq 返回 JSON object，但缺少 results 数组"
        )


    # --------------------------------------------------------
    # 建立 ID 映射
    # --------------------------------------------------------

    result_map = {}

    for item in results:

        if not isinstance(
            item,
            dict
        ):

            raise ValueError(
                "Groq results 中存在非 JSON object 元素"
            )

        item_id = item.get(
            "id"
        )

        if item_id is None:

            raise ValueError(
                "Groq 返回结果存在缺失 id 的项目"
            )

        item_id = str(
            item_id
        )

        if item_id in result_map:

            raise ValueError(
                f"Groq 返回重复 id：{item_id}"
            )

        result_map[item_id] = item


    # --------------------------------------------------------
    # 检查是否存在不存在的 ID
    # --------------------------------------------------------

    expected_id_set = {
        str(item)
        for item in expected_ids
    }

    returned_id_set = set(
        result_map.keys()
    )


    unexpected_ids = (
        returned_id_set
        - expected_id_set
    )

    if unexpected_ids:

        raise ValueError(
            f"Groq 返回了输入中不存在的 id："
            f"{sorted(unexpected_ids)}"
        )


    # --------------------------------------------------------
    # 检查是否遗漏 ID
    # --------------------------------------------------------

    missing_ids = (
        expected_id_set
        - returned_id_set
    )

    if missing_ids:

        raise ValueError(
            f"Groq 返回结果缺失 id："
            f"{sorted(missing_ids)}"
        )


    # --------------------------------------------------------
    # 检查数量
    # --------------------------------------------------------

    if len(result_map) != len(
        expected_ids
    ):

        raise ValueError(
            "Groq 返回结果数量与输入新闻数量不一致"
        )


    return result_map


# ============================================================
# 校验单条 AI 分析结果
# ============================================================

def validate_item(item):

    # --------------------------------------------------------
    # market_relevant
    # --------------------------------------------------------

    market_relevant = item.get(
        "market_relevant"
    )

    if not isinstance(
        market_relevant,
        bool
    ):

        raise ValueError(
            "market_relevant 必须是 true 或 false"
        )


    # --------------------------------------------------------
    # category
    # --------------------------------------------------------

    category = item.get(
        "category",
        ""
    )

    if category not in VALID_CATEGORIES:

        raise ValueError(
            f"非法新闻分类：{category}"
        )


    # --------------------------------------------------------
    # 文本字段
    # --------------------------------------------------------

    required_text_fields = [
        "event_type",
        "core_fact",
        "market_impact_reason",
        "event_key"
    ]

    for field in required_text_fields:

        value = item.get(
            field
        )

        if not isinstance(
            value,
            str
        ):

            raise ValueError(
                f"{field} 必须是字符串"
            )

        if not value.strip():

            raise ValueError(
                f"{field} 不能为空"
            )


# ============================================================
# 批量分析新闻
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
        "分析模式：一次全量批量分析"
    )

    print(
        "============================================================"
    )


    # ========================================================
    # 新闻 JSON
    # ========================================================

    articles_json = json.dumps(
        prepared_articles,
        ensure_ascii=False,
        separators=(
            ",",
            ":"
        )
    )


    # ========================================================
    # 用户 Prompt
    # ========================================================

    prompt = f"""
请一次性分析下面全部新闻。

输入新闻数量：

{len(prepared_articles)}

新闻数据：

{articles_json}


============================================================
返回要求
============================================================

必须返回：

{{
    "results": [
        {{
            "id": 1,
            "market_relevant": true,
            "event_type": "事件本身是什么",
            "category": "分类",
            "core_fact": "只根据输入新闻提取核心事实",
            "market_impact_reason": "为什么该事件可能影响金融市场",
            "event_key": "用于本地识别同一事件的简短事件标识"
        }}
    ]
}}


============================================================
严格要求
============================================================

1. 每一个输入 id 都必须返回。

2. id 必须与输入完全一致。

3. 不允许遗漏任何 id。

4. 不允许增加不存在的 id。

5. 每个 id 只能出现一次。

6. market_relevant 必须是 true 或 false。

7. 如果没有明确金融市场影响，
   market_relevant 必须为 false。

8. category 必须从以下分类中选择：

宏观经济与央行政策
全球股市
AI与半导体
能源与大宗商品
外汇与债券
地缘政治与制裁
公司重大事件
其他市场事件

9. category 必须根据“事件本身”决定。

10. 不得因为关键词出现就机械分类。

11. core_fact 只能使用输入新闻中的事实。

12. 不得补充输入新闻没有出现的信息。

13. market_impact_reason 只能基于输入新闻判断。

14. event_key 用于本地去重。

15. 不要进行任何评分。

16. 不要决定 TOP10。

17. 不要删除任何输入新闻。

18. 不要合并不同新闻。

19. 不要输出 Markdown。

20. 不要输出解释文字。

21. 不要输出 ```json。

22. 只返回合法 JSON object。

23. JSON object 顶层必须包含 results 数组。
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
            "\n============================================================"
        )

        print(
            "Groq AI 批量分析失败"
        )

        print(
            str(e)
        )

        print(
            "============================================================"
        )

        return mark_analysis_failed(
            articles
        )


    # ========================================================
    # 获取返回内容
    # ========================================================

    try:

        text = response.choices[
            0
        ].message.content

    except Exception as e:

        print(
            f"\nGroq 返回内容读取失败：{e}"
        )

        return mark_analysis_failed(
            articles
        )


    if not text:

        print(
            "\nGroq 返回内容为空"
        )

        return mark_analysis_failed(
            articles
        )


    text = text.strip()


    # ========================================================
    # 兼容极少数 Markdown 包裹
    #
    # 正常情况下系统已经明确禁止 Markdown。
    # 这里仅作为安全兜底。
    # ========================================================

    if text.startswith(
        "```"
    ):

        if text.startswith(
            "```json"
        ):

            text = text[
                len("```json"):
            ]

        else:

            text = text[
                len("```"):
            ]

        if text.endswith(
            "```"
        ):

            text = text[
                :-3
            ]

        text = text.strip()


    # ========================================================
    # JSON 解析
    # ========================================================

    try:

        result = json.loads(
            text
        )

    except json.JSONDecodeError as e:

        print(
            "\n============================================================"
        )

        print(
            "Groq 返回结果不是合法 JSON"
        )

        print(
            f"JSON解析错误：{e}"
        )

        print(
            "============================================================"
        )

        return mark_analysis_failed(
            articles
        )


    # ========================================================
    # 严格校验
    # ========================================================

    expected_ids = range(
        1,
        len(articles) + 1
    )


    try:

        result_map = validate_results(
            result,
            expected_ids
        )

    except Exception as e:

        print(
            "\n============================================================"
        )

        print(
            "Groq 返回结果校验失败"
        )

        print(
            str(e)
        )

        print(
            "============================================================"
        )

        return mark_analysis_failed(
            articles
        )


    # ========================================================
    # 校验每一条结果字段
    # ========================================================

    try:

        for item in result_map.values():

            validate_item(
                item
            )

    except Exception as e:

        print(
            "\n============================================================"
        )

        print(
            "Groq AI 分析字段校验失败"
        )

        print(
            str(e)
        )

        print(
            "============================================================"
        )

        return mark_analysis_failed(
            articles
        )


    # ========================================================
    # 写回原始新闻
    # ========================================================

    analyzed = []


    for index, article in enumerate(
        articles,
        1
    ):

        ai_result = result_map[
            str(index)
        ]


        article.update({

            "market_relevant":
                ai_result[
                    "market_relevant"
                ],

            "event_type":
                ai_result[
                    "event_type"
                ].strip(),

            "category":
                ai_result[
                    "category"
                ].strip(),

            "core_fact":
                ai_result[
                    "core_fact"
                ].strip(),

            "market_impact_reason":
                ai_result[
                    "market_impact_reason"
                ].strip(),

            "event_key":
                ai_result[
                    "event_key"
                ].strip(),

            "ai_analysis_failed":
                False
        })


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
        "AI调用方式：一次全量批量分析"
    )

    print(
        "AI不负责评分"
    )

    print(
        "AI不负责TOP10"
    )

    print(
        "============================================================"
    )


    return analyzed


# ============================================================
# 单条新闻分析
#
# 保留这个函数，兼容项目其他模块调用。
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

        "market_relevant":
            False,

        "ai_analysis_failed":
            True
    }


# ============================================================
# 本地测试
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
        "\nAI分析结果："
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=4
        )
    )
