"""Reproducible descriptive calculations, not a new regime or trading model."""

import math
from collections import defaultdict
from ashare_outlook_financing import strict_financing


NAMES = {"sh000001": "上证指数", "sh000985": "中证全指", "sh000300": "沪深300",
         "sh000905": "中证500", "sh000852": "中证1000"}


def price_rows(rows, code, end_date):
    selected = {}
    for row in rows:
        if row["index_code"] != code or row["trade_date"] > end_date:
            continue
        values = [row.get(k) for k in ("open_price", "close_price", "high_price", "low_price")]
        if (all(v is not None and math.isfinite(float(v)) and float(v) > 0 for v in values)
                and float(row["low_price"]) <= min(float(row["open_price"]), float(row["close_price"]))
                and float(row["high_price"]) >= max(float(row["open_price"]), float(row["close_price"]))):
            selected[row["trade_date"]] = row
    return sorted(selected.values(), key=lambda r: r["trade_date"])


def mean(values):
    return sum(values) / len(values) if values else None


def quantile(values, q):
    if not values:
        return None
    values = sorted(values)
    rank = (len(values) - 1) * q
    left = int(rank)
    right = min(left + 1, len(values) - 1)
    return values[left] + (values[right] - values[left]) * (rank - left)


def historical_breaks(rows):
    """First fifth consecutive close below MA250, with 120-session separation."""
    closes = [float(r["close_price"]) for r in rows]
    below_days, last_event = 0, -1000
    events = []
    for i in range(249, len(rows)):
        ma = mean(closes[i - 249:i + 1])
        below_days = below_days + 1 if closes[i] < ma else 0
        if below_days != 5 or i - last_event < 120 or rows[i]["trade_date"] < "2005-01-01":
            continue
        last_event = i
        event = {"date": rows[i]["trade_date"], "close": closes[i]}
        for window in (20, 60, 120):
            future = rows[i + 1:i + window + 1]
            complete = len(future) == window
            event[f"worst_{window}d_pct"] = (min(float(r["low_price"]) for r in future) / closes[i] - 1) * 100 if complete else None
            event[f"return_{window}d_pct"] = (float(future[-1]["close_price"]) / closes[i] - 1) * 100 if complete else None
        events.append(event)
    summaries = []
    for window in (20, 60, 120):
        losses = [e[f"worst_{window}d_pct"] for e in events if e[f"worst_{window}d_pct"] is not None]
        returns = [e[f"return_{window}d_pct"] for e in events if e[f"return_{window}d_pct"] is not None]
        summaries.append({"window": window, "sample_count": len(losses),
                          "worst_q25_pct": quantile(losses, .25), "worst_median_pct": quantile(losses, .5),
                          "worst_q75_pct": quantile(losses, .75), "return_median_pct": quantile(returns, .5),
                          "loss_over_10pct_count": sum(v <= -10 for v in losses)})
    return {"method": "2005年以来，第5个连续收盘低于MA250的交易日；事件间隔至少120交易日。后续最低价相对事件收盘，不含事件当日。",
            "limitations": "固定描述性样本，未控制宏观环境，不能作为当前跌幅概率或价格底部预测；120日以内窗口分离，不表示事件经济上独立。",
            "events": events, "summaries": summaries}


def index_analysis(rows, code, end_date):
    rows = price_rows(rows, code, end_date)
    if len(rows) < 270:
        raise ValueError(f"Insufficient price history: {code}")
    last = rows[-1]
    close = float(last["close_price"])
    closes = [float(r["close_price"]) for r in rows]
    cycle = [r for r in rows if r["trade_date"] >= "2024-09-18"]
    if not cycle:
        raise ValueError(f"No observations in the current cycle: {code}")
    peak = max(cycle, key=lambda r: float(r["high_price"]))
    july = [r for r in rows if "2026-07-01" <= r["trade_date"] <= "2026-07-31"]
    july_low = min(july, key=lambda r: float(r["low_price"])) if july else None
    anchors = []
    for window in (20, 60, 120, 250):
        low = min(rows[-window:], key=lambda r: float(r["low_price"]))
        anchors.append({"label": f"近{window}交易日最低价", "date": low["trade_date"], "value": float(low["low_price"]),
                        "distance_pct": (float(low["low_price"]) / close - 1) * 100})
    if july_low:
        value = float(july_low["low_price"])
        anchors.append({"label": "2026年7月调整最低价", "date": july_low["trade_date"], "value": value,
                        "distance_pct": (value / close - 1) * 100,
                        "status": "已失守，转为修复观察位" if close < value else "尚未失守，不代表一定托住"})
    scenarios = [{"peak_drawdown_pct": decline, "value": float(peak["high_price"]) * (1 - decline / 100),
                  "distance_pct": (float(peak["high_price"]) * (1 - decline / 100) / close - 1) * 100}
                 for decline in (20, 25, 30)]
    candles = []
    for i, row in enumerate(rows):
        if row["trade_date"] < "2024-09-01":
            continue
        candles.append({"date": row["trade_date"], "open": row["open_price"], "high": row["high_price"],
                        "low": row["low_price"], "close": row["close_price"],
                        "ma60": mean(closes[i - 59:i + 1]) if i >= 59 else None,
                        "ma250": mean(closes[i - 249:i + 1]) if i >= 249 else None})
    return {"index_code": code, "index_name": NAMES[code], "source_date": last["trade_date"],
            "data_source": last["data_source"], "close": close,
            "ma60": mean(closes[-60:]), "ma120": mean(closes[-120:]), "ma250": mean(closes[-250:]),
            "ma250_slope_20d_pct": (mean(closes[-250:]) / mean(closes[-270:-20]) - 1) * 100,
            "return_20d_pct": (close / closes[-21] - 1) * 100,
            "cycle_start_date": cycle[0]["trade_date"], "cycle_start_close": cycle[0]["close_price"],
            "cycle_return_pct": (close / float(cycle[0]["close_price"]) - 1) * 100,
            "cycle_peak_date": peak["trade_date"], "cycle_peak": float(peak["high_price"]),
            "cycle_drawdown_pct": (close / float(peak["high_price"]) - 1) * 100,
            "anchors": anchors, "stress_levels": scenarios, "candles": candles,
            "historical_breaks": historical_breaks(rows)}


def financing_summary(rows, calendar=None, as_of=None):
    if calendar is not None:
        return strict_financing(rows, calendar, as_of)
    grouped = defaultdict(dict)
    for row in rows:
        if row["exchange"] in ("SSE", "SZSE"):
            grouped[row["trade_date"]][row["exchange"]] = row
    complete = []
    for day, exchanges in sorted(grouped.items()):
        if len(exchanges) == 2 and all(r["financing_net_buy_amount"] is not None and r["financing_balance"] is not None for r in exchanges.values()):
            complete.append({"date": day, "balance": sum(float(r["financing_balance"]) for r in exchanges.values()),
                             "net_buy": sum(float(r["financing_net_buy_amount"]) for r in exchanges.values())})
    if not complete:
        return None
    result = {"source_date": complete[-1]["date"], "balance_cny": complete[-1]["balance"],
              "net_buy_cny": complete[-1]["net_buy"], "consecutive_windows_verified": False,
              "note": "来源日两个交易所均完整；滚动窗口需另核对A股日历，不能用删除缺失日后的最近N条冒充N交易日。"}
    return result


def calculate(snapshot):
    data = snapshot["data"]
    end_date = snapshot["as_of_at"][:10]
    indexes = [index_analysis(data["indexes"], code, end_date) for code in NAMES]
    market_date = indexes[0]["source_date"]
    calendar = [r["trade_date"] for r in price_rows(data["indexes"], "sh000985", market_date)]
    return {"as_of_at": snapshot["as_of_at"],
            "indexes": indexes,
            "financing": financing_summary(data["financing"], calendar, snapshot["as_of_at"]),
            "missing_dashboard": [{"index_code": code, "latest": [r for r in data["dashboard"] if r["index_code"] == code][-1]}
                                  for code in ("sh000300", "sh000852")],
            "methods": ["MA为未复权价格指数的交易日收盘简单平均，不是自然日均值。",
                        "高点回撤从2024-09-18后已发生的日内最高价计算。",
                        "20/25/30%高点回撤是情景压力参数，不是估计概率、底部或止损指令。",
                        "宏观快照含不同所属期和口径；累计流量不与单月值混算。"]}
