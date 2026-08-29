from market_data import get_market_data


def format_number(value):
    """数字格式化：千分位 + 2位小数"""
    return f"{value:,.2f}"


def format_percent(value):
    """涨跌幅格式化"""
    return f"{value:+.2f}%"


def print_market_table(market_data):
    """打印全球金融市场数据表格"""

    print("\n" + "=" * 76)
    print("                         全球金融市场数据")
    print("=" * 76)

    # 表头
    print(
        f"{'市场':^14}"
        f"{'最高':^15}"
        f"{'最低':^15}"
        f"{'收盘':^15}"
        f"{'涨跌幅':^11}"
    )

    print("-" * 76)

    for name, data in market_data.items():

        if data is None:
            print(f"{name:<14}{'获取失败':^56}")
            continue

        high = format_number(data["high"])
        low = format_number(data["low"])
        close = format_number(data["close"])
        change = format_percent(data["change_percent"])

        print(
            f"{name:^14}"
            f"{high:>15}"
            f"{low:>15}"
            f"{close:>15}"
            f"{change:>11}"
        )

    print("=" * 76)


def main():
    print("\nGlobal Market Agent\n")

    print("正在获取全球金融市场数据...")

    market_data = get_market_data()

    print_market_table(market_data)


if __name__ == "__main__":
    main()
