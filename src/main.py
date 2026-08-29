from market_data import get_market_data


def format_number(value):
    """数字格式化：千分位 + 2位小数"""
    return f"{value:,.2f}"


def format_percent(value):
    """涨跌幅格式化：统一显示 + / -"""
    return f"{value:+.2f}%"


def print_market_table(market_data):
    """打印全球金融市场数据表格"""

    # ==============================
    # 固定列宽
    # ==============================
    name_width = 14
    date_width = 14
    number_width = 16
    percent_width = 12

    total_width = (
        name_width
        + date_width
        + number_width * 3
        + percent_width
    )

    # ==============================
    # 表格标题
    # ==============================
    print("\n" + "=" * total_width)

    title = "全球金融市场数据"
    print(title.center(total_width))

    print("=" * total_width)

    # ==============================
    # 表头
    # ==============================
    print(
        f"{'市场':<{name_width}}"
        f"{'日期':^{date_width}}"
        f"{'最高':^{number_width}}"
        f"{'最低':^{number_width}}"
        f"{'收盘':^{number_width}}"
        f"{'涨跌幅':^{percent_width}}"
    )

    print("-" * total_width)

    # ==============================
    # 数据行
    # ==============================
    for name, data in market_data.items():

        # 获取失败
        if data is None:
            print(
                f"{name:<{name_width}}"
                f"{'获取失败':^{total_width - name_width}}"
            )
            continue

        # ------------------------------
        # 日期
        # ------------------------------
        date = data.get("date", "-")

        # ------------------------------
        # 数值格式化
        # ------------------------------
        high = format_number(data["high"])
        low = format_number(data["low"])
        close = format_number(data["close"])
        change = format_percent(data["change_percent"])

        # ==============================
        # 输出
        #
        # 市场名称：左对齐
        # 日期：居中
        # 数值：右对齐
        # 涨跌幅：右对齐
        # ==============================
        print(
            f"{name:<{name_width}}"
            f"{date:^{date_width}}"
            f"{high:>{number_width}}"
            f"{low:>{number_width}}"
            f"{close:>{number_width}}"
            f"{change:>{percent_width}}"
        )

    print("=" * total_width)


def main():
    print("\nGlobal Market Agent")

    print("\n正在获取全球金融市场数据...")

    # 获取市场数据
    market_data = get_market_data()

    # 打印第二部分：全球市场总览
    print_market_table(market_data)


if __name__ == "__main__":
    main()

