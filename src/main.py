from market_data import get_market_data


def main():
    print("Global Market Agent")
    market_data = get_market_data()
    print(market_data)


if __name__ == "__main__":
    main()
