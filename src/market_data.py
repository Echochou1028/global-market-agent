import yfinance as yf


MARKETS = {
    "标普500": "^GSPC",
    "纳斯达克": "^IXIC",
    "道琼斯": "^DJI",
    "日经225": "^N225",
    "恒生指数": "^HSI",
    "上证指数": "000001.SS",
    "深证成指": "399001.SZ",
    "黄金": "GC=F",
    "原油": "CL=F",
    "美元指数": "DX-Y.NYB",
}


def get_market_data():
    results = {}

    for name, symbol in MARKETS.items():
        try:
            data = yf.Ticker(symbol).history(period="2d")

            if data.empty:
                results[name] = None
                continue

            latest = data.iloc[-1]

            close = float(latest["Close"])

            if len(data) >= 2:
                previous = float(data.iloc[-2]["Close"])
                change = (close - previous) / previous * 100
            else:
                change = 0

            results[name] = {
                "price": close,
                "change_percent": change,
            }

        except Exception as e:
            print(f"{name} 获取失败: {e}")
            results[name] = None

    return results


if __name__ == "__main__":
    market_data = get_market_data()

    print("\n========== 全球金融市场 ==========\n")

    for name, data in market_data.items():
        if data is None:
            print(f"{name}: 获取失败")
        else:
            print(
                f"{name}: "
                f"{data['price']:.2f} "
                f"({data['change_percent']:+.2f}%)"
            )
