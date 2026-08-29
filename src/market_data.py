import yfinance as yf
import pandas as pd


MARKETS = {
    "标普500": "^GSPC",
    "纳斯达克": "^IXIC",
    "道琼斯": "^DJI",
    "韩国KOSPI": "^KS11",
    "日经225": "^N225",
    "恒生指数": "^HSI",
    "恒生科技指数": "HSTECH.HK",
    "上证指数": "000001.SS",
    "深证成指": "399001.SZ",
    "黄金": "GC=F",
    "布伦特原油": "BZ=F",
    "美元指数": "DX-Y.NYB",
    "VIX指数": "^VIX",
}


def get_market_data():
    results = {}

    for name, symbol in MARKETS.items():
        try:
            data = yf.Ticker(symbol).history(period="5d")

            if data.empty:
                print(f"{name}：没有获取到数据")
                results[name] = None
                continue

            # 删除 OHLC 全部缺失的行
            data = data.dropna(
                subset=["High", "Low", "Close"],
                how="all"
            )

            if data.empty:
                print(f"{name}：没有有效行情数据")
                results[name] = None
                continue

            # 找到最近一条有效交易数据
            latest = data.iloc[-1]

            high = latest["High"]
            low = latest["Low"]
            close = latest["Close"]

            # 检查核心字段是否有效
            if (
                pd.isna(high)
                or pd.isna(low)
                or pd.isna(close)
            ):
                print(f"{name}：最新行情数据缺失")
                results[name] = None
                continue

            # 找到上一条有效收盘价
            valid_close = data["Close"].dropna()

            if len(valid_close) >= 2:
                previous_close = float(valid_close.iloc[-2])
            else:
                previous_close = float(close)

            high = float(high)
            low = float(low)
            close = float(close)

            if previous_close != 0:
                change = (
                    (close - previous_close)
                    / previous_close
                    * 100
                )
            else:
                change = 0.0

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
