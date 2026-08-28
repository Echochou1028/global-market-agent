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

            # 最新交易日数据
            latest = data.iloc[-1]

            high = float(latest["High"])
            low = float(latest["Low"])
            close = float(latest["Close"])

            # 昨日收盘价
            if len(data) >= 2:
                previous_close = float(data.iloc[-2]["Close"])
                change = (
                    (close - previous_close)
                    / previous_close
                    * 100
                )
            else:
                previous_close = close
                change = 0

            results[name] = {
                "high": high,
                "low": low,
                "close": close,
                "previous_close": previous_close,
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
                f"最高 {data['high']:.2f} | "
                f"最低 {data['low']:.2f} | "
                f"收盘 {data['close']:.2f} | "
                f"昨收 {data['previous_close']:.2f} | "
                f"涨跌幅 {data['change_percent']:+.2f}%"
            )
