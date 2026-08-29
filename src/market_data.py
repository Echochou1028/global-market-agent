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


def download_data(symbol, start_date, end_date):
    """
    获取指定日期范围的日线数据
    """

    try:
        data = yf.download(
            symbol,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )

        if data.empty:
            return None

        # yfinance 某些版本返回 MultiIndex
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        return data.sort_index()

    except Exception as e:
        print(f"数据获取异常：{e}")
        return None


def get_complete_rows(data):
    """
    只保留 Close 有效的完整交易数据。
    High / Low / Close 必须存在。
    """

    if data is None or data.empty:
        return pd.DataFrame()

    required_columns = [
        "High",
        "Low",
        "Close",
    ]

    for column in required_columns:
        if column not in data.columns:
            return pd.DataFrame()

    result = data.dropna(
        subset=required_columns,
        how="any"
    )

    return result


def get_market_data():

    results = {}

    today = datetime.now(timezone.utc).date()

    # 多取几天，覆盖周末和节假日
    start_date = today - timedelta(days=10)

    # end 不包含当天，所以多取一天
    end_date = today + timedelta(days=1)

    for name, symbol in MARKETS.items():

        try:

            print(
                f"正在获取 {name} ({symbol})..."
            )

            # ==================================================
            # 第一次获取
            # ==================================================

            data = download_data(
                symbol,
                start_date,
                end_date
            )

            if data is None or data.empty:

                print(
                    f"{name}：没有获取到数据"
                )

                results[name] = None
                continue

            # ==================================================
            # 找到最近一条 Close 有效的数据
            # ==================================================

            complete_data = get_complete_rows(data)

            if complete_data.empty:

                print(
                    f"{name}：没有完整收盘数据"
                )

                results[name] = None
                continue

            latest_date = complete_data.index[-1]

            # ==================================================
            # 判断原始数据最后一天是否存在
            # ==================================================

            raw_latest_date = data.index[-1]

            if hasattr(raw_latest_date, "date"):
                raw_latest_date = raw_latest_date.date()

            if hasattr(latest_date, "date"):
                latest_date = latest_date.date()

            # ==================================================
            # 如果最新日期 Close 缺失：
            # 单独重新请求该日期
            # ==================================================

            if raw_latest_date > latest_date:

                print(
                    f"{name}："
                    f"{raw_latest_date} 收盘数据缺失，"
                    f"正在重新获取..."
                )

                retry_start = raw_latest_date
                retry_end = raw_latest_date + timedelta(days=1)

                retry_data = download_data(
                    symbol,
                    retry_start,
                    retry_end
                )

                retry_complete = get_complete_rows(
                    retry_data
                )

                if not retry_complete.empty:

                    # 找到重新获取后的最新完整数据
                    retry_latest_date = (
                        retry_complete.index[-1]
                    )

                    if hasattr(
                        retry_latest_date,
                        "date"
                    ):
                        retry_latest_date = (
                            retry_latest_date.date()
                        )

                    # 如果确实获取到了更新日期
                    if retry_latest_date >= latest_date:

                        complete_data = pd.concat(
                            [
                                complete_data,
                                retry_complete
                            ]
                        )

                        complete_data = (
                            complete_data[
                                ~complete_data.index.duplicated(
                                    keep="last"
                                )
                            ]
                            .sort_index()
                        )

                        latest_date = (
                            retry_latest_date
                        )

                        print(
                            f"{name}："
                            f"{latest_date} "
                            f"收盘数据获取成功"
                        )

                else:

                    print(
                        f"{name}："
                        f"{raw_latest_date} "
                        f"重新获取仍失败，"
                        f"回退到最近完整交易日 "
                        f"{latest_date}"
                    )

            # ==================================================
            # 最终确定最新完整交易日
            # ==================================================

            latest = complete_data.iloc[-1]

            # ==================================================
            # 找上一交易日收盘价
            # ==================================================

            valid_close = (
                complete_data["Close"]
                .dropna()
            )

            if len(valid_close) >= 2:

                previous_close = float(
                    valid_close.iloc[-2]
                )

            else:

                previous_close = float(
                    latest["Close"]
                )

            # ==================================================
            # 获取 OHLC
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
            # 保存最终结果
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
                f"{name} 获取失败：{e}"
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
