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
# 核心设计：
#
# 1. GPT-OSS 120B
# 2. reasoning_effort = low
# 3. JSON Object Mode
# 4. 最多50条/批
# 5. Token安全控制
# 6. 动态max_completion_tokens
# 7. 保守Token估算
# 8. finish_reason检查
# 9. JSON结构兼容
# 10. ID完整性验证
# 11. 批次失败自动重试
# 12. 批次不完整自动拆分
# 13. 所有批次成功后才合并
# 14. 任意最终批次失败 -> 整体失败
# 15. 不使用残缺结果
#
# ============================================================


# ============================================================
# Groq模型
# ============================================================

GROQ_MODEL = "openai/gpt-oss-120b"


# ============================================================
# 批次控制
# ============================================================

# 绝对数量上限
MAX_ARTICLES_PER_BATCH = 50

# ------------------------------------------------------------
# 真正用于自动切批的安全Token目标
#
# 注意：
#
# 这不是Groq官方TPM。
# Groq当前环境可能是8000 TPM。
#
# 我们主动留出安全空间。
# ------------------------------------------------------------

TOKEN_SAFETY_LIMIT = 6500


# ------------------------------------------------------------
# 最小批次
#
# 如果一个批次失败，会不断拆分。
#
# 最小不会低于1条。
# ------------------------------------------------------------

MIN_ARTICLES_PER_BATCH = 1


# ------------------------------------------------------------
# 输出Token估算
#
# 每条新闻需要：
#
# market_relevant
# event_type
# category
# core_fact
# market_impact_reason
# event_id
# impact_scope_level
# impact_degree_level
#
# 这里不是最终max_completion_tokens。
# 只是用于批次规划。
# ------------------------------------------------------------

OUTPUT_TOKENS_PER_ARTICLE = 110

MIN_OUTPUT_TOKENS = 700

MAX_OUTPUT_TOKENS = 2200


# ------------------------------------------------------------
# Groq请求最大重试次数
# ------------------------------------------------------------

MAX_RETRIES = 3

RETRY_DELAY_SECONDS = 2


# ------------------------------------------------------------
# Token估算安全系数
#
# 这是本次修复最重要的参数之一。
#
# 原来的估算明显低估真实请求Token。
#
# 因此不再使用：
#
# 中文 / 1.5
# 英文 / 4
#
# 而使用更保守的估算。
# ------------------------------------------------------------

TOKEN_ESTIMATE_SAFETY_FACTOR = 1.45


# ------------------------------------------------------------
# 请求失败后自动拆分
# ------------------------------------------------------------

ENABLE_AUTO_SPLIT = True


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

如果输入信息不足：

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
11. 不进行TOP10
12. 不进行最终排序

每条结果严格包含：

id
market_relevant
event_type
category
core_fact
market_impact_reason
event_id
impact_scope_level
impact_degree_level

不要输出reasoning。

不要输出额外字段。
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
#
# 核心修复：
#
# 不再使用过于乐观的中文/英文比例估算。
#
# 采用统一保守字符比例，
# 再乘安全系数。
# ============================================================

def estimate_tokens(text):

    if not text:

        return 0

    text = str(text)

    # --------------------------------------------------------
    # 基础字符估算
    #
    # 混合中英文新闻统一采用约2字符/token的保守估算。
    # --------------------------------------------------------

    base_tokens = len(text) / 2.0

    safe_tokens = (
        base_tokens
        * TOKEN_ESTIMATE_SAFETY_FACTOR
    )

    return max(
        1,
        int(safe_tokens)
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
# System Prompt Token估算
# ============================================================

def estimate_system_tokens():

    return estimate_tokens(
        SYSTEM_PROMPT
    )


# ============================================================
# 用户Prompt固定开销
# ============================================================

def estimate_prompt_overhead():

    # System prompt
    #
    # JSON Object要求
    #
    # 输入说明
    #
    # 额外安全空间

    return (
        estimate_system_tokens()
        + 700
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
        calculated,
        MIN_OUTPUT_TOKENS
    )

    calculated = min(
        calculated,
        MAX_OUTPUT_TOKENS
    )

    return int(
        calculated
    )


# ============================================================
# 单批Token估算
# ============================================================

def estimate_batch_tokens(
    articles
):

    input_tokens = (
        estimate_prompt_overhead()
    )

    for article in articles:

        input_tokens += (
            estimate_article_tokens(
                article
            )
        )

    output_tokens = calculate_output_tokens(
        len(articles)
    )

    total_tokens = (
        input_tokens
        + output_tokens
    )

    return (
        input_tokens,
        output_tokens,
        total_tokens
    )


# ============================================================
# 判断批次是否安全
# ============================================================

def is_batch_safe(
    articles
):

    if not articles:

        return True

    if len(articles) > MAX_ARTICLES_PER_BATCH:

        return False

    (
        input_tokens,
        output_tokens,
        total_tokens
    ) = estimate_batch_tokens(
        articles
    )

    return (
        total_tokens
        <= TOKEN_SAFETY_LIMIT
    )


# ============================================================
# 自动生成初始批次
#
# 50条只是硬上限。
#
# Token安全优先。
# ============================================================

def build_batches(
    articles
):

    batches = []

    current = []

    for article in articles:

        candidate = (
            current
            + [article]
        )

        if (
            current
            and not is_batch_safe(
                candidate
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
# 如果单条新闻本身估算过大
# ============================================================

def force_split_batch(
    batch
):

    if len(batch) <= 1:

        return [batch]

    midpoint = len(batch) // 2

    return [

        batch[:midpoint],

        batch[midpoint:]

    ]


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
            :-3
        ]


    return text.strip()


# ============================================================
# 提取JSON结果
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
# 验证AI结果
# ============================================================

def validate_ai_results(
    results,
    expected_ids
):

    if not isinstance(
        results,
        list
    ):

        raise ValueError(
            "Groq返回结果不是数组"
        )


    if len(results) != len(
        expected_ids
    ):

        raise ValueError(
            "Groq返回数量错误："
            f"期望 {len(expected_ids)} 条，"
            f"实际 {len(results)} 条"
        )


    expected_ids = {
        str(x)
        for x in expected_ids
    }


    actual_ids = set()


    for item in results:

        if not isinstance(
            item,
            dict
        ):

            raise ValueError(
                "Groq返回结果存在非JSON对象"
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
            "Groq返回ID不完整或错误："
            f"期望={sorted(expected_ids)}, "
            f"实际={sorted(actual_ids)}"
        )


    return True


# ============================================================
# 构造批次Prompt
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
请分析下面全部 {count} 条新闻。

必须对每一个id返回一个且仅一个结果。

输入新闻：

{articles_json}


============================================================
必须返回的JSON结构
============================================================

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

1. results必须包含全部 {count} 条新闻。

2. 每一个输入id必须返回。

3. id必须完全对应输入。

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

9. category必须根据“事件本身是什么”判断。

10. 不允许按照关键词机械分类。

11. core_fact只能来自输入新闻。

12. market_impact_reason只能来自输入新闻。

13. 不允许编造任何信息。

14. event_id必须描述核心事件。

15. 同一事件的不同报道尽可能使用相同event_id。

16. impact_scope_level只能使用：

global
multi_region
regional
country
industry
company
limited

17. impact_degree_level只能使用：

very_high
high
medium
low

18. 不计算最终评分。

19. 不计算来源可信度。

20. 不进行TOP10筛选。

21. 不进行新闻排序。

22. 不输出Markdown。

23. 不输出代码块。

24. 不输出解释文字。

25. 不输出reasoning。

26. 只返回合法JSON。

27. JSON顶层必须是对象。

28. JSON对象必须包含results数组。

29. 不要输出任何额外字段。

30. 即使market_relevant=false，也必须返回完整字段。

"""


# ============================================================
# 请求Groq
# ============================================================

def request_groq_batch(
    client,
    batch,
    batch_number
):

    prompt = build_batch_prompt(
        batch
    )


    expected_ids = [
        article["id"]
        for article in batch
    ]


    (
        estimated_input,
        estimated_output,
        estimated_total
    ) = estimate_batch_tokens(
        batch
    )


    last_error = None


    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        print(
            f"Groq第{batch_number}批："
            f"第{attempt}次请求"
        )


        # ----------------------------------------------------
        # 动态输出Token
        # ----------------------------------------------------

        max_completion_tokens = (
            calculate_output_tokens(
                len(batch)
            )
        )


        print(
            "本次max_completion_tokens："
            f"{max_completion_tokens}"
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
                # GPT-OSS reasoning不返回给业务层
                # ------------------------------------------------

                reasoning_format="hidden",

                # ------------------------------------------------
                # JSON Object Mode
                # ------------------------------------------------

                response_format={
                    "type": "json_object"
                },

                # ------------------------------------------------
                # 动态输出上限
                # ------------------------------------------------

                max_completion_tokens=(
                    max_completion_tokens
                )

            )


            # ----------------------------------------------------
            # 获取finish_reason
            # ----------------------------------------------------

            choice = response.choices[0]

            finish_reason = getattr(
                choice,
                "finish_reason",
                None
            )


            print(
                f"Groq第{batch_number}批"
                f"finish_reason："
                f"{finish_reason}"
            )


            # ----------------------------------------------------
            # 如果因为长度停止
            # ----------------------------------------------------

            if finish_reason in (
                "length",
                "max_tokens"
            ):

                raise ValueError(
                    "Groq输出达到Token上限，"
                    "JSON结果可能不完整"
                )


            text = (
                choice.message.content
            )


            if not text:

                raise ValueError(
                    "Groq返回内容为空"
                )


            text = clean_json_text(
                text
            )


            # ----------------------------------------------------
            # JSON解析
            # ----------------------------------------------------

            try:

                result = json.loads(
                    text
                )

            except json.JSONDecodeError as e:

                raise ValueError(
                    "Groq返回内容不是合法JSON："
                    f"{e}"
                )


            # ----------------------------------------------------
            # 兼容results/articles/data
            # ----------------------------------------------------

            results = extract_results(
                result
            )


            if results is None:

                raise ValueError(
                    "Groq返回JSON对象，"
                    "但没有找到results、"
                    "articles或data数组"
                )


            # ----------------------------------------------------
            # ID完整性验证
            # ----------------------------------------------------

            validate_ai_results(
                results,
                expected_ids
            )


            # ----------------------------------------------------
            # 成功
            # ----------------------------------------------------

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
        f"Groq第{batch_number}批"
        f"达到最大重试次数："
        f"{last_error}"
    )


# ============================================================
# 分析单个批次
#
# 如果批次失败：
#
# 1. 重试3次
# 2. 仍失败 -> 自动二分
# 3. 子批次继续执行
#
# 这是本版真正解决：
#
# “39条只返回14条”
#
# 的核心机制。
# ============================================================

def analyze_batch_recursive(
    client,
    batch,
    batch_label
):

    try:

        print(
            "\n------------------------------------------------------------"
        )

        print(
            f"正在分析批次：{batch_label}"
        )

        print(
            f"本批新闻数量："
            f"{len(batch)}"
        )


        (
            input_tokens,
            output_tokens,
            total_tokens
        ) = estimate_batch_tokens(
            batch
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
            f"预计总Token："
            f"{total_tokens}"
        )


        print(
            "------------------------------------------------------------"
        )


        results = request_groq_batch(
            client,
            batch,
            batch_label
        )


        print(
            f"批次{batch_label}分析成功："
            f"{len(results)}条"
        )


        return results


    except Exception as e:

        print(
            f"\n批次{batch_label}分析失败："
            f"{e}"
        )


        # ----------------------------------------------------
        # 无法继续拆分
        # ----------------------------------------------------

        if (
            not ENABLE_AUTO_SPLIT
            or len(batch) <= MIN_ARTICLES_PER_BATCH
        ):

            raise RuntimeError(
                f"批次{batch_label}最终失败："
                f"{e}"
            )


        # ----------------------------------------------------
        # 自动二分
        # ----------------------------------------------------

        sub_batches = force_split_batch(
            batch
        )


        print(
            "\n============================================================"
        )

        print(
            f"批次{batch_label}无法稳定完成。"
        )

        print(
            f"自动拆分为："
            f"{len(sub_batches)}个子批次"
        )

        print(
            "不会使用当前批次的残缺结果。"
        )

        print(
            "============================================================"
        )


        all_sub_results = []


        for index, sub_batch in enumerate(
            sub_batches,
            1
        ):

            sub_label = (
                f"{batch_label}.{index}"
            )


            sub_results = (
                analyze_batch_recursive(
                    client,
                    sub_batch,
                    sub_label
                )
            )


            all_sub_results.extend(
                sub_results
            )


        # ----------------------------------------------------
        # 拆分后再次验证
        # ----------------------------------------------------

        expected_ids = [
            article["id"]
            for article in batch
        ]


        validate_ai_results(
            all_sub_results,
            expected_ids
        )


        print(
            f"批次{batch_label}"
            f"拆分分析完成："
            f"{len(all_sub_results)}条"
        )


        return all_sub_results


# ============================================================
# 整体失败标记
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
# 最终结果合并
# ============================================================

def merge_and_validate_all_results(
    results,
    articles
):

    expected_ids = {
        str(article["id"])
        for article in articles
    }


    if len(results) != len(
        articles
    ):

        raise ValueError(
            "最终结果数量错误："
            f"期望={len(articles)}, "
            f"实际={len(results)}"
        )


    result_map = {}


    for item in results:

        if not isinstance(
            item,
            dict
        ):

            raise ValueError(
                "最终结果包含非JSON对象"
            )


        if "id" not in item:

            raise ValueError(
                "最终结果缺少id"
            )


        item_id = str(
            item["id"]
        )


        if item_id in result_map:

            raise ValueError(
                f"最终结果存在重复ID："
                f"{item_id}"
            )


        result_map[
            item_id
        ] = item


    actual_ids = set(
        result_map.keys()
    )


    if actual_ids != expected_ids:

        raise ValueError(
            "最终结果ID不完整："
            f"期望={sorted(expected_ids)}, "
            f"实际={sorted(actual_ids)}"
        )


    return result_map


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
    # 建立全局ID
    # ========================================================

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


    # ========================================================
    # 初始批次
    # ========================================================

    batches = build_batches(
        prepared
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
        f"{len(batches)} 批"
    )


    for index, batch in enumerate(
        batches,
        1
    ):

        (
            input_tokens,
            output_tokens,
            total_tokens
        ) = estimate_batch_tokens(
            batch
        )


        print(
            f"  第{index}批："
            f"{len(batch)}条，"
            f"预计输入Token："
            f"{input_tokens}，"
            f"动态输出Token："
            f"{output_tokens}，"
            f"预计总Token："
            f"{total_tokens}"
        )


    # ========================================================
    # 分析所有批次
    # ========================================================

    all_results = []


    try:

        for index, batch in enumerate(
            batches,
            1
        ):

            batch_results = (
                analyze_batch_recursive(
                    client,
                    batch,
                    str(index)
                )
            )


            all_results.extend(
                batch_results
            )


        # ----------------------------------------------------
        # 所有批次完成后才做最终验证
        # ----------------------------------------------------

        result_map = (
            merge_and_validate_all_results(
                all_results,
                prepared
            )
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
        "AI调用方式："
        "Token安全分批 + 失败自动拆分"
    )

    print(
        "所有批次均通过ID完整性验证"
    )

    print(
        "未使用任何残缺分析结果"
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
        "\n测试结果："
    )


    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=4
        )
    )
