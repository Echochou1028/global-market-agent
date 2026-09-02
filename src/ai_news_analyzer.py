import json
import os
import time

from openai import OpenAI


# ============================================================
# 全球金融市场日报
# ai_news_analyzer.py
#
# 稳定版 v2.1 (具备 429 TPD 限流降级与部分保存能力)
#
# 改动说明：
# 1. 批次处理遇到 Groq TPD（每日 Token 限制）429 报错时，
#    自动中断后续批次，但保留并合并前面已成功分析的批次数据。
# 2. 未能完成 AI 分析的新闻将被标记为失败，不会导致整个程序返回 0 条。
# ============================================================


# ============================================================
# Groq 模型
# ============================================================

GROQ_MODEL = "openai/gpt-oss-120b"


# ============================================================
# 批次控制
# ============================================================

MAX_ARTICLES_PER_BATCH = 5


# ============================================================
# Token控制
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
# ============================================================

def estimate_tokens(text):
    if not text:
        return 0
    text = str(text)
    chinese_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
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

    if len(
