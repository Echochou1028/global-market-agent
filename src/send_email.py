import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# ============================================================
# 全球金融市场日报
# send_email.py
#
# 职责：把 news_data.py 已经算好的最终新闻列表，格式化成HTML
# 邮件并发送出去。
#
# 重要：本文件不重新调用 get_news_data()，不重新跑一遍AI分析——
# 那一整套流程很贵（十几批Groq请求，几十秒到几分钟），
# 只应该在一次运行里跑一次。news_data.py的__main__算完
# news之后直接把结果传进来，这里只负责"排版+发送"。
# ============================================================


CATEGORY_ORDER = ["宏观、政策与地缘", "市场与资产", "公司、行业与研报"]


def build_html_report(news):

    china_tz = timezone(timedelta(hours=8))

    today_str = datetime.now(timezone.utc).astimezone(china_tz).strftime("%Y年%m月%d日")

    if not news:

        return f"""
        <html><body style="font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif;">
        <h2>全球金融市场日报 - {today_str}</h2>
        <p>今日未获取到有效的市场相关新闻（数据源异常，或AI分析失败被严格模式整体作废）。</p>
        </body></html>
        """

    grouped = {cat: [] for cat in CATEGORY_ORDER}

    for article in news:

        cat = article.get("category", "公司、行业与研报")

        if cat not in grouped:
            grouped[cat] = []

        grouped[cat].append(article)

    html_parts = [f"""
    <html><body style="font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; color:#222; max-width:720px; margin:0 auto;">
    <h2 style="border-bottom:2px solid #333; padding-bottom:8px;">全球金融市场日报 - {today_str}</h2>
    <p style="color:#666; font-size:13px;">共 {len(news)} 条新闻</p>
    """]

    for cat in CATEGORY_ORDER:

        items = grouped.get(cat, [])

        if not items:
            continue

        html_parts.append(
            f'<h3 style="color:#1a5276; margin-top:28px; '
            f'border-bottom:1px solid #ccc; padding-bottom:4px;">'
            f'【{cat}】（{len(items)}条）</h3>'
        )

        for i, article in enumerate(items, 1):

            title = article.get("title_zh") or article.get("title", "")
            core_fact = article.get("core_fact", "")
            reason = article.get("market_impact_reason", "")
            source = article.get("source", "未知来源")
            published = article.get("published", "时间缺失")
            url = article.get("url", "")
            score = article.get("score", 0)

            html_parts.append(f"""
            <div style="margin-bottom:16px; padding-bottom:12px; border-bottom:1px solid #eee;">
                <div style="font-weight:600; font-size:15px;">{i}. {title}</div>
                <div style="color:#444; font-size:13px; margin:4px 0;">{core_fact}</div>
                <div style="color:#777; font-size:12px;">影响逻辑：{reason}</div>
                <div style="color:#999; font-size:11px; margin-top:4px;">
                    来源：{source} ｜ 时间：{published} ｜ 综合得分：{score}
                    ｜ <a href="{url}" style="color:#2980b9;">原文链接</a>
                </div>
            </div>
            """)

    html_parts.append("</body></html>")

    return "".join(html_parts)


def send_report_email(news):

    # ========================================================
    # 从环境变量读取SMTP配置（对应GitHub Secrets）：
    #
    # SMTP_HOST      默认 smtp.gmail.com
    # SMTP_PORT      默认 465（SSL）
    # SMTP_USERNAME  发信/收信账号（同一个Gmail邮箱收发时，
    #                这个值跟 SMTP_TO 一样）
    # SMTP_PASSWORD  Gmail的"应用专用密码"（App Password，
    #                16位，不是登录密码——需要先在Google账号
    #                开启两步验证，再去生成）
    # SMTP_TO        收信地址（同一个Gmail邮箱收发时，
    #                这个值跟 SMTP_USERNAME 一样）
    # ========================================================

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_to = os.getenv("SMTP_TO")

    if not smtp_username or not smtp_password or not smtp_to:

        print(
            "\n未配置 SMTP_USERNAME / SMTP_PASSWORD / SMTP_TO，"
            "跳过邮件发送（本地测试或未设置GitHub Secrets时属正常现象）"
        )

        return

    china_tz = timezone(timedelta(hours=8))

    today_str = datetime.now(timezone.utc).astimezone(china_tz).strftime("%Y-%m-%d")

    msg = MIMEMultipart("alternative")

    msg["Subject"] = f"全球金融市场日报 {today_str}（共{len(news)}条）"
    msg["From"] = smtp_username
    msg["To"] = smtp_to

    html_body = build_html_report(news)

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    print(f"\n正在通过 {smtp_host}:{smtp_port} 发送邮件至 {smtp_to} ...")

    try:

        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:

            server.login(smtp_username, smtp_password)

            server.sendmail(smtp_username, [smtp_to], msg.as_string())

        print("邮件发送成功")

    except Exception as e:

        print(f"邮件发送失败：{e}")

        # 发送失败要让整个工作流显式报错（GitHub Actions里显示红叉），
        # 而不是悄悄吞掉——不然日报没发出去，你也不会知道。
        raise
