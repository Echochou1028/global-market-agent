from market_data import get_market_data


def main():
    print("========================================")
    print("       Global Market Agent")
    print("========================================")

    market_data = get_market_data()

    print("\n全球金融市场数据：\n")

    for name, data in market_data.items():
        if data is None:
            print(f"{name}: 获取失败")
        else:
            print(
                f"{name}: "
                f"{data['price']:.2f} "
                f"({data['change_percent']:+.2f}%)"
            )


if __name__ == "__main__":
    main()
