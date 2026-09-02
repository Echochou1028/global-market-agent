import json
import os
import time
from openai import OpenAI

# ============================================================
# 全球金融市场日报
# ai_news_analyzer.py
#
# 稳定版 v3.1 (已修复 Groq 模型弃用与权限 404/400 问题)
# ============================================================

# 最新确认有效的 Groq 免费模型序列
MODEL_FALLBACK_PIPELINE = [
    {"provider": "groq", "model": "openai/gpt-oss-120b"},
    {"provider": "groq", "model": "llama-3.3-70b-versatile"},
    {"provider": "groq", "model": "llama-3.1-8b-instant"},
    {"provider": "groq", "model": "mixtral-8x7b-32768"},
    {"provider": "groq", "model": "deepseek-r1-distill-llama-70b"},
    # 若在 GitHub Secrets 配置 GEMINI_API_KEY，可实现无限量容灾
    {"provider": "gemini", "model": "gemini-1.5-flash"}
]

# ============================================================
# 批次与Token控制
# ============================================================

MAX_ARTICLES_PER_BATCH = 10
TOKEN_SAFETY_LIMIT = 7500
OUTPUT_TOKENS_PER_ARTICLE = 220
MIN_OUTPUT_TOKEN_RESERVE = 1200
MAX_OUTPUT_TOKEN_RESERVE = 2500

MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 2
GROQ_TPM_LIMIT = 8000
RATE_LIMIT_SAFETY_FACTOR = 1.1
MIN_BATCH_INTERVAL_SECONDS = 10


def get_client_for_provider(provider):
    if provider == "groq":
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return None
        return OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1"
        )
    elif provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return None
        return OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    return None


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
5. event_id (string): 简短的核心事件统一标识符，用于归并同类报道。
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


def estimate_batch_tokens(articles):
    prompt_overhead = estimate_tokens(SYSTEM_PROMPT) + 300
    input_tokens = prompt_overhead + sum(estimate_article_tokens(a) for a in articles)
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


def build_batch_prompt(articles):
    articles_json = json.dumps(articles, ensure_ascii=False)
    count = len(articles)
    return f"请分析以下全部 {count} 条新闻，返回包含全部 {count} 条结果的 JSON 对象：\n\n{articles_json}"


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
        raise ValueError(f"返回数量错误：期望 {len(expected_ids)} 条，实际 {len(results) if isinstance(results, list) else 0} 条")

    actual_ids = {str(item.get("id")) for item in results if isinstance(item, dict) and "id" in item}
    expected_id_set = {str(x) for x in expected_ids}
    if actual_ids != expected_id_set:
        raise ValueError(f"返回ID不完整：期望={sorted(expected_id_set)}, 实际={sorted(actual_ids)}")
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


def request_batch_with_fallback(articles, batch_number):
    prompt = build_batch_prompt(articles)
    expected_ids = [article["id"] for article in articles]
    _, output_tokens, total_tokens = estimate_batch_tokens(articles)
    last_error = None

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]

    for model_cfg in MODEL_FALLBACK_PIPELINE:
        provider = model_cfg["provider"]
        model_name = model_cfg["model"]
        client = get_client_for_provider(provider)

        if not client:
            continue

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"批次 [{batch_number}] -> 尝试通道【{provider.upper()} : {model_name}】(第{attempt}次)")
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

                validate_ai_results(results, expected_ids)
                
                if usage:
                    print(f"Token消耗: 输入 {usage.prompt_tokens} + 输出 {usage.completion_tokens} = {usage.total_tokens}")
                return results, usage_total_tokens

            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                print(f"通道【{model_name}】请求失败: {e}")

                # 429(限流)、404(未找到)、400(废弃) 立即熔断切换下一模型，不再死循环重试
                if any(k in err_str for k in ["429", "rate_limit", "404", "model_not_found", "400", "decommissioned"]):
                    print(f"【通道熔断】检测到不可用或被限流，立即切换下一备用模型...")
                    break

                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(f"所有备选通道均请求失败。最后错误: {last_error}")


def wait_for_rate_limit(total_tokens_used, elapsed_seconds):
    target_seconds = (total_tokens_used / GROQ_TPM_LIMIT * 60 * RATE_LIMIT_SAFETY_FACTOR)
    target_seconds = max(target_seconds, MIN_BATCH_INTERVAL_SECONDS)
    sleep_seconds = target_seconds - elapsed_seconds

    if sleep_seconds > 0:
        print(f"限速冷却：等待 {sleep_seconds:.1f} 秒 (消耗 Token: {total_tokens_used})...")
        time.sleep(sleep_seconds)


def analyze_news_list(articles):
    if not articles:
        return []

    print("\n============================================================")
    print(f"启动 AI 批量新闻事件分析 (待处理新闻: {len(articles)} 条)")
    print(f"批次容量: {MAX_ARTICLES_PER_BATCH} 条/批 | 容灾通道数: {len(MODEL_FALLBACK_PIPELINE)}")
    print("============================================================")

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
    print(f"自动切分优化批次：共 {total_batches} 批\n")

    all_batch_results = []

    for batch_index, batch in enumerate(batches, 1):
        print(f"--- 处理批次 [{batch_index}/{total_batches}] (包含 {len(batch)} 条新闻) ---")
        batch_start_time = time.time()

        try:
            batch_results, used_tokens = request_batch_with_fallback(batch, batch_index)
            all_batch_results.append(batch_results)
            print(f"批次 [{batch_index}] 分析成功 ({len(batch_results)} 条)")

            if batch_index < total_batches:
                elapsed = time.time() - batch_start_time
                wait_for_rate_limit(used_tokens, elapsed)

        except Exception as e:
            print(f"\n【批次中断警告】第 {batch_index} 批处理异常: {e}")
            print(f"保留此前已完成的 {len(all_batch_results)} 批数据继续执行...")
            break

    merged_results = []
    for sublist in all_batch_results:
        if isinstance(sublist, list):
            merged_results.extend(sublist)

    result_map = {str(item["id"]): item for item in merged_results if isinstance(item, dict) and "id" in item}

    analyzed = []
    success_count = 0

    for idx, original_article in enumerate(articles, 1):
        str_id = str(idx)
        article = dict(original_article)

        if str_id in result_map:
            ai_data = result_map[str_id]
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
            success_count += 1
        else:
            article.update({
                "market_relevant": False,
                "event_type": "",
                "category": "公司、行业与研报",
                "core_fact": article.get("summary", ""),
                "market_impact_reason": "",
                "event_id": "",
                "impact_scope_level": "limited",
                "impact_degree_level": "low",
                "ai_analysis_failed": True
            })
        analyzed.append(article)

    print("\n============================================================")
    print(f"AI 分析任务全部结束: 原始共 {len(analyzed)} 条，成功分析 {success_count} 条")
    print("============================================================\n")

    return analyzed


def analyze_news(article):
    results = analyze_news_list([article])
    return results[0] if results else {"market_relevant": False, "ai_analysis_failed": True}
