import json
import os
import time
from openai import OpenAI


# ============================================================
# 全球金融市场日报
# ai_news_analyzer.py
#
# 稳定版 v4
#
# 本版改动（相对 v3.1）：
#
# 1. MODEL_FALLBACK 从5个通道精简为2个：
#
#    openai/gpt-oss-120b（主力） → openai/gpt-oss-20b（备用）
#
#    删掉的4个（llama-3.3-70b-versatile / llama-3.1-8b-instant /
#    mixtral-8x7b-32768 / deepseek-r1-distill-llama-70b）
#    在Groq上已经全部弃用/下线，之前每次熔断都要先陪它们
#    404/400空转一遍，才能走到真正有效的模型，纯粹浪费时间。
#
#    openai/gpt-oss-120b 和 openai/gpt-oss-20b 是两个独立模型，
#    各自有独立的每日Token额度（TPD），互不共享——
#    这是当前唯一真正有意义的备用通道。
#
#    是否要接入 Gemini 作为第三重兜底：暂时不加，
#    详见本次对话里的说明，等两个Groq模型真的在生产环境里
#    出现过同一天都不够用的情况，再考虑加。
#
# 2. 恢复"不使用任何不完整分析结果"的严格原则：
#
#    只要有一个批次两个模型都失败，整次AI分析立即判定失败，
#    不再"保留已成功批次、继续往下跑"——
#    那种做法会让日报在完全不提示的情况下，
#    只覆盖当天一小部分新闻，这是本版明确要修掉的行为。
#
# 3. 批量大小、Token预算、限速逻辑维持v3.1的数值不变——
#    这些在实际运行日志里已经验证有效（10条/批，
#    finish_reason全部是stop，没有出现截断），没有理由重调。
# ============================================================


# ============================================================
# Groq 模型 fallback 顺序
#
# 只保留Groq上真实存在、当前仍受支持的模型。
# 两者是独立模型，独立的TPM/TPD额度池，
# 主力额度耗尽时切到备用是真正有效的容灾，
# 不是在空转不存在的模型。
# ============================================================

MODEL_FALLBACK = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
]


# ============================================================
# 批次与Token控制
#
# 数值沿用v3.1——实际运行日志显示10条/批 + 这版精简后的
# SYSTEM_PROMPT，finish_reason全部是stop，没有截断，
# 没必要重新调整。
# ============================================================

MAX_ARTICLES_PER_BATCH = 10
TOKEN_SAFETY_LIMIT = 7500
OUTPUT_TOKENS_PER_ARTICLE = 220
MIN_OUTPUT_TOKEN_RESERVE = 1200
MAX_OUTPUT_TOKEN_RESERVE = 2500

MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 2

GROQ_TPM_LIMIT = 8000
# 已知事件清单会让批次越往后input token越多（最后几批可能比
# 最初几批多出1000-2000+ token），加上上次实测15批里有5批已经
# 撞了TPM——1.1的余量偏紧，上调到1.4留出更多缓冲。
# 就算撞了限流也有gpt-oss-20b兜底，不是致命的，
# 但余量更大能减少不必要的429和重试次数。
RATE_LIMIT_SAFETY_FACTOR = 1.4
MIN_BATCH_INTERVAL_SECONDS = 10


# ============================================================
# 初始化 Groq 客户端
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

SYSTEM_PROMPT = """你是一个金融市场新闻分析引擎。
任务：分析输入的新闻，提取关键市场信息，判断其对金融市场的实际影响。

【判断标准】
1. market_relevant (boolean): 是否对股市、债市、外汇、大宗商品、加密货币、重要宏观/行业具有实际金融市场影响。娱乐/社会/无市场价值的新闻设为 false。
2. category (string): 只能属于以下三类之一：
   - 宏观、政策与地缘 (央行/利率/通胀/就业/GDP/关税/地缘政治)
   - 市场与资产 (股市大盘/大宗商品/外汇/虚拟货币剧烈波动)
   - 公司、行业与研报 (重要财报/并购/科技半导体AI产业/重磅研报)
3. core_fact (string): 严谨客观总结输入新闻中的核心事实，禁止编造。
4. market_impact_reason (string): 说明为何影响市场。
5. event_id (string): 简短的核心事件统一标识符，用于归并同类报道。如果本次请求提供了"已知事件清单"，且这批新闻里有描述同一事件的报道，必须复用清单里给出的event_id，禁止为同一事件重新生成新的event_id；只有确认是清单里没有的全新事件时，才创建新的event_id。
6. impact_scope_level (string): global / multi_region / regional / country / industry / company / limited
7. impact_degree_level (string): very_high / high / medium / low

【输出格式】
必须严格输出合法 JSON 格式对象，不要输出任何 Markdown 标记或额外说明：
{
  "results": [
    {
      "id": 1,
      "market_relevant": true,
      "event_type": "事件类型简述",
      "category": "分类",
      "core_fact": "核心事实简述",
      "market_impact_reason": "影响逻辑",
      "event_id": "event_identifier",
      "impact_scope_level": "global",
      "impact_degree_level": "high"
    }
  ]
}
"""


def estimate_tokens(text):
    if not text:
        return 0
    text = str(text)
    chinese_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    other_count = len(text) - chinese_count
    return int(chinese_count / 1.5 + other_count / 4)


def estimate_article_tokens(article):
    return estimate_tokens(json.dumps(article, ensure_ascii=False))


def calculate_output_tokens(article_count):
    dynamic_tokens = article_count * OUTPUT_TOKENS_PER_ARTICLE
    dynamic_tokens = max(dynamic_tokens, MIN_OUTPUT_TOKEN_RESERVE)
    return min(dynamic_tokens, MAX_OUTPUT_TOKEN_RESERVE)


def estimate_batch_tokens(articles, known_events=None):
    prompt_overhead = estimate_tokens(SYSTEM_PROMPT) + 300
    known_events_tokens = 0
    if known_events:
        known_events_tokens = estimate_tokens(json.dumps(known_events, ensure_ascii=False))
    input_tokens = prompt_overhead + known_events_tokens + sum(estimate_article_tokens(a) for a in articles)
    output_tokens = calculate_output_tokens(len(articles))
    return input_tokens, output_tokens, input_tokens + output_tokens


def build_batches(articles):
    batches = []
    current_batch = []
    for article in articles:
        candidate = current_batch + [article]
        _, _, total_tokens = estimate_batch_tokens(candidate)
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


def build_batch_prompt(articles, known_events=None):
    articles_json = json.dumps(articles, ensure_ascii=False)
    count = len(articles)

    known_events_section = ""
    if known_events:
        known_events_json = json.dumps(known_events, ensure_ascii=False)
        known_events_section = (
            f"\n\n已知事件清单（今天已经识别过的事件，如果本批新闻里有属于"
            f"以下某个事件的报道，必须复用对应的event_id，不要新起一个）：\n\n"
            f"{known_events_json}"
        )

    return (
        f"请分析以下全部 {count} 条新闻，返回包含全部 {count} 条结果的 JSON 对象："
        f"\n\n{articles_json}"
        f"{known_events_section}"
    )


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


def extract_results(result):
    if not isinstance(result, dict):
        return None
    for key in ("results", "articles", "data"):
        value = result.get(key)
        if isinstance(value, list):
            return value
    return None


def validate_ai_results(results, expected_ids):
    if not isinstance(results, list) or len(results) != len(expected_ids):
        raise ValueError(
            f"返回数量错误：期望 {len(expected_ids)} 条，"
            f"实际 {len(results) if isinstance(results, list) else 0} 条"
        )

    actual_ids = {
        str(item.get("id"))
        for item in results
        if isinstance(item, dict) and "id" in item
    }
    expected_id_set = {str(x) for x in expected_ids}
    if actual_ids != expected_id_set:
        raise ValueError(
            f"返回ID不完整：期望={sorted(expected_id_set)}, 实际={sorted(actual_ids)}"
        )
    return True


def execute_chat_completion(client, model_name, messages, max_tokens):
    kwargs = {
        "model": model_name,
        "messages": messages,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": max_tokens
    }
    if "gpt-oss" in model_name:
        kwargs["reasoning_effort"] = "low"

    return client.chat.completions.create(**kwargs)


# ============================================================
# 单批请求（带模型fallback）
#
# 429（限流）/ 404（模型不存在）/ 400+decommissioned（模型下线）
# 立即熔断切换下一个模型，不在明知必挂的模型上浪费重试次数。
#
# 其余异常（解析失败、截断等）在同一个模型上重试
# MAX_RETRIES 次，仍失败才切下一个模型。
#
# 两个模型都失败 → 抛异常，交给上层判定整次分析失败。
# ============================================================

def request_batch_with_fallback(client, articles, batch_number, known_events=None):

    # ========================================================
    # 批内本地编号
    #
    # 不管这批文章在全局id里是第几号（比如121-130），
    # 发给AI的时候永远从1开始编号，拿到结果后再换算回
    # 真实的全局id。
    #
    # 起因：openai/gpt-oss-20b处理"起始编号不是1"的批次时，
    # 出现过擅自把id重新编号成1..N的情况（两次重试结果一致，
    # 是系统性行为，不是偶然），导致返回id跟预期对不上，
    # 整批判定失败。用本地编号1..N提问，结果再换算回全局id，
    # 从根上绕开这个问题——不用赌模型会不会乖乖遵守
    # "必须保留原id"这条指令。
    # ========================================================

    local_to_global_id = {}
    local_articles = []

    for local_id, article in enumerate(articles, 1):
        local_to_global_id[local_id] = article["id"]
        local_article = dict(article)
        local_article["id"] = local_id
        local_articles.append(local_article)

    prompt = build_batch_prompt(local_articles, known_events)
    expected_local_ids = list(range(1, len(articles) + 1))
    _, output_tokens, total_tokens = estimate_batch_tokens(local_articles, known_events)
    last_error = None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]

    for model_name in MODEL_FALLBACK:

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"批次 [{batch_number}] -> 尝试模型【{model_name}】(第{attempt}次)")
            try:
                response = execute_chat_completion(client, model_name, messages, output_tokens)

                finish_reason = response.choices[0].finish_reason
                usage = response.usage
                usage_total_tokens = usage.total_tokens if usage else total_tokens

                if finish_reason == "length":
                    raise ValueError("输出截断 (finish_reason=length)")

                raw_content = response.choices[0].message.content
                if not raw_content:
                    raise ValueError("返回内容为空")

                parsed = json.loads(clean_json_text(raw_content))
                results = extract_results(parsed)
                if results is None:
                    raise ValueError("未找到 results 数组")

                validate_ai_results(results, expected_local_ids)

                # 换算回全局id，让下游合并逻辑不用感知本地编号这层
                for item in results:
                    if isinstance(item, dict) and "id" in item:
                        try:
                            local_id = int(item["id"])
                        except (TypeError, ValueError):
                            local_id = None
                        if local_id in local_to_global_id:
                            item["id"] = local_to_global_id[local_id]

                if usage:
                    print(
                        f"Token消耗: 输入 {usage.prompt_tokens} + "
                        f"输出 {usage.completion_tokens} = {usage.total_tokens}"
                    )
                return results, usage_total_tokens

            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                print(f"模型【{model_name}】请求失败: {e}")

                # 429/rate_limit：额度耗尽 / 404/model_not_found：模型不存在
                # / decommissioned：模型已下线 —— 这几种是模型本身不可用，
                # 立即切下一个模型，不浪费剩余重试次数。
                #
                # 注意：不能用裸的"400"做判断——模型偶发生成的JSON
                # 格式错误（json_validate_failed）也是400，但这是随机的
                # 一次性抖动，不是模型不可用，应该在同一模型上重试，
                # 而不是直接放弃这个模型切去更弱的备用模型。
                if any(
                    k in err_str
                    for k in ["429", "rate_limit", "404", "model_not_found", "decommissioned"]
                ):
                    print("【模型熔断】检测到不可用或被限流，立即切换下一模型...")
                    break

                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(f"批次[{batch_number}]所有备选模型均请求失败，最后错误: {last_error}")


def wait_for_rate_limit(total_tokens_used, elapsed_seconds):
    target_seconds = total_tokens_used / GROQ_TPM_LIMIT * 60 * RATE_LIMIT_SAFETY_FACTOR
    target_seconds = max(target_seconds, MIN_BATCH_INTERVAL_SECONDS)
    sleep_seconds = target_seconds - elapsed_seconds

    if sleep_seconds > 0:
        print(f"限速冷却：等待 {sleep_seconds:.1f} 秒 (消耗 Token: {total_tokens_used})...")
        time.sleep(sleep_seconds)


# ============================================================
# 分析失败时的兜底标记
#
# 严格模式下，只要有一批彻底失败，整次分析全部标记失败——
# 不使用任何不完整的分析结果。
# 下游 news_scoring.py 会因为 market_relevant=False
# 自动把这些新闻全部过滤掉，news_data.py 会走到
# "数据缺失/获取失败"的分支，而不是悄悄发一份不完整的日报。
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
# 批量分析新闻
# ============================================================

def analyze_news_list(articles):
    if not articles:
        return []

    print("\n============================================================")
    print(f"启动 AI 批量新闻事件分析 (待处理新闻: {len(articles)} 条)")
    print(f"批次容量: {MAX_ARTICLES_PER_BATCH} 条/批 | 模型fallback: {' -> '.join(MODEL_FALLBACK)}")
    print("失败模式：严格（任意批次最终失败 → 整次分析全部作废）")
    print("============================================================")

    client = get_client()

    prepared_articles = []
    for idx, item in enumerate(articles, 1):
        prepared_articles.append({
            "id": idx,
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
            "url": item.get("url", "")
        })

    batches = build_batches(prepared_articles)
    total_batches = len(batches)
    print(f"自动切分批次：共 {total_batches} 批\n")

    all_batch_results = []

    # ========================================================
    # 跨批次已知事件清单
    #
    # 每处理完一批，把这批新识别出的事件（event_id + 简短
    # event_type）加进这个清单，后续批次的prompt都会带上它，
    # 让AI在遇到同一事件的不同报道时复用已有event_id，
    # 而不是每批各起各的、导致同一事件在最终日报里重复出现。
    # ========================================================

    known_events = []
    seen_event_ids = set()

    for batch_index, batch in enumerate(batches, 1):
        print(f"--- 处理批次 [{batch_index}/{total_batches}] (包含 {len(batch)} 条新闻) ---")
        batch_start_time = time.time()

        try:
            batch_results, used_tokens = request_batch_with_fallback(
                client, batch, batch_index, known_events
            )
            all_batch_results.append(batch_results)
            print(f"批次 [{batch_index}] 分析成功 ({len(batch_results)} 条)")

            # 把这批新出现的事件登记进已知事件清单，供后续批次复用
            for item in batch_results:
                if not isinstance(item, dict):
                    continue
                eid = item.get("event_id")
                if eid and eid not in seen_event_ids:
                    seen_event_ids.add(eid)
                    known_events.append({
                        "event_id": eid,
                        "event_type": item.get("event_type", "")[:60]
                    })

            if batch_index < total_batches:
                elapsed = time.time() - batch_start_time
                wait_for_rate_limit(used_tokens, elapsed)

        except Exception as e:

            print(f"\n【批次失败】第 {batch_index}/{total_batches} 批处理异常: {e}")
            print(
                f"严格模式：不使用任何不完整分析结果，"
                f"本次AI分析整体判定失败（此前已成功 {len(all_batch_results)} 批也一并作废）"
            )
            print("============================================================\n")

            return mark_analysis_failed(articles)

    # ========================================================
    # 走到这里说明全部批次都成功了。
    #
    # 严格模式下这已经隐含"数量必然对得上"，
    # 但仍然显式核对一次，作为最后一道防线——
    # 万一某个批次的validate_ai_results有遗漏，
    # 这里能兜底发现，而不是让脏数据流到下游。
    # ========================================================

    merged_results = []
    for sublist in all_batch_results:
        if isinstance(sublist, list):
            merged_results.extend(sublist)

    if len(merged_results) != len(prepared_articles):
        print("\n============================================================")
        print("全部批次均已成功，但合并后数量校验未通过（不应该发生）")
        print(f"期望：{len(prepared_articles)}，实际：{len(merged_results)}")
        print("严格模式：不使用任何不完整分析结果")
        print("============================================================\n")
        return mark_analysis_failed(articles)

    result_map = {
        str(item["id"]): item
        for item in merged_results
        if isinstance(item, dict) and "id" in item
    }

    expected_global_ids = {str(i) for i in range(1, len(articles) + 1)}

    if set(result_map.keys()) != expected_global_ids:
        print("\n============================================================")
        print("全部批次均已成功，但最终ID校验未通过（不应该发生）")
        print("严格模式：不使用任何不完整分析结果")
        print("============================================================\n")
        return mark_analysis_failed(articles)

    analyzed = []

    for idx, original_article in enumerate(articles, 1):
        ai_data = result_map[str(idx)]
        article = dict(original_article)
        article.update({
            "market_relevant": bool(ai_data.get("market_relevant", False)),
            "event_type": ai_data.get("event_type", ""),
            "category": ai_data.get("category", "公司、行业与研报"),
            "core_fact": ai_data.get("core_fact", article.get("summary", "")),
            "market_impact_reason": ai_data.get("market_impact_reason", ""),
            "event_id": ai_data.get("event_id", ""),
            "impact_scope_level": ai_data.get("impact_scope_level", "limited"),
            "impact_degree_level": ai_data.get("impact_degree_level", "low"),
            "ai_analysis_failed": False
        })
        analyzed.append(article)

    print("\n============================================================")
    print(f"AI 分析任务全部完成：{len(analyzed)} 条，全部成功，无不完整数据")
    print("============================================================\n")

    return analyzed


def analyze_news(article):
    results = analyze_news_list([article])
    return results[0] if results else {"market_relevant": False, "ai_analysis_failed": True}
