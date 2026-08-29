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
            # 多取几天，避免周末、节假日导致历史数据不足
            data = yf.Ticker(symbol).history(
                period="10d"
            )

            if data.empty:
                print(f"{name}：没有获取到数据")
                results[name] = None
                continue

            # ==================================================
            # 只保留 OHLC 完整的交易日
            # ==================================================

            required_columns = [
                "Open",
                "High",
                "Low",
                "Close",
            ]

            data = data.dropna(
                subset=required_columns,
                how="any"
            )

            if data.empty:
                print(f"{name}：没有完整行情数据")
                results[name] = None
                continue

            # ==================================================
            # 最近一个完整交易日
            # ==================================================

            latest = data.iloc[-1]

            high = float(latest["High"])
            low = float(latest["Low"])
            close = float(latest["Close"])

            # ==================================================
            # 上一个完整交易日
            # ==================================================

            if len(data) >= 2:

                previous = data.iloc[-2]

                previous_close = float(
                    previous["Close"]
                )

            else:

                previous_close = close

            # ==================================================
            # 计算涨跌幅
            # ==================================================

            if previous_close != 0:

                change = (
                    (close - previous_close)
                    / previous_close
                    * 100
                )

            else:

                change = 0.0

            # ==================================================
            # 获取数据日期
            # ==================================================

            latest_date = data.index[-1]

            if hasattr(
                latest_date,
                "date"
            ):

                data_date = str(
                    latest_date.date()
                )

            else:

                data_date = str(
                    latest_date
                )

            # ==================================================
            # 保存结果
            # ==================================================

            results[name] = {

                "date": data_date,

                "high": high,

                "low": low,

                "close": close,

                "previous_close":
                    previous_close,

                "change_percent":
                    change,

            }

        except Exception as e:

            print(
                f"{name} 获取失败: {e}"
            )

            results[name] = None

    return results


if __name__ == "__main__":

    market_data = get_market_data()

    print(
        "\n========== 全球金融市场 ==========\n"
    )

    for name, data in market_data.items():

        if data is None:

            print(
                f"{name}: 获取失败"
            )

        else:

            print(
                f"{name}: "
                f"日期 {data['date']} | "
                f"最高 {data['high']:.2f} | "
                f"最低 {data['low']:.2f} | "
                f"收盘 {data['close']:.2f} | "
                f"昨收 {data['previous_close']:.2f} | "
                f"涨跌幅 {data['change_percent']:+.2f}%"
            )
