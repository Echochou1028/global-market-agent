import json
import os
import time
from openai import OpenAI


# ============================================================
# 全球金融市场日报
# ai_news_analyzer.py
#
# 最终稳定版
#
# 核心目标：
#
# 1. Groq GPT-OSS 120B
# 2. 自动Token控制
# 3. 小批量优先，避免长输出被截断
# 4. JSON Object Mode
# 5. JSON results/articles/data兼容
# 6. 批次失败自动重试
# 7. 返回数量不足自动拆批
# 8. ID完整性验证
# 9. 所有批次成功后才合并
# 10. 任意最终批次失败 -> 整体失败
# 11. 不使用任何不完整结果
#
# 注意：
#
# 不使用：
#   reasoning_format
#   include_reasoning
#
# 仅使用：
#   reasoning_effort="low"
#
# 原因：
# 当前项目实际运行环境中的OpenAI SDK
# 已经证明上述两个参数可能导致：
#
# Completions.create() got an unexpected keyword argument
#
# ============================================================


# ============================================================
# Groq模型
# ============================================================

GROQ_MODEL = "openai/gpt-oss-120b"


# ============================================================
# 批量控制
# ============================================================

# 业务层硬上限
MAX_ARTICLES_PER_BATCH = 50

# 实际推荐目标
#
# 不再追求把50条全部塞进一次请求。
#
# GPT-OSS需要输出大量结构化字段，
# 小批量更加稳定。
PREFERRED_ARTICLES_PER_BATCH = 8


# ============================================================
# Token安全控制
# ============================================================

# Groq当前你这个组织此前实际返回：
#
# TPM Limit = 8000
#
# 因此这里不再使用7600这种过于激进的值。
TOKEN_SAFETY_LIMIT = 6500


# 每条新闻输出预算
#
# 每条需要输出：
#
# id
# market_relevant
# event_type
# category
# core_fact
# market_impact_reason
# event_id
# impact_scope_level
# impact_degree_level
#
# 不能设置得过低。
OUTPUT_TOKENS_PER_ARTICLE = 110


# 最小输出预算
MIN_OUTPUT_TOKEN_RESERVE = 700


# 最大输出预算
MAX_OUTPUT_TOKEN_RESERVE = 1800


# ============================================================
# API重试
# ============================================================

MAX_RETRIES = 3

RETRY_DELAY_SECONDS = 2


# ============================================================
# 自动拆分
# ============================================================

AUTO_SPLIT_ON_FAILURE = True

MIN_SPLIT_SIZE = 1


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

最终评分由本地Python程序执行。

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
- 财报
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
三、核心事实原则
============================================================

core_fact必须严格来自输入新闻。

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

一次性分析当前批次的全部新闻。

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
11. 不计算来源可信度
12. 不进行TOP10
13. 不进行新闻排序

输出字段：

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

    for article in articles:

        prepared.append({

            "id": article["id"],

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
# ============================================================

def estimate_tokens(text):

    if not text:

        return 0

    text = str(text)

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

    return max(
        1,
        int(estimated)
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
# Prompt固定开销
# ============================================================

def estimate_prompt_overhead():

    return (
        estimate_tokens(
            SYSTEM_PROMPT
        )
        + 500
    )


# ============================================================
# 动态输出Token
# ============================================================

def calculate_output_tokens(
    article_count
):

    calculated = (
        article_count
        * OUTPUT_TOKENS_PER_ARTICLE
    )

    calculated = max(
        MIN_OUTPUT_TOKEN_RESERVE,
        calculated
    )

    calculated = min(
        MAX_OUTPUT_TOKEN_RESERVE,
        calculated
    )

    return calculated


# ============================================================
# 单批输入Token估算
# ============================================================

def estimate_input_tokens(
    articles
):

    total = estimate_prompt_overhead()

    for article in articles:

        total += estimate_article_tokens(
            article
        )

    return total


# ============================================================
# 请求Token预算
# ============================================================

def estimate_request_tokens(
    articles
):

    input_tokens = estimate_input_tokens(
        articles
    )

    output_tokens = calculate_output_tokens(
        len(articles)
    )

    total = (
        input_tokens
        + output_tokens
    )

    return (
        input_tokens,
        output_tokens,
        total
    )


# ============================================================
# 构建初始批次
#
# 重要：
#
# 不再简单按照50条切。
#
# 优先采用：
#
# 1. 8条左右
# 2. Token不超过6500
# 3. 最多50条
#
# 如果单条新闻本身很长，
# Token规则优先。
# ============================================================

def build_initial_batches(
    articles
):

    batches = []

    current = []

    for article in articles:

        candidate = (
            current
            + [article]
        )

        (
            input_tokens,
            output_tokens,
            total_tokens
        ) = estimate_request_tokens(
            candidate
        )

        exceeds_token = (
            total_tokens
            > TOKEN_SAFETY_LIMIT
        )

        exceeds_preferred = (
            len(candidate)
            > PREFERRED_ARTICLES_PER_BATCH
        )

        exceeds_max = (
            len(candidate)
            > MAX_ARTICLES_PER_BATCH
        )

        if (
            current
            and (
                exceeds_token
                or exceeds_preferred
                or exceeds_max
            )
        ):

            batches.append(
                current
            )

            current = [
                article
            ]

        else:

            current = candidate


    if current:

        batches.append(
            current
        )


    return batches


# ============================================================
# 构建Prompt
# ============================================================

def build_batch_prompt(
    articles
):

    count = len(
        articles
    )

    articles_json = json.dumps(
        articles,
        ensure_ascii=False
    )

    return f"""
请一次性分析下面全部 {count} 条新闻。

新闻数据：

{articles_json}


============================================================
输出要求
============================================================

必须返回一个JSON对象。

JSON顶层格式必须为：

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


必须：

1. 返回全部 {count} 条结果。

2. 每一个输入id必须返回。

3. id必须完全保持不变。

4. 不允许遗漏id。

5. 不允许增加不存在的id。

6. 不允许重复id。

7. market_relevant只能是true或false。

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

10. core_fact只能来自输入新闻。

11. market_impact_reason只能来自输入新闻。

12. event_id用于识别同一事件。

13. impact_scope_level只能使用：

global
multi_region
regional
country
industry
company
limited

14. impact_degree_level只能使用：

very_high
high
medium
low

15. 不计算最终评分。

16. 不计算来源可信度。

17. 不进行TOP10筛选。

18. 不进行排序。

19. 不输出Markdown。

20. 不输出代码块。

21. 不输出解释文字。

22. 不输出reasoning。

23. 不输出额外字段。

24. 只返回合法JSON。

25. JSON顶层必须是对象。

26. 顶层对象必须包含results数组。

27. results必须包含全部 {count} 条结果。

"""


# ============================================================
# 清理JSON
# ============================================================

def clean_json_text(
    text
):

    if not text:

        return ""

    text = text.strip()

    if text.startswith(
        "```json"
    ):

        text = text[
            7:
        ]

    elif text.startswith(
        "```"
    ):

        text = text[
            3:
        ]


    if text.endswith(
        "```"
    ):

        text = text[
            :-3
        ]


    return text.strip()


# ============================================================
# 提取结果
#
# 兼容：
#
# []
# {"results":[]}
# {"articles":[]}
# {"data":[]}
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
# 验证批次ID
# ============================================================

def validate_batch_results(
    results,
    expected_articles
):

    if not isinstance(
        results,
        list
    ):

        raise ValueError(
            "AI返回结果不是数组"
        )


    expected_ids = {
        str(
            article["id"]
        )
        for article
        in expected_articles
    }


    actual_ids = set()


    for item in results:

        if not isinstance(
            item,
            dict
        ):

            raise ValueError(
                "结果中存在非JSON对象"
            )


        if "id" not in item:

            raise ValueError(
                "结果缺少id"
            )


        item_id = str(
            item["id"]
        )


        if item_id in actual_ids:

            raise ValueError(
                f"发现重复id：{item_id}"
            )


        actual_ids.add(
            item_id
        )


    if actual_ids != expected_ids:

        raise ValueError(
            "ID不完整或不匹配："
            f"期望={sorted(expected_ids)}, "
            f"实际={sorted(actual_ids)}"
        )


    if len(results) != len(
        expected_articles
    ):

        raise ValueError(
            "AI返回数量错误："
            f"期望={len(expected_articles)}, "
            f"实际={len(results)}"
        )


    return True


# ============================================================
# 请求Groq
#
# 注意：
#
# 不使用：
#
# reasoning_format
# include_reasoning
#
# 仅使用：
#
# reasoning_effort="low"
#
# response_format=json_object
# ============================================================

def request_groq_batch(
    client,
    articles,
    batch_label
):

    prompt = build_batch_prompt(
        articles
    )


    (
        input_tokens,
        output_tokens,
        total_tokens
    ) = estimate_request_tokens(
        articles
    )


    print(
        f"Groq第{batch_label}批："
        f"预计输入Token={input_tokens}"
    )

    print(
        f"Groq第{batch_label}批："
        f"max_completion_tokens={output_tokens}"
    )


    last_error = None


    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"Groq第{batch_label}批："
            f"第{attempt}次请求"
        )


        try:

            response = (
                client
                .chat
                .completions
                .create(

                    model=GROQ_MODEL,

                    messages=[
                        {
                            "role":
                                "system",

                            "content":
                                SYSTEM_PROMPT
                        },
                        {
                            "role":
                                "user",

                            "content":
                                prompt
                        }
                    ],

                    temperature=0,

                    # GPT-OSS官方支持
                    reasoning_effort="low",

                    # JSON Object Mode
                    response_format={
                        "type":
                            "json_object"
                    },

                    # 动态输出Token
                    max_completion_tokens=
                        output_tokens
                )
            )


            if not response.choices:

                raise ValueError(
                    "Groq没有返回choices"
                )


            message = (
                response
                .choices[0]
                .message
            )


            text = (
                message.content
            )


            if not text:

                raise ValueError(
                    "Groq返回content为空"
                )


            text = clean_json_text(
                text
            )


            try:

                result = json.loads(
                    text
                )

            except json.JSONDecodeError as e:

                raise ValueError(
                    f"Groq返回JSON解析失败：{e}"
                )


            results = extract_results(
                result
            )


            if results is None:

                raise ValueError(
                    "Groq返回JSON对象，"
                    "但没有results/articles/data数组"
                )


            # ==================================================
            # 关键验证
            #
            # 如果只返回14/39：
            #
            # 这里直接失败。
            #
            # 上层会自动拆批。
            # ==================================================

            validate_batch_results(
                results,
                articles
            )


            return results


        except Exception as e:

            last_error = e

            print(
                f"Groq第{batch_label}批失败："
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
        f"Groq第{batch_label}批达到最大重试次数："
        f"{last_error}"
    )


# ============================================================
# 失败批次自动拆半
# ============================================================

def split_batch(
    articles
):

    if len(articles) <= MIN_SPLIT_SIZE:

        return None


    middle = len(articles) // 2

    left = articles[
        :middle
    ]

    right = articles[
        middle:
    ]


    return (
        left,
        right
    )


# ============================================================
# 递归稳定分析
#
# 这是本版真正解决：
#
# “请求成功，但只返回部分结果”
#
# 的核心。
# ============================================================

def analyze_batch_with_fallback(
    client,
    articles,
    batch_label
):

    print(
        "\n------------------------------------------------------------"
    )

    print(
        f"正在分析批次：{batch_label}"
    )

    print(
        f"本批新闻数量："
        f"{len(articles)}"
    )


    (
        input_tokens,
        output_tokens,
        total_tokens
    ) = estimate_request_tokens(
        articles
    )


    print(
        f"预计输入Token："
        f"{input_tokens}"
    )

    print(
        f"动态输出Token："
        f"{output_tokens}"
    )

    print(
        f"预计请求Token："
        f"{total_tokens}"
    )

    print(
        "------------------------------------------------------------"
    )


    # ========================================================
    # 第一步：直接请求
    # ========================================================

    try:

        results = request_groq_batch(

            client,

            articles,

            batch_label

        )


        print(
            f"批次{batch_label}分析成功："
            f"{len(results)}条"
        )


        return results


    except Exception as e:

        print(
            f"批次{batch_label}分析失败："
            f"{e}"
        )


    # ========================================================
    # 第二步：自动拆半
    # ========================================================

    if not AUTO_SPLIT_ON_FAILURE:

        raise RuntimeError(
            f"批次{batch_label}最终失败"
        )


    if len(articles) <= MIN_SPLIT_SIZE:

        raise RuntimeError(
            f"批次{batch_label}只有"
            f"{len(articles)}条，"
            f"仍无法完成AI分析"
        )


    split_result = split_batch(
        articles
    )


    if not split_result:

        raise RuntimeError(
            f"批次{batch_label}无法继续拆分"
        )


    left, right = split_result


    print(
        "\n============================================================"
    )

    print(
        f"批次{batch_label}无法稳定完成。"
    )

    print(
        f"自动拆分为："
        f"{len(left)}条 + {len(right)}条"
    )

    print(
        "不会使用当前批次的残缺结果。"
    )

    print(
        "============================================================"
    )


    # ========================================================
    # 第三个层级：
    # 分别完整成功
    # ========================================================

    left_results = (
        analyze_batch_with_fallback(
            client,
            left,
            f"{batch_label}.1"
        )
    )


    right_results = (
        analyze_batch_with_fallback(
            client,
            right,
            f"{batch_label}.2"
        )
    )


    return (
        left_results
        + right_results
    )


# ============================================================
# 合并结果
# ============================================================

def merge_results(
    results
):

    merged = []

    for result in results:

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
# 最终ID验证
# ============================================================

def validate_final_results(
    results,
    articles
):

    expected_ids = {
        str(
            article["id"]
        )
        for article
        in articles
    }


    actual_ids = set()


    for item in results:

        if not isinstance(
            item,
            dict
        ):

            raise ValueError(
                "最终结果存在非对象"
            )


        if "id" not in item:

            raise ValueError(
                "最终结果存在缺失id"
            )


        item_id = str(
            item["id"]
        )


        if item_id in actual_ids:

            raise ValueError(
                f"最终结果存在重复id："
                f"{item_id}"
            )


        actual_ids.add(
            item_id
        )


    if (
        actual_ids
        != expected_ids
    ):

        raise ValueError(
            "最终结果ID不完整："
            f"期望={sorted(expected_ids)}, "
            f"实际={sorted(actual_ids)}"
        )


    if len(results) != len(
        articles
    ):

        raise ValueError(
            "最终结果数量错误："
            f"期望={len(articles)}, "
            f"实际={len(results)}"
        )


    return True


# ============================================================
# AI失败
# ============================================================

def mark_analysis_failed(
    articles
):

    failed = []

    for article in articles:

        item = dict(
            article
        )

        item[
            "market_relevant"
        ] = False

        item[
            "ai_analysis_failed"
        ] = True

        failed.append(
            item
        )

    return failed


# ============================================================
# 主分析函数
# ============================================================

def analyze_news_list(
    articles
):

    if not articles:

        return []


    client = get_client()


    # ========================================================
    # 建立全局ID
    # ========================================================

    prepared = []


    for index, article in enumerate(
        articles,
        1
    ):

        prepared.append({

            "id":
                index,

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


    # ========================================================
    # 初始批次
    # ========================================================

    initial_batches = (
        build_initial_batches(
            prepared
        )
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
        "分析模式：自动Token安全分批"
    )

    print(
        f"单批最大新闻数："
        f"{MAX_ARTICLES_PER_BATCH}"
    )

    print(
        f"推荐批次大小："
        f"{PREFERRED_ARTICLES_PER_BATCH}"
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
        "reasoning_effort：low"
    )

    print(
        "自动拆分：开启"
    )

    print(
        "============================================================"
    )


    print(
        f"自动生成初始批次："
        f"{len(initial_batches)} 批"
    )


    for index, batch in enumerate(
        initial_batches,
        1
    ):

        (
            input_tokens,
            output_tokens,
            total_tokens
        ) = estimate_request_tokens(
            batch
        )


        print(
            f"  第{index}批："
            f"{len(batch)}条，"
            f"预计输入Token："
            f"{input_tokens}，"
            f"动态输出Token："
            f"{output_tokens}，"
            f"预计请求Token："
            f"{total_tokens}"
        )


    # ========================================================
    # 所有批次逐一完整分析
    # ========================================================

    all_results = []


    try:

        for batch_index, batch in enumerate(
            initial_batches,
            1
        ):

            batch_results = (
                analyze_batch_with_fallback(

                    client,

                    batch,

                    str(batch_index)

                )
            )


            # -----------------------------------------------
            # 再次验证这个最终批次
            # -----------------------------------------------

            validate_batch_results(
                batch_results,
                batch
            )


            all_results.append(
                batch_results
            )


    except Exception as e:

        print(
            "\n============================================================"
        )

        print(
            "Groq批量新闻分析整体失败"
        )

        print(
            f"失败原因：{e}"
        )

        print(
            "不会使用任何不完整分析结果。"
        )

        print(
            "============================================================"
        )

        return mark_analysis_failed(
            articles
        )


    # ========================================================
    # 只有所有批次成功后，才允许合并
    # ========================================================

    try:

        merged_results = merge_results(
            all_results
        )


        validate_final_results(
            merged_results,
            prepared
        )


    except Exception as e:

        print(
            "\n============================================================"
        )

        print(
            f"Groq最终结果验证失败：{e}"
        )

        print(
            "不会使用任何不完整分析结果。"
        )

        print(
            "============================================================"
        )

        return mark_analysis_failed(
            articles
        )


    # ========================================================
    # 建立结果索引
    # ========================================================

    result_map = {}

    for item in merged_results:

        item_id = str(
            item["id"]
        )

        result_map[
            item_id
        ] = item


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


        item = dict(
            article
        )


        item.update({

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
            item
        )


        print(
            f"[{index}/{len(articles)}] "
            f"{item.get('title', '')}"
        )

        print(
            f"  金融市场相关："
            f"{item.get('market_relevant')}"
        )

        print(
            f"  分类："
            f"{item.get('category')}"
        )

        print(
            f"  事件："
            f"{item.get('event_type')}"
        )

        print(
            f"  影响范围："
            f"{item.get('impact_scope_level')}"
        )

        print(
            f"  影响程度："
            f"{item.get('impact_degree_level')}"
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
        f"初始批次数："
        f"{len(initial_batches)}"
    )

    print(
        "AI调用方式："
        "Token安全 + 自动拆分 + 完整性验证"
    )

    print(
        "所有批次均已完整成功。"
    )

    print(
        "============================================================"
    )


    return analyzed


# ============================================================
# 单条新闻分析
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

    test_articles = [

        {
            "title":
                "Fed keeps interest rates unchanged",

            "summary":
                "The Federal Reserve kept interest rates unchanged.",

            "source":
                "CNBC Finance",

            "url":
                "https://example.com/fed"
        },

        {
            "title":
                "Oil prices rise amid supply concerns",

            "summary":
                "Oil prices moved higher as markets assessed supply risks.",

            "source":
                "CNBC Markets",

            "url":
                "https://example.com/oil"
        }

    ]


    result = analyze_news_list(
        test_articles
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
