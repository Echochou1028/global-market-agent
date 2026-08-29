import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone


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

    # ==========================================================
    # 计算请求日期范围
    #
    # end 不包含当天，因此向后多请求几天，
    # 防止周末、节假日造成数据缺失。
    # ==========================================================

    today = datetime.now(timezone.utc).date()

    start_date = today - timedelta(days=10)

    end_date = today + timedelta(days=1)

    for name, symbol in MARKETS.items():

        try:

            print(
                f"正在获取 {name} ({symbol})..."
            )

            # ==================================================
            # 获取明确日期范围的日线数据
            # ==================================================

            data = yf.download(
                symbol,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            print(
                f"{name} 原始数据日期："
                f"{[str(x.date()) if hasattr(x, 'date') else str(x) for x in data.index]}"
            )
            
            # ==================================================
            # yfinance 某些版本返回 MultiIndex
            # ==================================================

            if isinstance(data.columns, pd.MultiIndex):

                try:
                    data.columns = data.columns.get_level_values(0)

                except Exception:

                    pass

            if data.empty:

                print(
                    f"{name}：没有获取到数据"
                )

                results[name] = None

                continue

            # ==================================================
            # 确保索引按照时间排序
            # ==================================================

            data = data.sort_index()

            # ==================================================
            # 只保留 OHLC 完整的数据
            # ==================================================

            required_columns = [
                "Open",
                "High",
                "Low",
                "Close",
            ]

            missing_columns = [
                col
                for col in required_columns
                if col not in data.columns
            ]

            if missing_columns:

                print(
                    f"{name}：缺少字段 {missing_columns}"
                )

                results[name] = None

                continue

            data = data.dropna(
                subset=required_columns,
                how="any"
            )

            if data.empty:

                print(
                    f"{name}：没有完整行情数据"
                )

                results[name] = None

                continue

            # ==================================================
            # 最近一个完整交易日
            # ==================================================

            latest = data.iloc[-1]

            latest_date = data.index[-1]

            # ==================================================
            # 上一个完整交易日
            # ==================================================

            if len(data) >= 2:

                previous = data.iloc[-2]

                previous_close = float(
                    previous["Close"]
                )

            else:

                previous_close = float(
                    latest["Close"]
                )

            # ==================================================
            # 当前交易日数据
            # ==================================================

            high = float(
                latest["High"]
            )

            low = float(
                latest["Low"]
            )

            close = float(
                latest["Close"]
            )

            # ==================================================
            # 计算涨跌幅
            # ==================================================

            if previous_close != 0:

                change_percent = (
                    (close - previous_close)
                    / previous_close
                    * 100
                )

            else:

                change_percent = 0.0

            # ==================================================
            # 处理日期
            # ==================================================

            if hasattr(
                latest_date,
                "date"
            ):

                latest_date = (
                    latest_date.date()
                )

            # ==================================================
            # 保存结果
            # ==================================================

            results[name] = {

                "date":
                    str(latest_date),

                "high":
                    high,

                "low":
                    low,

                "close":
                    close,

                "previous_close":
                    previous_close,

                "change_percent":
                    change_percent,
            }

            print(
                f"{name}："
                f"{latest_date} "
                f"收盘 {close:.2f} "
                f"涨跌 {change_percent:+.2f}%"
            )

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
