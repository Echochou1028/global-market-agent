import json
import os
import time

from openai import OpenAI


# ============================================================
# 全球金融市场日报
# ai_news_analyzer.py
#
# 最终版
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
# ❌ 最终排序
#
# ============================================================
# 批量控制
#
# 最多50条/批
# Token安全阈值6000
#
# 注意：
#
# 6000不是简单的输入Token上限。
# 批次生成时同时考虑：
#
# 1. 输入Token估算
# 2. 输出Token预留
#
# 避免触碰Groq TPM限制。
#
# ============================================================


# ============================================================
# Groq模型
# ============================================================

GROQ_MODEL = "openai/gpt-oss-120b"


# ============================================================
# 批量控制
# ============================================================

MAX_ARTICLES_PER_BATCH = 50

TOKEN_SAFETY_LIMIT = 6000

# 每条新闻为模型输出预留的Token预算。
#
# 最终输出字段较多：
# market_relevant
# event_type
# category
# core_fact
# market_impact_reason
# event_id
# impact_scope_level
# impact_degree_level
#
# 因此不能只给一个极小的输出预算。
OUTPUT_TOKENS_PER_ARTICLE = 90

MIN_OUTPUT_TOKEN_RESERVE = 1000

MAX_RETRIES = 3

RETRY_DELAY_SECONDS = 2


# ============================================================
# 初始化Groq
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
# AI系统规则
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
- 重要企业并购、财报、经营事件

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
新闻核心重点是能源供应和油价：

→ 能源与大宗商品


AI芯片公司发布重大产品或财报：

→ AI与半导体


美元大幅波动，
核心事件是汇率市场：

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

如果输入信息不足，
必须保持谨慎。


============================================================
四、市场影响原因
============================================================

market_impact_reason：

说明为什么这个事件可能影响金融市场。

必须根据新闻内容判断。

不能凭空添加新闻没有提供的信息。


============================================================
五、影响范围
============================================================

只能使用：

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
七、重要原则
============================================================

影响范围和影响程度必须分别判断。

不能因为：

“来源很权威”

就提高影响范围。

不能因为：

“新闻来自CNBC、Reuters、Bloomberg等”

就提高影响程度。

来源可信度由本地Python程序单独计算。


============================================================
八、事件ID
============================================================

event_id用于识别：

“不同新闻是否实际上描述同一个事件”。

同一事件的不同媒体报道，
应该尽可能使用相同或高度一致的event_id。

event_id必须：

- 简短
- 稳定
- 描述核心事件
- 不包含媒体名称
- 不包含新闻标题原文
- 不使用随机字符串


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

你将一次性分析一批新闻。

必须：

1. 每条输入新闻返回一个结果
2. id必须完全对应输入新闻
3. 不允许遗漏id
4. 不允许增加不存在的id
5. 不允许改变id
6. 不允许输出Markdown
7. 不允许输出解释文字
8. 不允许输出代码块
9. 只返回合法JSON
10. 不进行最终评分

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
# Token估算
#
# 这里不追求精确Token计数。
#
# 目标是：
# “保守估算”，避免请求超过安全阈值。
#
# 中英文混合新闻使用字符长度进行近似。
# ============================================================

def estimate_tokens(text):

    if not text:

        return 0

    text = str(text)

    # 一个保守的简单估算：
    #
    # ASCII文本：
    # 大约4字符≈1 token
    #
    # 中文：
    # 大约1.5字符≈1 token
    #
    # 混合新闻采用偏保守计算。
    #
    # 同时考虑JSON、字段名、系统提示等开销。

    chinese_count = sum(
        1
        for char in text
        if "\u4e00" <= char <= "\u9fff"
    )

    other_count = len(text) - chinese_count

    estimated = (
        chinese_count / 1.5
        + other_count / 4
    )

    return int(
        estimated
    )


# ============================================================
# 单条新闻Token估算
# ============================================================

def estimate_article_tokens(article):

    article_text = json.dumps(
        article,
        ensure_ascii=False
    )

    return estimate_tokens(
        article_text
    )


# ============================================================
# 系统Prompt + 用户Prompt固定开销估算
# ============================================================

def estimate_prompt_overhead():

    return (
        estimate_tokens(
            SYSTEM_PROMPT
        )
        + 500
    )


# ============================================================
# 输出Token预留
# ============================================================

def estimate_output_reserve(
    article_count
):

    return max(

        MIN_OUTPUT_TOKEN_RESERVE,

        article_count
        * OUTPUT_TOKENS_PER_ARTICLE

    )


# ============================================================
# 单批Token估算
# ============================================================

def estimate_batch_tokens(
    articles
):

    input_tokens = estimate_prompt_overhead()

    for article in articles:

        input_tokens += (
            estimate_article_tokens(
                article
            )
        )

    output_reserve = (
        estimate_output_reserve(
            len(articles)
        )
    )

    total_estimated = (
        input_tokens
        + output_reserve
    )

    return (
        input_tokens,
        output_reserve,
        total_estimated
    )


# ============================================================
# 自动生成批次
#
# 规则：
#
# 1. 单批最多50条
# 2. 预计总Token不得超过6000
# 3. Token达到安全阈值时提前切批
#
# 注意：
# 50条只是数量上限。
# Token条件优先级更高。
# ============================================================

def build_batches(
    articles
):

    batches = []

    current_batch = []

    prepared_count = len(
        articles
    )

    for article in articles:

        candidate = (
            current_batch
            + [article]
        )

        (
            input_tokens,
            output_reserve,
            total_tokens
        ) = estimate_batch_tokens(
            candidate
        )

        # ----------------------------------------------------
        # 第一优先级：50条硬上限
        # ----------------------------------------------------

        too_many_articles = (
            len(candidate)
            > MAX_ARTICLES_PER_BATCH
        )

        # ----------------------------------------------------
        # 第二优先级：Token安全阈值
        # ----------------------------------------------------

        too_many_tokens = (
            total_tokens
            > TOKEN_SAFETY_LIMIT
        )

        # ----------------------------------------------------
        # 需要切批
        # ----------------------------------------------------

        if (
            current_batch
            and (
                too_many_articles
                or too_many_tokens
            )
        ):

            batches.append(
                current_batch
            )

            current_batch = [
                article
            ]

        else:

            current_batch = candidate


    if current_batch:

        batches.append(
            current_batch
        )


    return batches


# ============================================================
# AI失败处理
# ============================================================

def mark_analysis_failed(
    articles
):

    failed = []

    for article in articles:

        item = dict(
            article
        )

        item["market_relevant"] = False

        item["ai_analysis_failed"] = True

        failed.append(
            item
        )

    return failed


# ============================================================
# JSON清理
# ============================================================

def clean_json_text(text):

    if not text:

        return ""

    text = text.strip()

    if text.startswith(
        "```json"
    ):

        text = text[
            len("```json"):
        ]

    elif text.startswith(
        "```"
    ):

        text = text[
            len("```"):
        ]


    if text.endswith(
        "```"
    ):

        text = text[
            :-len("```")
        ]


    return text.strip()


# ============================================================
# 提取JSON数组
#
# 兼容：
#
# 1. [...]
# 2. {"results":[...]}
# 3. {"articles":[...]}
# 4. {"data":[...]}
# ============================================================

def extract_results(
    result
):

    if isinstance(
        result,
        list
    ):

        return result


    if not isinstance(
        result,
        dict
    ):

        return None


    for key in (
        "results",
        "articles",
        "data"
    ):

        value = result.get(
            key
        )

        if isinstance(
            value,
            list
        ):

            return value


    return None


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
            "Groq返回数量错误："
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

        if item_id in actual_ids:

            raise ValueError(
                f"Groq返回重复id：{item_id}"
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
# 构造批次Prompt
# ============================================================

def build_batch_prompt(
    prepared_articles
):

    articles_json = json.dumps(
        prepared_articles,
        ensure_ascii=False
    )


    count = len(
        prepared_articles
    )


    return f"""
请一次性分析下面全部新闻。

输入新闻数量：

{count}

新闻数据：

{articles_json}


必须为每一条新闻返回一个分析结果。

必须返回：

{count}

条结果。


JSON顶层必须是一个对象。

推荐格式：

{{
    "results": [
        {{
            "id": 1,
            "market_relevant": true,
            "event_type": "事件本身是什么",
            "category": "分类",
            "core_fact": "核心事实",
            "market_impact_reason": "金融市场影响原因",
            "event_id": "核心事件标识",
            "impact_scope_level": "global",
            "impact_degree_level": "high"
        }}
    ]
}}


============================================================
严格要求
============================================================

1. id必须与输入完全一致。

2. 每一个输入id都必须返回。

3. 不允许遗漏任何id。

4. 不允许增加不存在的id。

5. 不允许重复id。

6. market_relevant只能是true或false。

7. 没有明确金融市场影响时：
   market_relevant=false。

8. category只能使用：

宏观经济与央行政策
全球股市
AI与半导体
能源与大宗商品
外汇与债券
地缘政治与制裁
公司重大事件
其他市场事件

9. category必须依据事件本身决定。

10. core_fact只能根据输入新闻。

11. 禁止编造输入新闻之外的信息。

12. market_impact_reason只能根据输入新闻判断。

13. event_id用于识别同一事件。

14. impact_scope_level只能使用：

global
multi_region
regional
country
industry
company
limited

15. impact_degree_level只能使用：

very_high
high
medium
low

16. 不要计算分数。

17. 不要计算来源可信度。

18. 不要进行TOP10筛选。

19. 不要进行新闻排序。

20. 不要输出Markdown。

21. 不要输出代码块。

22. 不要输出解释文字。

23. 只返回合法JSON。

24. JSON顶层必须是对象。

25. JSON对象必须包含results数组。

26. results数组必须包含全部{count}条新闻。

27. 不要输出reasoning。

28. 不要输出任何额外字段。

"""


# ============================================================
# 请求Groq
# ============================================================

def request_groq_batch(
    client,
    prompt,
    batch_number
):

    last_error = None


    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"Groq第{batch_number}批："
            f"第{attempt}次请求"
        )


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
                
                reasoning_effort="low",
                
                # ------------------------------------------------
                # JSON Object Mode
                # ------------------------------------------------
                #
                # 强制模型返回合法 JSON 对象。
                # 不要求返回 reasoning。
                # ------------------------------------------------

                response_format={
                    "type": "json_object"
                },

                # ------------------------------------------------
                # GPT-OSS
                #
                # 不返回reasoning字段，
                # 避免reasoning干扰结构化结果。
                # ------------------------------------------------

                # ------------------------------------------------
                # 输出上限
                # ------------------------------------------------

                max_completion_tokens=6000

            )


            text = response.choices[
                0
            ].message.content


            if not text:

                raise ValueError(
                    "Groq返回内容为空"
                )


            text = clean_json_text(
                text
            )


            result = json.loads(
                text
            )


            results = extract_results(
                result
            )


            if results is None:

                raise ValueError(
                    "Groq返回JSON对象，"
                    "但没有找到results、articles或data数组"
                )


            return results


        except Exception as e:

            last_error = e

            print(
                f"Groq第{batch_number}批失败："
                f"{e}"
            )


            if attempt < MAX_RETRIES:

                print(
                    f"将在"
                    f"{RETRY_DELAY_SECONDS}"
                    f"秒后重试..."
                )

                time.sleep(
                    RETRY_DELAY_SECONDS
                )


    raise RuntimeError(
        f"Groq第{batch_number}批达到最大重试次数："
        f"{last_error}"
    )


# ============================================================
# 合并多批AI结果
# ============================================================

def merge_batch_results(
    all_results
):

    merged = []

    for result in all_results:

        if not isinstance(
            result,
            list
        ):

            raise ValueError(
                "存在无效批次结果"
            )

        merged.extend(
            result
        )


    return merged


# ============================================================
# 批量分析新闻
# ============================================================

def analyze_news_list(
    articles
):

    if not articles:

        return []


    client = get_client()


    # ========================================================
    # 原始新闻ID
    #
    # 每个批次内部重新从1开始编号。
    # ========================================================

    batches = []


    # --------------------------------------------------------
    # 先建立全局带索引新闻
    # --------------------------------------------------------

    indexed_articles = []

    for global_index, article in enumerate(
        articles,
        1
    ):

        item = dict(
            article
        )

        item["_global_id"] = (
            global_index
        )

        indexed_articles.append(
            item
        )


    # --------------------------------------------------------
    # 按Token和数量生成批次
    # --------------------------------------------------------

    prepared_all = []

    for item in indexed_articles:

        prepared_all.append({

            "id":
                item["_global_id"],

            "title":
                item.get(
                    "title",
                    ""
                ),

            "summary":
                item.get(
                    "summary",
                    ""
                ),

            "source":
                item.get(
                    "source",
                    ""
                ),

            "url":
                item.get(
                    "url",
                    ""
                )

        })


    batches = build_batches(
        prepared_all
    )


    print(
        "\n============================================================"
    )

    print(
        "开始使用 Groq AI 批量分析新闻事件"
    )

    print(
        f"待分析新闻："
        f"{len(articles)} 条"
    )

    print(
        "分析模式：自动分批分析"
    )

    print(
        f"单批最大新闻数："
        f"{MAX_ARTICLES_PER_BATCH}"
    )

    print(
        f"Token安全阈值："
        f"{TOKEN_SAFETY_LIMIT}"
    )

    print(
        f"模型："
        f"{GROQ_MODEL}"
    )

    print(
        "============================================================"
    )


    print(
        f"自动生成分析批次："
        f"{len(batches)} 批"
    )


    for batch_index, batch in enumerate(
        batches,
        1
    ):

        (
            input_tokens,
            output_reserve,
            total_tokens
        ) = estimate_batch_tokens(
            batch
        )


        print(
            f"  第{batch_index}批："
            f"{len(batch)}条，"
            f"预计输入Token："
            f"{input_tokens}，"
            f"输出预留："
            f"{output_reserve}，"
            f"预计总Token："
            f"{total_tokens}"
        )


    # ========================================================
    # 所有批次逐批分析
    # ========================================================

    all_results = []


    for batch_index, batch in enumerate(
        batches,
        1
    ):

        print(
            "\n------------------------------------------------------------"
        )

        print(
            f"正在分析第 "
            f"{batch_index}/{len(batches)} 批"
        )

        print(
            f"本批新闻数量："
            f"{len(batch)}"
        )


        (
            input_tokens,
            output_reserve,
            total_tokens
        ) = estimate_batch_tokens(
            batch
        )


        print(
            f"预计输入Token："
            f"{input_tokens}"
        )

        print(
            f"预计总Token："
            f"{total_tokens}"
        )

        print(
            "------------------------------------------------------------"
        )


        # ----------------------------------------------------
        # 构造本批Prompt
        # ----------------------------------------------------

        prompt = build_batch_prompt(
            batch
        )


        # ----------------------------------------------------
        # 请求Groq
        # ----------------------------------------------------

        try:

            batch_results = request_groq_batch(

                client,

                prompt,

                batch_index

            )


        except Exception as e:

            print(
                "\n============================================================"
            )

            print(
                "Groq批量新闻分析整体失败"
            )

            print(
                f"失败批次："
                f"{batch_index}/{len(batches)}"
            )

            print(
                f"失败原因："
                f"{e}"
            )

            print(
                "不会使用不完整分析结果。"
            )

            print(
                "============================================================"
            )

            return mark_analysis_failed(
                articles
            )


        # ----------------------------------------------------
        # 验证本批ID
        # ----------------------------------------------------

        try:

            validate_ai_results(

                batch_results,

                len(batch)

            )


        except ValueError as e:

            print(
                "\n============================================================"
            )

            print(
                f"Groq第{batch_index}批结果验证失败："
                f"{e}"
            )

            print(
                "不会使用不完整分析结果。"
            )

            print(
                "============================================================"
            )

            return mark_analysis_failed(
                articles
            )


        # ----------------------------------------------------
        # 保存本批结果
        # ----------------------------------------------------

        all_results.extend(
            batch_results
        )


        print(
            f"第{batch_index}批分析成功："
            f"{len(batch_results)}条"
        )


    # ========================================================
    # 合并全部批次
    # ========================================================

    merged_results = merge_batch_results(
        all_results
    )


    # ========================================================
    # 验证最终总数量
    # ========================================================

    if len(
        merged_results
    ) != len(articles):

        print(
            "\n============================================================"
        )

        print(
            "Groq全部批次合并后数量错误"
        )

        print(
            f"期望：{len(articles)}"
        )

        print(
            f"实际：{len(merged_results)}"
        )

        print(
            "不会使用不完整分析结果。"
        )

        print(
            "============================================================"
        )

        return mark_analysis_failed(
            articles
        )


    # ========================================================
    # 建立全局ID索引
    # ========================================================

    result_map = {}

    try:

        for item in merged_results:

            item_id = str(
                item["id"]
            )

            if item_id in result_map:

                raise ValueError(
                    f"发现重复全局ID：{item_id}"
                )

            result_map[
                item_id
            ] = item


    except Exception as e:

        print(
            "\n============================================================"
        )

        print(
            f"Groq最终结果ID验证失败：{e}"
        )

        print(
            "不会使用不完整分析结果。"
        )

        print(
            "============================================================"
        )

        return mark_analysis_failed(
            articles
        )


    # ========================================================
    # 验证全部原始新闻ID
    # ========================================================

    expected_global_ids = {
        str(i)
        for i in range(
            1,
            len(articles) + 1
        )
    }


    actual_global_ids = set(
        result_map.keys()
    )


    if (
        actual_global_ids
        != expected_global_ids
    ):

        print(
            "\n============================================================"
        )

        print(
            "Groq最终结果存在ID遗漏或增加"
        )

        print(
            f"期望ID："
            f"{sorted(expected_global_ids)}"
        )

        print(
            f"实际ID："
            f"{sorted(actual_global_ids)}"
        )

        print(
            "不会使用不完整分析结果。"
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


        article = dict(
            article
        )


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
        f"Groq批量新闻分析完成："
        f"{len(analyzed)} 条"
    )

    print(
        f"实际分析批次："
        f"{len(batches)} 批"
    )

    print(
        "AI调用方式：自动Token安全分批"
    )

    print(
        "============================================================"
    )


    return analyzed


# ============================================================
# 单条新闻分析
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

        "market_relevant":
            False,

        "ai_analysis_failed":
            True

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
