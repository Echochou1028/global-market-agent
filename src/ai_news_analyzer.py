import json
import os
import time

from openai import OpenAI


# ============================================================
# 全球金融市场日报
# ai_news_analyzer.py
#
# 稳定版 v2
#
# 本版核心改动：
#
# 1. 批量从 6条/批 降为 5条/批
#    —— 给 gpt-oss-120b 的隐藏推理阶段留出更多有效Token空间，
#       避免JSON结果被强制截断（这是v1真正的失败原因）
# 2. 动态输出Token预算大幅上调（1800-2500）
#    —— 原来的700-1200只够"内容"，不够"推理+内容"
# 3. 新增 finish_reason 截断检测
#    —— 一旦命中 finish_reason == "length"，直接明确报错，
#       不再靠"返回数量不对"这种间接信号倒推原因
# 4. 新增 Groq 免费额度 TPM 限速（8000 TPM）
#    —— 按每批实际Token消耗动态计算批次间隔，
#       避免免费额度下的429限流
# 5. 分类体系从7类改为3类（不再按国际/中国拆分）
#    —— 宏观、政策与地缘 / 市场与资产 / 公司、行业与研报
#    —— 分类只判断"事件本身是什么"，不参与最终评分
#
# 本文件仍然不负责：
#
# ❌ 最终评分（由 news_scoring.py 按 影响范围→影响程度→来源可信度 计算）
# ❌ 来源可信度评分
# ❌ TOP10 / 排序（含"高影响全部保留、低影响按分类限量"的策略）
#
# ============================================================


# ============================================================
# Groq 模型
# ============================================================

GROQ_MODEL = "openai/gpt-oss-120b"


# ============================================================
# 批次控制
#
# 重要：
#
# MAX_ARTICLES_PER_BATCH 是"硬上限"，不是必须凑满的数量。
#
# 5条/批是本版的默认值——用真实运行日志验证过：
# 6条/批时，gpt-oss-120b的隐藏推理经常把700-1200的输出预算
# 提前耗尽，JSON会被强制截断成合法但不完整的数组。
# 5条/批 + 更大的输出预算，能显著降低这个概率。
# ============================================================

MAX_ARTICLES_PER_BATCH = 5


# ============================================================
# Token控制
#
# TOKEN_SAFETY_LIMIT 只是"单批不要太离谱"的粗粒度保护，
# 真正决定批次大小的是 MAX_ARTICLES_PER_BATCH。
#
# 输出Token预算大幅上调：
# 原来 700-1200 只覆盖"内容"部分，
# 没有算上 gpt-oss-120b 隐藏推理阶段消耗的Token。
# 即使 reasoning_effort="low"，推理阶段仍然会占用
# max_completion_tokens 里的一部分预算。
# ============================================================

TOKEN_SAFETY_LIMIT = 7000

OUTPUT_TOKENS_PER_ARTICLE = 300

MIN_OUTPUT_TOKEN_RESERVE = 1800

MAX_OUTPUT_TOKEN_RESERVE = 2500


# ============================================================
# 请求重试
# ============================================================

MAX_RETRIES = 3

RETRY_DELAY_SECONDS = 3


# ============================================================
# Groq 免费额度限速
#
# 免费额度下 openai/gpt-oss-120b 的硬限制是 8000 TPM
# （每分钟Token数，而不是每日请求数）。
#
# 这里按每批"实际消耗的Token数"动态计算批次之间该等多久，
# 而不是猜一个固定秒数——批次之间的真实间隔会随新闻长度浮动。
#
# RATE_LIMIT_SAFETY_FACTOR 留一点余量，避免贴着上限走
# （重试、估算误差都需要缓冲）。
# ============================================================

GROQ_TPM_LIMIT = 8000

RATE_LIMIT_SAFETY_FACTOR = 1.2

MIN_BATCH_INTERVAL_SECONDS = 30


# ============================================================
# 初始化 Groq
# ============================================================

def get_client():

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:

        raise RuntimeError("GROQ_API_KEY 未配置")

    return OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1"
    )


# ============================================================
# AI系统规则
# ============================================================

SYSTEM_PROMPT = """
你是"全球金融市场日报 Agent"的新闻事件分析引擎。

你的任务是：

理解新闻事件本身，
判断它是否具有实际的金融市场影响，
判断事件类型，
确定新闻分类，
判断事件影响范围，
判断事件影响程度，
提取核心事实，
并识别同一事件。

你不是最终评分器。

最终评分由本地 Python 程序执行。


============================================================
一、金融市场相关性
============================================================

只有对金融市场具有实际影响，
或者明确可能影响金融市场的信息，
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
- 经营事件

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

"事件本身是什么"

进行分类。

绝对不能因为文章中出现某个关键词，
就机械地按照关键词分类。

重要原则：

"国际 / 中国"不是分类维度。

三个分类都必须同时覆盖国际与中国市场的同类事件，
不能因为新闻发生在哪个国家就单独归为一类。

允许使用以下分类：

1. 宏观、政策与地缘
2. 市场与资产
3. 公司、行业与研报


============================================================
三、分类定义与示例
============================================================

【1. 宏观、政策与地缘】

定义：

影响经济环境、政策预期及国际关系的重大事件。

包含：

美联储/中国央行、利率、通胀、就业、GDP、
财政政策、货币政策、监管政策、贸易政策、
关税、制裁、战争、地缘冲突、中美关系等。

示例：

中国央行降息 → 宏观、政策与地缘
美联储降息 → 宏观、政策与地缘
中美关税升级 → 宏观、政策与地缘


【2. 市场与资产】

定义：

直接影响金融市场及各类资产价格的事件。

包含：

全球股市、中国股市、港股、美股、
债券、汇率、人民币、美元、
黄金、原油、商品、加密资产、
市场剧烈波动等。

示例：

中国A股大跌 → 市场与资产
纳斯达克大跌 → 市场与资产


【3. 公司、行业与研报】

定义：

影响具体公司、行业及投资判断的重要信息。

包含：

公司财报、业绩预告、并购重组、重大订单、
管理层变化、AI、半导体、科技、能源等行业，
以及券商/知名投行/知名机构重大研报与观点。

示例：

英伟达财报 → 公司、行业与研报
中国半导体行业重大政策 → 公司、行业与研报


============================================================
四、核心事实
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
五、市场影响原因
============================================================

market_impact_reason：

说明为什么这个事件可能影响金融市场。

必须根据新闻内容判断。

不能凭空添加新闻没有提供的信息。


============================================================
六、影响范围
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
七、影响程度
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
八、影响范围与影响程度
============================================================

影响范围和影响程度必须分别判断。

不能因为：

"来源很权威"

就提高影响范围。

不能因为：

"新闻来自 CNBC、Reuters、Bloomberg 等"

就提高影响程度。

来源可信度由本地 Python 程序单独计算。

分类（category）不参与评分，
最终评分仅由 影响范围、影响程度、来源可信度 三项计算，
由本地 news_scoring.py 完成。


============================================================
九、事件ID
============================================================

event_id 用于识别：

"不同新闻是否实际上描述同一个事件"。

同一事件的不同媒体报道，
应该尽可能使用相同或高度一致的 event_id。

event_id 必须：

- 简短
- 稳定
- 描述核心事件
- 不包含媒体名称
- 不包含新闻标题原文
- 不使用随机字符串


============================================================
十、事实真实性
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
十一、输出规则
============================================================

你将一次性分析一批新闻。

必须：

1. 每条输入新闻返回一个结果
2. id必须完全对应输入新闻
3. 不允许遗漏id
4. 不允许增加不存在的id
5. 不允许改变id
6. 不允许重复id
7. 不允许输出Markdown
8. 不允许输出解释文字
9. 只返回合法JSON
10. 不进行最终评分
11. 不计算来源可信度
12. 不进行TOP10筛选
13. 不进行新闻排序
14. 不输出reasoning


============================================================
十二、输出字段
============================================================

每条新闻必须严格返回：

id
market_relevant
event_type
category
core_fact
market_impact_reason
event_id
impact_scope_level
impact_degree_level

不要增加其他字段。


============================================================
十三、JSON格式
============================================================

JSON顶层必须是对象。

格式必须为：

{
    "results": [
        {
            "id": 1,
            "market_relevant": true,
            "event_type": "事件本身是什么",
            "category": "分类",
            "core_fact": "核心事实",
            "market_impact_reason": "金融市场影响原因",
            "event_id": "核心事件标识",
            "impact_scope_level": "global",
            "impact_degree_level": "high"
        }
    ]
}

必须保证：

results 数量 = 输入新闻数量。

"""


# ============================================================
# 新闻预处理
# ============================================================

def prepare_articles(articles):

    prepared = []

    for index, article in enumerate(articles, 1):

        prepared.append({
            "id": index,
            "title": article.get("title", ""),
            "summary": article.get("summary", ""),
            "source": article.get("source", ""),
            "url": article.get("url", "")
        })

    return prepared


# ============================================================
# Token估算
#
# 注意：
# 这里只用于批次大小控制，不是Groq官方Token计数器，
# 因此故意保持较大的安全空间。
# ============================================================

def estimate_tokens(text):

    if not text:
        return 0

    text = str(text)

    chinese_count = sum(
        1 for char in text if "\u4e00" <= char <= "\u9fff"
    )

    other_count = len(text) - chinese_count

    estimated = chinese_count / 1.5 + other_count / 4

    return int(estimated)


def estimate_article_tokens(article):

    article_text = json.dumps(article, ensure_ascii=False)

    return estimate_tokens(article_text)


def estimate_prompt_overhead():

    return estimate_tokens(SYSTEM_PROMPT) + 500


# ============================================================
# 动态输出 Token
#
# 每条新闻预留约300 Token（含分摊的推理开销）。
# 最低1800，最高2500——这个范围是按"5条/批需要覆盖
# 推理+8字段×5条内容"反推出来的，不是拍脑袋的数字。
# ============================================================

def calculate_output_tokens(article_count):

    dynamic_tokens = article_count * OUTPUT_TOKENS_PER_ARTICLE

    dynamic_tokens = max(dynamic_tokens, MIN_OUTPUT_TOKEN_RESERVE)

    dynamic_tokens = min(dynamic_tokens, MAX_OUTPUT_TOKEN_RESERVE)

    return dynamic_tokens


def estimate_batch_tokens(articles):

    input_tokens = estimate_prompt_overhead()

    for article in articles:
        input_tokens += estimate_article_tokens(article)

    output_tokens = calculate_output_tokens(len(articles))

    total_tokens = input_tokens + output_tokens

    return input_tokens, output_tokens, total_tokens


# ============================================================
# 建立稳定小批次
#
# 默认 5条/批，同时检查Token总量。
# 如果5条仍然超过安全阈值，会自动降低当前批次数量。
#
# 但是：
# ❌ 不递归
# ❌ 不无限拆分
# ============================================================

def build_batches(articles):

    batches = []

    current_batch = []

    for article in articles:

        candidate = current_batch + [article]

        input_tokens, output_tokens, total_tokens = estimate_batch_tokens(candidate)

        too_many_articles = len(candidate) > MAX_ARTICLES_PER_BATCH

        too_many_tokens = total_tokens > TOKEN_SAFETY_LIMIT

        if current_batch and (too_many_articles or too_many_tokens):

            batches.append(current_batch)

            current_batch = [article]

        else:

            current_batch = candidate

    if current_batch:
        batches.append(current_batch)

    return batches


# ============================================================
# 构造批次 Prompt
# ============================================================

def build_batch_prompt(articles):

    articles_json = json.dumps(articles, ensure_ascii=False)

    count = len(articles)

    return f"""
请严格按照系统规则分析下面全部 {count} 条新闻。

必须对每一条新闻返回一个结果。

输入新闻：

{articles_json}


============================================================
强制要求
============================================================

1. 必须返回 {count} 条结果。

2. 每个输入id必须返回。

3. id必须完全保持不变。

4. 不允许遗漏id。

5. 不允许增加不存在的id。

6. 不允许重复id。

7. market_relevant只能是true或false。

8. category只能使用以下3个分类：

宏观、政策与地缘
市场与资产
公司、行业与研报

9. category必须依据"事件本身是什么"判断，
不按"国际/中国"等地域划分——三个分类都同时覆盖国际与中国市场。

10. core_fact只能来自输入新闻。

11. market_impact_reason只能根据输入新闻判断。

12. impact_scope_level只能使用：

global
multi_region
regional
country
industry
company
limited

13. impact_degree_level只能使用：

very_high
high
medium
low

14. 不计算最终评分。

15. 不计算来源可信度。

16. 不进行TOP10筛选。

17. 不进行排序。

18. 不输出Markdown。

19. 不输出解释文字。

20. 不输出代码块。

21. 不输出reasoning。

22. 不增加任何额外字段。

23. JSON顶层必须是对象。

24. JSON对象必须包含results数组。

25. results数组必须包含全部 {count} 条结果。


============================================================
必须返回以下结构
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
"""


# ============================================================
# 清理 JSON
# ============================================================

def clean_json_text(text):

    if not text:
        return ""

    text = text.strip()

    if text.startswith("```json"):
        text = text[len("```json"):]
    elif text.startswith("```"):
        text = text[len("```"):]

    if text.endswith("```"):
        text = text[:-3]

    return text.strip()


# ============================================================
# 提取 results
# ============================================================

def extract_results(result):

    if not isinstance(result, dict):
        return None

    for key in ("results", "articles", "data"):

        value = result.get(key)

        if isinstance(value, list):
            return value

    return None


# ============================================================
# 验证AI结果
# ============================================================

def validate_ai_results(results, expected_ids):

    if not isinstance(results, list):
        raise ValueError("Groq返回结果不是数组")

    if len(results) != len(expected_ids):
        raise ValueError(
            "Groq返回数量错误："
            f"期望 {len(expected_ids)} 条，实际 {len(results)} 条"
        )

    actual_ids = set()

    for item in results:

        if not isinstance(item, dict):
            raise ValueError("Groq返回结果中存在非对象")

        if "id" not in item:
            raise ValueError("Groq返回结果缺少id")

        item_id = str(item["id"])

        if item_id in actual_ids:
            raise ValueError(f"Groq返回重复id：{item_id}")

        actual_ids.add(item_id)

    expected_id_set = {str(x) for x in expected_ids}

    if actual_ids != expected_id_set:
        raise ValueError(
            "Groq返回ID不完整或存在错误："
            f"期望={sorted(expected_id_set)}, 实际={sorted(actual_ids)}"
        )

    return True


# ============================================================
# 请求 Groq
#
# 不使用 reasoning_format / include_reasoning
#（gpt-oss-120b在Groq上不支持这两个作为标准kwarg传入）。
#
# 保留 reasoning_effort="low" + response_format=json_object，
# 并对 reasoning_effort 做一次兼容降级。
# ============================================================

def call_groq(client, messages, max_completion_tokens, use_reasoning_effort=True):

    kwargs = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": max_completion_tokens
    }

    if use_reasoning_effort:
        kwargs["reasoning_effort"] = "low"

    return client.chat.completions.create(**kwargs)


# ============================================================
# Groq 免费额度限速
#
# 按本批实际消耗的Token数（response.usage.total_tokens）
# 动态计算需要等待多久，再减去本批请求本身已经花掉的时间，
# 避免"傻等"浪费预算内的时间窗口。
# ============================================================

def wait_for_rate_limit(total_tokens_used, elapsed_seconds):

    target_seconds = (
        total_tokens_used / GROQ_TPM_LIMIT * 60 * RATE_LIMIT_SAFETY_FACTOR
    )

    target_seconds = max(target_seconds, MIN_BATCH_INTERVAL_SECONDS)

    sleep_seconds = target_seconds - elapsed_seconds

    if sleep_seconds > 0:

        print(
            f"限速等待：{sleep_seconds:.1f}秒 "
            f"（本批消耗{total_tokens_used} Token，"
            f"TPM限制{GROQ_TPM_LIMIT}，已用时{elapsed_seconds:.1f}秒）"
        )

        time.sleep(sleep_seconds)

    else:

        print(
            f"本批已用时{elapsed_seconds:.1f}秒，"
            f"超过限速所需间隔，无需额外等待"
        )


# ============================================================
# 单批请求
#
# 返回 (results, usage_info)
# usage_info 用于外层做限速节奏控制
# ============================================================

def request_groq_batch(client, articles, batch_number):

    prompt = build_batch_prompt(articles)

    expected_ids = [article["id"] for article in articles]

    input_tokens, output_tokens, total_tokens = estimate_batch_tokens(articles)

    last_error = None

    reasoning_effort_supported = True

    for attempt in range(1, MAX_RETRIES + 1):

        print(f"Groq第{batch_number}批：第{attempt}次请求")
        print(f"本次max_completion_tokens：{output_tokens}")

        try:

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ]

            try:

                response = call_groq(
                    client,
                    messages,
                    output_tokens,
                    use_reasoning_effort=reasoning_effort_supported
                )

            except TypeError as e:

                error_text = str(e)

                if "reasoning_effort" in error_text:

                    print(
                        "当前OpenAI SDK/Groq接口不支持 reasoning_effort，"
                        "自动降级为不传该参数。"
                    )

                    reasoning_effort_supported = False

                    response = call_groq(
                        client,
                        messages,
                        output_tokens,
                        use_reasoning_effort=False
                    )

                else:

                    raise

            # ================================================
            # 截断检测
            #
            # 这是本版新增的关键检查：
            # 一旦命中 finish_reason == "length"，
            # 说明 max_completion_tokens 不够（通常是被隐藏
            # 推理阶段吃掉了），必须直接报错，
            # 不能指望后面的数量校验来间接发现。
            # ================================================

            finish_reason = response.choices[0].finish_reason

            usage = response.usage

            usage_total_tokens = usage.total_tokens if usage else total_tokens

            if usage:
                print(
                    f"实际Token消耗：输入{usage.prompt_tokens} "
                    f"输出{usage.completion_tokens} "
                    f"总计{usage.total_tokens}"
                )

            print(f"finish_reason：{finish_reason}")

            if finish_reason == "length":
                raise ValueError(
                    "输出被截断（finish_reason=length），"
                    f"当前max_completion_tokens={output_tokens}不足以覆盖"
                    "推理+完整JSON输出，需要增大预算或减小批量"
                )

            text = response.choices[0].message.content

            if not text:
                raise ValueError("Groq返回内容为空")

            text = clean_json_text(text)

            result = json.loads(text)

            results = extract_results(result)

            if results is None:
                raise ValueError(
                    "Groq返回JSON对象，但没有results、articles或data数组"
                )

            validate_ai_results(results, expected_ids)

            return results, {"total_tokens": usage_total_tokens}

        except Exception as e:

            last_error = e

            print(f"Groq第{batch_number}批失败：{e}")

            if attempt < MAX_RETRIES:

                print(f"将在{RETRY_DELAY_SECONDS}秒后重试...")

                time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(
        f"Groq第{batch_number}批达到最大重试次数：{last_error}"
    )


# ============================================================
# AI失败结果
# ============================================================

def mark_analysis_failed(articles):

    failed = []

    for article in articles:

        item = dict(article)

        item["market_relevant"] = False

        item["ai_analysis_failed"] = True

        failed.append(item)

    return failed


# ============================================================
# 合并批次
# ============================================================

def merge_batch_results(batch_results_list):

    merged = []

    for batch_results in batch_results_list:

        if not isinstance(batch_results, list):
            raise ValueError("存在无效批次结果")

        merged.extend(batch_results)

    return merged


# ============================================================
# 批量分析新闻
# ============================================================

def analyze_news_list(articles):

    if not articles:
        return []

    print("\n============================================================")
    print("开始使用 Groq AI 批量分析新闻事件")
    print(f"待分析新闻：{len(articles)} 条")
    print("分析模式：稳定小批量 + 动态Token + 免费额度限速")
    print(f"单批最大新闻数：{MAX_ARTICLES_PER_BATCH}")
    print(f"Token安全阈值：{TOKEN_SAFETY_LIMIT}")
    print(f"模型：{GROQ_MODEL}")
    print("reasoning_effort：low")
    print(f"Groq免费额度TPM限制：{GROQ_TPM_LIMIT}")
    print("自动递归拆分：关闭")
    print("============================================================")

    client = get_client()

    # ========================================================
    # 建立全局ID
    # ========================================================

    prepared_articles = []

    for global_id, article in enumerate(articles, 1):

        prepared_articles.append({
            "id": global_id,
            "title": article.get("title", ""),
            "summary": article.get("summary", ""),
            "source": article.get("source", ""),
            "url": article.get("url", "")
        })

    # ========================================================
    # 自动建立稳定小批次
    # ========================================================

    batches = build_batches(prepared_articles)

    print(f"自动生成分析批次：{len(batches)} 批")

    for batch_index, batch in enumerate(batches, 1):

        input_tokens, output_tokens, total_tokens = estimate_batch_tokens(batch)

        print(
            f"  第{batch_index}批：{len(batch)}条，"
            f"预计输入Token：{input_tokens}，"
            f"动态输出Token：{output_tokens}，"
            f"预计总Token：{total_tokens}"
        )

    # ========================================================
    # 逐批分析
    #
    # 任何一批最终失败 → 不再继续 → 整体失败 →
    # 不使用前面成功批次的部分结果。
    #
    # 批次之间按实际Token消耗动态限速，
    # 避免Groq免费额度下的429限流。
    # ========================================================

    all_batch_results = []

    total_batches = len(batches)

    for batch_index, batch in enumerate(batches, 1):

        print("\n------------------------------------------------------------")
        print(f"正在分析批次：{batch_index}/{total_batches}")
        print(f"本批新闻数量：{len(batch)}")

        input_tokens, output_tokens, total_tokens = estimate_batch_tokens(batch)

        print(f"预计输入Token：{input_tokens}")
        print(f"动态输出Token：{output_tokens}")
        print(f"预计总Token：{total_tokens}")
        print("------------------------------------------------------------")

        batch_start_time = time.time()

        try:

            batch_results, usage_info = request_groq_batch(client, batch, batch_index)

        except Exception as e:

            print("\n============================================================")
            print("Groq批量新闻分析整体失败")
            print(f"失败批次：{batch_index}/{total_batches}")
            print(f"失败原因：{e}")
            print("不会使用任何不完整分析结果。")
            print("不会继续递归拆分。")
            print("============================================================")

            return mark_analysis_failed(articles)

        # ====================================================
        # 再次验证当前批次
        # ====================================================

        expected_ids = [article["id"] for article in batch]

        try:

            validate_ai_results(batch_results, expected_ids)

        except Exception as e:

            print("\n============================================================")
            print(f"Groq第{batch_index}批最终验证失败：{e}")
            print("不会使用任何不完整分析结果。")
            print("============================================================")

            return mark_analysis_failed(articles)

        all_batch_results.append(batch_results)

        print(f"第{batch_index}批分析成功：{len(batch_results)}条")

        # ====================================================
        # 批次间限速（最后一批之后不需要再等）
        # ====================================================

        if batch_index < total_batches:

            elapsed_seconds = time.time() - batch_start_time

            wait_for_rate_limit(usage_info["total_tokens"], elapsed_seconds)

    # ========================================================
    # 所有批次成功，开始合并
    # ========================================================

    print("\n============================================================")
    print("所有Groq批次均已成功完成")
    print("开始合并全部AI分析结果")
    print("============================================================")

    merged_results = merge_batch_results(all_batch_results)

    # ========================================================
    # 最终数量验证
    # ========================================================

    if len(merged_results) != len(articles):

        print("\n============================================================")
        print("Groq全部批次合并后数量错误")
        print(f"期望：{len(articles)}")
        print(f"实际：{len(merged_results)}")
        print("不会使用任何不完整分析结果。")
        print("============================================================")

        return mark_analysis_failed(articles)

    # ========================================================
    # 建立结果ID索引
    # ========================================================

    result_map = {}

    try:

        for item in merged_results:

            if not isinstance(item, dict):
                raise ValueError("最终结果中存在非对象")

            if "id" not in item:
                raise ValueError("最终结果缺少id")

            item_id = str(item["id"])

            if item_id in result_map:
                raise ValueError(f"发现重复全局ID：{item_id}")

            result_map[item_id] = item

    except Exception as e:

        print("\n============================================================")
        print(f"Groq最终结果ID验证失败：{e}")
        print("不会使用任何不完整分析结果。")
        print("============================================================")

        return mark_analysis_failed(articles)

    # ========================================================
    # 验证全部全局ID
    # ========================================================

    expected_global_ids = {str(i) for i in range(1, len(articles) + 1)}

    actual_global_ids = set(result_map.keys())

    if actual_global_ids != expected_global_ids:

        print("\n============================================================")
        print("Groq最终结果存在ID遗漏或增加")
        print(f"期望ID：{sorted(expected_global_ids)}")
        print(f"实际ID：{sorted(actual_global_ids)}")
        print("不会使用任何不完整分析结果。")
        print("============================================================")

        return mark_analysis_failed(articles)

    # ========================================================
    # 写回原始新闻
    #
    # category 默认值改为"公司、行业与研报"（3类体系下的
    # 兜底分类，正常情况不应触发——模型必须返回3类之一）。
    # ========================================================

    analyzed = []

    for index, original_article in enumerate(articles, 1):

        ai_result = result_map[str(index)]

        article = dict(original_article)

        article.update({
            "market_relevant": bool(ai_result.get("market_relevant", False)),
            "event_type": ai_result.get("event_type", ""),
            "category": ai_result.get("category", "公司、行业与研报"),
            "core_fact": ai_result.get("core_fact", ""),
            "market_impact_reason": ai_result.get("market_impact_reason", ""),
            "event_id": ai_result.get("event_id", ""),
            "impact_scope_level": ai_result.get("impact_scope_level", "limited"),
            "impact_degree_level": ai_result.get("impact_degree_level", "low"),
            "ai_analysis_failed": False
        })

        analyzed.append(article)

    # ========================================================
    # 输出分析结果
    # ========================================================

    for index, article in enumerate(analyzed, 1):

        print(f"[{index}/{len(analyzed)}] {article.get('title', '')}")
        print(f"  金融市场相关：{article.get('market_relevant')}")
        print(f"  分类：{article.get('category')}")
        print(f"  事件：{article.get('event_type')}")
        print(f"  影响范围：{article.get('impact_scope_level')}")
        print(f"  影响程度：{article.get('impact_degree_level')}")

    # ========================================================
    # 最终成功
    # ========================================================

    print("\n============================================================")
    print(f"Groq批量新闻分析完成：{len(analyzed)} 条")
    print(f"实际分析批次：{len(batches)} 批")
    print("AI调用方式：稳定小批量 + 动态Token + 免费额度限速")
    print("完整性检查：通过")
    print("不会使用不完整分析结果")
    print("============================================================")

    return analyzed


# ============================================================
# 单条新闻分析
# ============================================================

def analyze_news(article):

    results = analyze_news_list([article])

    if results:
        return results[0]

    return {"market_relevant": False, "ai_analysis_failed": True}


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":

    test_article = {
        "title": "Fed keeps interest rates unchanged",
        "summary": "The Federal Reserve kept interest rates unchanged.",
        "source": "CNBC Finance",
        "url": "https://example.com"
    }

    result = analyze_news(test_article)

    print("\n测试结果：")

    print(json.dumps(result, ensure_ascii=False, indent=4))
