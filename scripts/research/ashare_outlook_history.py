"""Cross-cycle, cross-style comparisons. Case labels are retrospective, never signals."""

from ashare_outlook_analysis import NAMES, price_rows


CASES = [
    ("2007", "2007全面转熊", "2007-10-16", "2008-10-28", None,
     "多个宽基后续持续走弱；不以单只明星股见顶定义结束。"),
    ("2009", "2009快速调整后修复", "2009-08-04", "2009-12-31", None,
     "年度高点后的深跌与中期修复并存，不能把每次跌破均线都当多年熊市。"),
    ("2015", "2015杠杆牛市结束", "2015-06-12", "2016-01-28", None,
     "价格风险跨风格扩散；年底反弹没有恢复此前高点。"),
    ("2018", "2018跨风格下行", "2018-01-26", "2018-12-28", None,
     "大盘到小盘共同承压，与强风格接力的2021年不同。"),
    ("2020", "2020全球冲击后再上行", "2020-03-23", "2021-02-10", None,
     "外部急跌后价格趋势重新恢复；短期风险不等于大周期必然结束。"),
    ("2021", "2021核心股转弱、中小盘接力", "2021-02-10", "2021-12-31", None,
     "春节前最后交易日到年底；大盘与中小盘方向相反，终点随风格不同。"),
    ("2022", "2022熊市中途反弹", "2022-04-26", "2022-10-31", "2022-06-28",
     "同时列反弹阶段和其后结果；不能把4至6月强反弹独立命名为新牛市。"),
    ("2024", "2024春季反弹与9月之前", "2024-02-05", "2024-09-18", "2024-05-20",
     "春季阶段盈利不代表中期趋势已经持续反转；9月18日为本轮起点。"),
    ("current", "2026当前调整", "2026-05-14", "2026-09-30", None,
     "仅记录截至9月30日已发生结果，未来周期终点未知，不补未来路径。"),
]

PANEL_DATES = ("2020-03-23", "2021-03-09", "2021-07-28", "2021-09-30",
               "2021-12-31", "2022-04-26", "2026-09-30")


def prepared(rows):
    closes = [float(r["close_price"]) for r in rows]
    prefix = [0.0]
    for value in closes:
        prefix.append(prefix[-1] + value)
    enriched = []
    for i, row in enumerate(rows):
        ma60 = (prefix[i + 1] - prefix[i - 59]) / 60 if i >= 59 else None
        ma250 = (prefix[i + 1] - prefix[i - 249]) / 250 if i >= 249 else None
        old250 = (prefix[i - 19] - prefix[i - 269]) / 250 if i >= 269 else None
        enriched.append({**row, "ma60": ma60, "ma250": ma250,
                         "ma250_slope_20d_pct": (ma250 / old250 - 1) * 100 if old250 else None,
                         "return_20d_pct": (closes[i] / closes[i - 20] - 1) * 100 if i >= 20 else None,
                         "return_60d_pct": (closes[i] / closes[i - 60] - 1) * 100 if i >= 60 else None})
    return enriched


def panel(histories, day):
    values = []
    for code, rows in histories.items():
        r = next((r for r in reversed(rows) if r["trade_date"] <= day), None)
        if not r or r["trade_date"] != day or r["ma250_slope_20d_pct"] is None:
            return None
        close = float(r["close_price"])
        values.append({"index_code": code, "name": NAMES[code], "date": day, "close": close,
                       "above_ma60": close > r["ma60"], "above_ma250": close > r["ma250"],
                       "distance_ma250_pct": (close / r["ma250"] - 1) * 100,
                       "ma250_slope_20d_pct": r["ma250_slope_20d_pct"],
                       "return_20d_pct": r["return_20d_pct"]})
    return {"date": day, "above_ma60_count": sum(r["above_ma60"] for r in values),
            "above_ma250_count": sum(r["above_ma250"] for r in values),
            "rising_ma250_count": sum(r["ma250_slope_20d_pct"] > 0 for r in values),
            "positive_20d_count": sum(r["return_20d_pct"] > 0 for r in values), "rows": values}


def period(histories, start, end):
    result = []
    for code, rows in histories.items():
        part = [r for r in rows if start <= r["trade_date"] <= end]
        if len(part) < 2 or part[0]["trade_date"] != start or part[-1]["trade_date"] != end:
            result.append({"index_code": code, "name": NAMES[code], "return_pct": None,
                           "lowest_from_start_pct": None, "peak_date": None})
            continue
        close = float(part[0]["close_price"])
        peak = max(part, key=lambda r: float(r["high_price"]))
        result.append({"index_code": code, "name": NAMES[code],
                       "return_pct": (float(part[-1]["close_price"]) / close - 1) * 100,
                       "lowest_from_start_pct": (min(float(r["low_price"]) for r in part[1:]) / close - 1) * 100,
                       "peak_date": peak["trade_date"]})
    return result


def synchronized_breaks(histories):
    """All five below MA60 and MA250 for five days, spaced 120 common sessions."""
    lookups = {code: {r["trade_date"]: r for r in rows} for code, rows in histories.items()}
    common = sorted(set.intersection(*(set(r) for r in lookups.values())))
    whole = lookups["sh000985"]
    count, last = 0, -1000
    events = []
    for i, day in enumerate(common):
        state = all(r[day]["ma250"] is not None and r[day]["close_price"] < r[day]["ma250"]
                    and r[day]["close_price"] < r[day]["ma60"] for r in lookups.values())
        count = count + 1 if state else 0
        if count != 5 or i - last < 120:
            continue
        last = i
        close = float(whole[day]["close_price"])
        e = {"date": day, "close": close}
        for window in (20, 60, 120):
            days = common[i + 1:i + 1 + window]
            complete = len(days) == window
            e[f"return_{window}d_pct"] = (float(whole[days[-1]]["close_price"]) / close - 1) * 100 if complete else None
            e[f"lowest_{window}d_pct"] = (min(float(whole[d]["low_price"]) for d in days) / close - 1) * 100 if complete else None
        events.append(e)
    return {"method": "五条宽基同时低于MA60与MA250，连续第5日记录；事件至少间隔120个共同交易日。后续只评价中证全指，不含触发日。",
            "note": "描述性反例检查，不是牛熊判定器；均线失守本身不能区分牛市调整与趋势反转。保留全部事件与未完成窗口。",
            "events": events}


def spring_2021(histories, stocks):
    series = {code: (NAMES[code], rows, "price_index") for code, rows in histories.items()}
    stock_rows = price_rows([{**r, "index_code": "600519"} for r in stocks], "600519", "2021-12-31")
    if stock_rows:
        series["600519"] = ("贵州茅台", stock_rows, "unadjusted_stock_price")
    metrics, paths = [], []
    for code, (name, rows, basis) in series.items():
        by_day = {r["trade_date"]: r for r in rows}
        required = ("2020-12-31", "2021-02-10", "2021-03-09", "2021-12-31")
        if not all(day in by_day for day in required):
            metrics.append({"code": code, "name": name, "missing_reason": "关键比较日期缺少真实行情"})
            continue
        a, b, c, d = [float(by_day[day]["close_price"]) for day in required]
        year = [r for r in rows if "2021-01-01" <= r["trade_date"] <= "2021-12-31"]
        peak = max(year, key=lambda r: float(r["high_price"]))
        metrics.append({"code": code, "name": name, "basis": basis, "source": by_day[required[-1]]["data_source"],
                        "year_return_pct": (d / a - 1) * 100, "spring_to_march_pct": (c / b - 1) * 100,
                        "spring_to_end_pct": (d / b - 1) * 100, "march_to_end_pct": (d / c - 1) * 100,
                        "peak_date": peak["trade_date"], "peak_value": float(peak["high_price"]),
                        "end_vs_peak_pct": (d / float(peak["high_price"]) - 1) * 100})
        paths.append({"code": code, "name": name, "basis": basis,
                      "points": [{"date": r["trade_date"], "value": float(r["close_price"]) / b * 100}
                                 for r in year if r["trade_date"] >= "2021-02-10"]})
    return {"base_date": "2021-02-10", "end_date": "2021-12-31", "rows": metrics, "paths": paths,
            "note": "2月10日为春节前最后交易日；曲线均以该日收盘=100，全年涨跌另以2020年末为基准。指数为价格指数；茅台为未复权价格，均不含分红。峰值日期为事后逐日核验，不参与实时预测。"}


def compare(snapshot, extra):
    cutoff = min(snapshot["as_of_at"][:10], "2026-09-30")
    histories = {code: prepared(price_rows(snapshot["data"]["indexes"], code, cutoff)) for code in NAMES}
    cases = []
    for id_, title, start, end, rebound, note in CASES:
        if end > cutoff:
            continue
        cases.append({"id": id_, "title": title, "start": start, "end": end,
                      "note": note, "rows": period(histories, start, end),
                      "rebound_end": rebound, "rebound_rows": period(histories, start, rebound) if rebound else []})
    return {"version": "ashare-history-comparison-v1", "as_of_at": snapshot["as_of_at"],
            "research_only": True, "spring_2021": spring_2021(histories, [r for r in extra["stocks"] if r["trade_date"] <= cutoff]),
            "panels": [r for day in PANEL_DATES if day <= cutoff and (r := panel(histories, day))],
            "cases": cases, "synchronized_breaks": synchronized_breaks(histories),
            "limitations": ["案例区间和类型是事后描述，不是事前可交易周期标签，不计算类比胜率或本轮转熊概率。",
                            "指数峰值存在风格错位；不使用某个明星股或沪深300代表全部A股。",
                            "五个相关且市值加权的宽基是风格参与代理，不是逐股广度或等权市场；不假装五个独立样本。",
                            "早期指数包含回溯历史；价格不含分红，指数规则与行业权重随年份变化。",
                            "历史月度信用、政策与外盘用于机制解释；未认证首次公开版本的序列不冒充实时回测。"]}
