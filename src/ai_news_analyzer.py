import json
import os

from openai import OpenAI


# ============================================================
# 全球金融市场日报
# ai_news_analyzer.py
#
# 职责：
#
# 1. 使用 Groq AI 批量理解新闻
# 2. 判断是否具有金融市场影响
# 3. 判断事件本身是什么
# 4. 确定新闻分类
# 5. 判断同一事件关系
# 6. 提取核心事实
# 7. 判断影响范围等级
# 8. 判断影响程度等级
#
# 本文件不负责：
#
# ❌ 最终评分
# ❌ 来源可信度评分
# ❌ TOP10
# ❌ 新闻数量限制
# ❌ 最终排序
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
# 本地去重
# ↓
# 本地评分
# ↓
# 本地排序
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

你的任务是理解新闻事件本身，并判断它是否具有实际的金融市场影响。

你不是最终评分器。

最终评分由本地 Python 程序执行。

============================================================
一、金融市场相关性
============================================================

只有对金融市场具有实际影响，或者明确可能影响金融市场的信息，
才应该判定：

market_relevant = true

可能影响以下市场或领域：

- 全球股票市场
- 债券市场
- 外汇市场
- 能源市场
- 贵金属
- 大宗商品
- AI / 半导体产业链
- 重要上市公司
- 全球宏观经济
- 央行政策
- 国际贸易
- 制裁
- 地缘政治
- 金融机构
- 重要企业并购
- 重要财报
- 重大经营事件

以下信息如果没有明确金融市场影响，
必须判定：

market_relevant = false

例如：

- 普通社会新闻
- 娱乐新闻
- 体育新闻
- 明星新闻
- 生活方式新闻
- 与金融市场没有明显关系的普通科技新闻


============================================================
二、分类原则
============================================================

必须按照：

“事件本身是什么”

进行分类。

绝对不能因为文章中出现某个关键词，
就机械地按照关键词分类。

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
分类示例
============================================================

Fed决定维持或调整利率：

→ 宏观经济与央行政策


某公司公布季度财报：

→ 公司重大事件


公司宣布重大并购：

→ 公司重大事件


美国提高对某国商品关税：

→ 地缘政治与制裁


美国与伊朗发生军事冲突：

→ 地缘政治与制裁


军事冲突导致石油供应受到重大影响，
且新闻核心重点是能源供应和油价：

→ 能源与大宗商品


AI芯片公司发布重大产品或财报：

→ AI与半导体


美元汇率出现重大变化，
且新闻核心事件就是外汇市场变化：

→ 外汇与债券


股票市场整体发生重大变化：

→ 全球股市


============================================================
三、核心事实原则
============================================================

core_fact 必须严格来自输入新闻。

只能总结输入新闻中明确存在的信息。

禁止：

- 编造事实
- 推测新闻没有明确表达的事实
- 添加新闻之外的数据
- 添加新闻之外的市场行情
- 添加新闻之外的公司事件
- 添加新闻之外的政策
- 添加新闻之外的人物表态

如果输入信息不足：

必须保持谨慎。


============================================================
四、市场影响原因
============================================================

market_impact_reason：

说明为什么这个事件可能影响金融市场。

必须根据新闻内容判断。

不能凭空添加新闻没有提供的信息。

不要因为某个新闻来源权威，
就自动认为市场影响更大。


============================================================
五、影响范围
============================================================

判断事件可能影响的范围。

只能使用以下值：

global
multi_region
regional
country
industry
company
limited

定义：

global
→ 可能影响全球多个主要金融市场或全球经济

multi_region
→ 明确影响多个国家或多个地区

regional
→ 主要影响某一个地区

country
→ 主要影响单一国家整体金融市场或经济

industry
→ 主要影响某一个行业或产业链

company
→ 主要影响单一公司或少数特定公司

limited
→ 影响范围非常有限


============================================================
六、影响程度
============================================================

判断事件本身的影响程度。

只能使用：

very_high
high
medium
low

定义：

very_high
→ 极重大事件，可能造成重大金融市场冲击

high
→ 重大事件，对金融市场具有明显影响

medium
→ 有一定市场影响，但影响程度有限

low
→ 市场影响较小


============================================================
七、影响范围与影响程度必须独立判断
============================================================

影响范围和影响程度是两个不同维度。

例如：

一个重大上市公司事件：

impact_scope_level = company

但：

impact_degree_level = high

完全允许。

又例如：

一个影响多个国家的事件：

impact_scope_level = multi_region

但如果市场影响有限：

impact_degree_level = medium

也完全允许。

绝对不能因为影响范围大，
就自动判断影响程度高。

也不能因为来源权威，
就自动提高影响范围或影响程度。


============================================================
八、事件ID规则
============================================================

event_id 是非常重要的字段。

它用于识别：

“不同新闻是否实际上描述同一个具体事件”。

目标是：

同一具体事件的不同媒体报道，
尽可能使用完全一致的 event_id。

不同事件绝对不能使用相同 event_id。


------------------------------------------------------------
event_id 必须满足：
------------------------------------------------------------

1. 简短
2. 稳定
3. 描述核心事件
4. 不包含媒体名称
5. 不包含新闻标题原文
6. 不包含URL
7. 不包含随机数字
8. 不使用随机字符串
9. 不使用当前时间
10. 不使用新闻发布时间
11. 不因为媒体不同而改变
12. 不因为标题措辞不同而改变


------------------------------------------------------------
正确示例：
------------------------------------------------------------

美国宣布提高对中国商品关税

→ us_china_tariff_increase


美联储决定维持利率不变

→ fed_rate_decision


美国打击伊朗目标

→ us_iran_military_strike


英伟达发布季度财报

→ nvidia_quarterly_earnings


------------------------------------------------------------
错误示例：
------------------------------------------------------------

reuters_us_iran_20260831

因为包含媒体和日期，不稳定。

cnbc_fed_article_12345

因为包含媒体和随机编号，不稳定。

fed_keeps_rates_unchanged_reuters

因为包含媒体名称，不稳定。


------------------------------------------------------------
同一事件判断
------------------------------------------------------------

如果多条新闻明确描述的是同一个具体事件：

必须尽可能使用相同 event_id。

例如：

新闻A：
Reuters报道美国打击伊朗目标。

新闻B：
CNBC报道美国对伊朗发动军事行动。

如果两条新闻描述的是同一次具体军事行动：

两条新闻必须尽可能使用相同 event_id：

us_iran_military_strike


但是：

如果新闻A描述的是第一次军事行动，
新闻B描述的是数小时后发生的另一场独立军事行动：

必须使用不同 event_id。


------------------------------------------------------------
重要：
------------------------------------------------------------

不要因为两条新闻讨论的是同一个长期主题，
就认为它们属于同一事件。

例如：

“美联储降息”

和

“美联储官员讨论未来降息”

可能属于不同事件。

“伊朗局势紧张”

和

“美国当天发动具体军事打击”

也可能属于不同事件。

event_id 识别的是：

“具体事件”

而不是：

“相同主题”。


============================================================
九、事实真实性
============================================================

只能使用输入新闻提供的信息。

绝对禁止：

- 编造新闻
- 编造数据
- 编造来源
- 编造公司事件
- 编造政策
- 编造市场行情
- 编造人物观点
- 编造时间
- 编造新闻链接

如果无法确认：

保持谨慎。


============================================================
十、输出原则
============================================================

你将一次性分析多条新闻。

必须：

1. 每条输入新闻返回一个结果
2. id 必须完全对应输入新闻
3. 不允许遗漏id
4. 不允许增加不存在的id
5. 不允许改变id
6. 不允许输出Markdown
7. 不允许输出解释文字
8. 不允许输出代码块
9. 只返回合法JSON
10. 不进行最终评分
11. 不进行TOP10筛选
12. 不进行新闻排序

输出字段必须严格为：

id
market_relevant
event_type
category
core_fact
market_impact_reason
event_id
impact_scope_level
impact_degree_level
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
# JSON清理
# ============================================================

def clean_json_text(text):

    if not text:

        return ""

    text = text.strip()

    if text.startswith("```json"):

        text = text[
            len("```json"):
        ]

    elif text.startswith("```"):

        text = text[
            len("```"):
        ]

    if text.endswith("```"):

        text = text[
            :-len("```")
        ]

    return text.strip()


# ============================================================
# 验证AI结果
# ============================================================

def validate_ai_results(
    results,
    expected_count
):

    if not isinstance(
        results,
        list
    ):

        raise ValueError(
            "Groq返回结果不是JSON数组"
        )


    if len(results) != expected_count:

        raise ValueError(
            f"Groq返回数量错误："
            f"期望 {expected_count} 条，"
            f"实际 {len(results)} 条"
        )


    expected_ids = {

        str(i)

        for i in range(
            1,
            expected_count + 1
        )

    }


    actual_ids = set()


    for item in results:

        if not isinstance(
            item,
            dict
        ):

            raise ValueError(
                "Groq返回结果中存在非JSON对象"
            )


        if "id" not in item:

            raise ValueError(
                "Groq返回结果缺少id"
            )


        item_id = str(
            item["id"]
        )

        actual_ids.add(
            item_id
        )


    if actual_ids != expected_ids:

        raise ValueError(
            "Groq返回的新闻ID与输入不一致："
            f"期望={sorted(expected_ids)}, "
            f"实际={sorted(actual_ids)}"
        )


    return True


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
        "分析模式：全量批量分析"
    )

    print(
        f"模型：{GROQ_MODEL}"
    )

    print(
        "============================================================"
    )


    # ========================================================
    # 全量新闻一次性转换为JSON
    # ========================================================

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


必须为每一条新闻返回一个分析结果。

必须返回：

{len(prepared_articles)}

条结果。


每个结果必须严格包含以下字段：

{{
    "id": 1,
    "market_relevant": true,
    "event_type": "事件本身是什么",
    "category": "分类",
    "core_fact": "核心事实",
    "market_impact_reason": "金融市场影响原因",
    "event_id": "核心具体事件标识",
    "impact_scope_level": "global",
    "impact_degree_level": "high"
}}


============================================================
严格要求
============================================================

1. id必须与输入完全一致。

2. 每一个输入id都必须返回。

3. 不允许遗漏任何id。

4. 不允许增加不存在的id。

5. market_relevant只能是true或false。

6. 没有明确金融市场影响时：
   market_relevant=false。

7. category只能使用：

宏观经济与央行政策
全球股市
AI与半导体
能源与大宗商品
外汇与债券
地缘政治与制裁
公司重大事件
其他市场事件

8. category必须依据事件本身决定。

9. core_fact只能根据输入新闻。

10. 禁止编造输入新闻之外的信息。

11. market_impact_reason只能根据输入新闻判断。

12. event_id必须表示“具体事件”，
    不能只是表示一个长期主题。

13. 如果多条新闻明确描述同一个具体事件，
    必须尽可能使用完全一致的event_id。

14. 不同具体事件不能使用相同event_id。

15. event_id不能包含媒体名称。

16. event_id不能包含URL。

17. event_id不能包含随机数字。

18. event_id不能包含新闻发布时间。

19. event_id不能因为不同媒体报道而改变。

20. impact_scope_level只能使用：

global
multi_region
regional
country
industry
company
limited

21. impact_degree_level只能使用：

very_high
high
medium
low

22. impact_scope_level和impact_degree_level必须独立判断。

23. 不要因为新闻来源权威而提高影响范围。

24. 不要因为新闻来源权威而提高影响程度。

25. 不要计算最终分数。

26. 不要计算来源可信度。

27. 不要进行TOP10筛选。

28. 不要进行新闻排序。

29. 不要输出Markdown。

30. 不要输出```json。

31. 不要输出解释文字。

32. 只返回合法JSON。

33. 必须返回全部新闻的分析结果。
"""


    # ========================================================
    # 调用 Groq
    #
    # 关键修复：
    #
    # 1. include_reasoning=False
    # 2. max_completion_tokens=12000
    # 3. JSON Object Mode
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

            max_completion_tokens=12000,

            include_reasoning=False,

            response_format={
                "type": "json_object"
            }
        )


    except Exception as e:

        print(
            "\nGroq AI 批量分析失败："
            f"{e}"
        )

        return mark_analysis_failed(
            articles
        )


    # ========================================================
    # 获取AI返回
    # ========================================================

    try:

        text = response.choices[
            0
        ].message.content

    except Exception as e:

        print(
            "\n无法读取 Groq 返回结果："
            f"{e}"
        )

        return mark_analysis_failed(
            articles
        )


    text = clean_json_text(
        text
    )


    # ========================================================
    # JSON解析
    # ========================================================

    try:

        result = json.loads(
            text
        )

    except json.JSONDecodeError as e:

        print(
            "\nGroq 返回结果不是合法 JSON："
        )

        print(
            text
        )

        print(
            f"\nJSON解析错误：{e}"
        )

        return mark_analysis_failed(
            articles
        )


    # ========================================================
    # Groq response_format=json_object
    #
    # 因此允许：
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
                "\nGroq返回JSON对象，"
                "但没有找到results或articles数组。"
            )

            return mark_analysis_failed(
                articles
            )


    # ========================================================
    # 验证返回结果
    # ========================================================

    try:

        validate_ai_results(
            result,
            len(articles)
        )

    except ValueError as e:

        print(
            f"\nGroq返回结果验证失败：{e}"
        )

        return mark_analysis_failed(
            articles
        )


    # ========================================================
    # 建立AI结果索引
    # ========================================================

    result_map = {

        str(item["id"]): item

        for item in result

    }


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
                bool(
                    ai_result.get(
                        "market_relevant",
                        False
                    )
                ),

            "event_type":
                ai_result.get(
                    "event_type",
                    ""
                ),

            "category":
                ai_result.get(
                    "category",
                    "其他市场事件"
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

            "event_id":
                ai_result.get(
                    "event_id",
                    ""
                ),

            "impact_scope_level":
                ai_result.get(
                    "impact_scope_level",
                    "limited"
                ),

            "impact_degree_level":
                ai_result.get(
                    "impact_degree_level",
                    "low"
                ),

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

        print(
            f"  事件ID："
            f"{article.get('event_id')}"
        )

        print(
            f"  影响范围："
            f"{article.get('impact_scope_level')}"
        )

        print(
            f"  影响程度："
            f"{article.get('impact_degree_level')}"
        )


    # ========================================================
    # 完成
    # ========================================================

    print(
        "\n============================================================"
    )

    print(
        f"Groq 批量新闻分析完成："
        f"{len(analyzed)} 条"
    )

    print(
        "AI调用方式：全量批量分析"
    )

    print(
        "============================================================"
    )


    return analyzed


# ============================================================
# 单条新闻分析
#
# 主要用于调试。
#
# 正式日报仍然使用：
#
# analyze_news_list()
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
        "\n测试结果："
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=4
        )
    )
