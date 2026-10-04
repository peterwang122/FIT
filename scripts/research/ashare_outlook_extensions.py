"""Expanded, descriptive evidence. No trading rules or production writes."""

from collections import defaultdict
from datetime import date
from math import sqrt
from statistics import stdev

from ashare_outlook_analysis import NAMES, price_rows
from ashare_outlook_content import p
from ashare_outlook_history import prepared
from ashare_outlook_financing import strict_financing

SOURCES = [
    ("sector_method", "中证：全指行业优选指数资料", "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/000987factsheet.pdf", "2026-08-31", "经过流动性和市值筛选的行业代表指数；不是全部行业或逐股广度"),
    ("sse_h1", "上交所：2026半年报业绩综述", "https://star.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260830_10830362.shtml", "2026-08-30", "沪市汇总，不等于中证500/1000当时成分的可比财务数据"),
    ("etf2024", "上交所：2024上半年ETF白皮书", "https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20240913_10761555.shtml", "2024-09-13", "股票ETF净流入与价格下跌可以并存；报告发布晚于所属期"),
    ("etf_shares", "上交所：清算后ETF份额", "https://www.sse.com.cn/market/funddata/volumn/etfvolumn/", "2026-09-28", "份额不是市值；未取得同口径长历史，不伪造全市场日净流入"),
    ("amac_aug", "基金业协会：2026年8月公募数据", "https://www.amac.org.cn/sjtj/tjbg/gmjj/202609/P020260918624509873296.pdf", "2026-09-18", "亿份、亿元；官方表本身有四舍五入；月末存量不是每日现金流"),
    ("amac_mar", "基金业协会：2026年3月公募数据", "https://www.amac.org.cn/sjtj/tjbg/gmjj/202604/P020260422599009744026.pdf", "2026-04-22", "份额与净值分别观察；不是10月最新值"),
    ("repurchase", "上交所转载：回购计划与实际进展", "https://www.sse.com.cn/cpc/cpctheme/4th20thcpc/4th20thcpcgcxx/c/c_20260413_10815019.shtml", "2026-04-03", "报道日期为4月3日；单公司例子，不冒充全市场已用额度"),
    ("repurchase_rule", "人民银行：股票回购增持再贷款通知", "https://www.pbc.gov.cn/redianzhuanti/118742/5444129/5444142/481faf4556cb42a5b444677b9673ea5c/index.html", "2024-10-18", "机制文件；已披露方案、授信、贷款发放和实际买入不是同一个量"),
    ("ah", "恒生：沪深港通AH股溢价指数", "https://origin-www.hsi.com.hk/chi/indexes/all-indexes/ahpremium", "2026-09-11T09:50:00+08:00", "官方页面可核验的是9月11日盘中124.20；不能当作9月30日最新收盘"),
]

SECTOR_CODES = ("sh000986", "sh000987", "sh000988", "sh000989", "sh000990", "sh000991", "sh000992", "sh000993")
STYLE_NAMES = {"sh000057": "上证全指成长", "sh000058": "上证全指价值", "sh000922": "中证红利", "sh000982": "中证500等权"}


def fmt(value, suffix="%", signed=True):
    return "缺失 / 窗口不足" if value is None else f"{value:+.2f}{suffix}" if signed else f"{value:.2f}{suffix}"


def table(title, columns, rows, note):
    return {"title": title, "columns": columns, "rows": rows, "note": note}


def visible_months(rows, as_of):
    """Keep vintage, basis and period kind separate; never count daily carry as samples."""
    selected = {}
    for r in rows:
        if r["available_at"] > as_of or r["period_end"] > as_of[:10]:
            continue
        key = (r["series_key"], r["period_kind"], r["basis_version"], r["period_end"])
        rank = (r["available_at"], r.get("revision_number", 0), r.get("observed_at", ""))
        if key not in selected or rank > selected[key][0]:
            selected[key] = (rank, r)
    return [v[1] for _, v in sorted(selected.items())]


def monthly_change(rows, latest, months):
    day = date.fromisoformat(latest["period_end"])
    target = day.year * 12 + day.month - months
    prior = next((r for r in rows if r["series_key"] == latest["series_key"]
                  and r["period_kind"] == latest["period_kind"] and r["basis_version"] == latest["basis_version"]
                  and date.fromisoformat(r["period_end"]).year * 12 + date.fromisoformat(r["period_end"]).month == target), None)
    return float(latest["value"]) - float(prior["value"]) if prior else None


def forward(rows, day, window):
    i = next((i for i, r in enumerate(rows) if r["trade_date"] == day), None)
    if i is None or i + window >= len(rows):
        return {"return_pct": None, "lowest_pct": None}
    future = rows[i + 1:i + 1 + window]
    close = float(rows[i]["close_price"])
    return {"return_pct": (float(future[-1]["close_price"]) / close - 1) * 100,
            "lowest_pct": (min(float(r["low_price"]) for r in future) / close - 1) * 100}


def valuation_parts(price_start, price_end, pe_start, pe_end):
    # An identity diagnostic, not official comparable EPS or index constituent profit.
    p_ratio, pe_ratio = price_end / price_start, pe_end / pe_start
    return {"price_change_pct": (p_ratio - 1) * 100, "pe_change_pct": (pe_ratio - 1) * 100,
            "implied_earnings_scale_change_pct": (p_ratio / pe_ratio - 1) * 100}


def calculate_extensions(snapshot, extra, history):
    if extra["as_of_at"] != snapshot["as_of_at"]:
        raise ValueError("Extension evidence cutoffs must match")
    cutoff, data = extra["market_date"], extra["data"]
    broad = {code: prepared(price_rows(snapshot["data"]["indexes"], code, cutoff)) for code in NAMES}
    proxy = {code: prepared(price_rows(data["indexes"], code, cutoff)) for code in SECTOR_CODES + tuple(STYLE_NAMES)}
    metrics = []
    whole_by_date = {r["trade_date"]: r for r in broad["sh000985"]}
    for code, rows in proxy.items():
        if len(rows) < 250 or rows[-1]["trade_date"] != cutoff:
            continue
        last = rows[-1]
        i = len(rows) - 1
        r20, r60 = last["return_20d_pct"], last["return_60d_pct"]
        base = next((r for r in rows if r["trade_date"] == rows[i - 20]["trade_date"]), None)
        whole = whole_by_date.get(base["trade_date"]) if base else None
        relative = ((float(last["close_price"]) / float(base["close_price"])) /
                    (float(whole_by_date[cutoff]["close_price"]) / float(whole["close_price"])) - 1) * 100 if whole else None
        activity_rows = rows[-25:]
        turnover = [r.get("turnover") for r in activity_rows]
        activity = (sum(turnover[-5:]) / 5) / (sum(turnover[:20]) / 20) if all(v is not None and v > 0 for v in turnover) and len({r["data_source"] for r in activity_rows}) == 1 else None
        metrics.append({"code": code, "name": STYLE_NAMES.get(code, last.get("index_name", code)), "date": cutoff,
                        "start": rows[0]["trade_date"], "observations": len(rows), "return_20d_pct": r20,
                        "return_60d_pct": r60, "relative_20d_pct": relative,
                        "above_ma60": last["close_price"] > last["ma60"], "above_ma250": last["close_price"] > last["ma250"],
                        "positive_20d_days": sum(r["return_20d_pct"] > 0 for r in rows[-20:]), "turnover_5_vs_prior20": activity})
    style_periods = []
    for label, start, end in (("2013至2014成长与全市场", "2013-01-04", "2014-12-31"),
                               ("2016至2017质量大盘接力", "2016-01-28", "2017-12-29"),
                               ("2021春节后错位见顶", "2021-02-10", "2021-12-31")):
        values = []
        for code in ("sh000985", "sh000300", "sh000905", "sh000852", "sh000057", "sh000058", "sh000922"):
            rows = broad.get(code, proxy.get(code, []))
            part = {r["trade_date"]: r for r in rows if start <= r["trade_date"] <= end}
            value = (float(part[end]["close_price"]) / float(part[start]["close_price"]) - 1) * 100 if start in part and end in part else None
            values.append({"code": code, "return_pct": value})
        style_periods.append({"label": label, "start": start, "end": end, "values": values})
    financing = strict_financing(data["financing"], [r["trade_date"] for r in broad["sh000985"]], extra["as_of_at"])
    valuations = []
    for code in ("sh000300", "sh000852"):
        rows = [r for r in data["valuations"] if r["index_code"] == code[2:] and r["pe_ttm"] is not None and r["pe_ttm"] > 0 and r["trade_date"] <= cutoff]
        last = rows[-1]
        prior = [float(r["pe_ttm"]) for r in rows[:-1]]
        rank = (sum(v < last["pe_ttm"] for v in prior) + .5 * sum(v == last["pe_ttm"] for v in prior)) / len(prior) * 100
        prices = {r["trade_date"]: r for r in broad[code]}
        anchor = next(r["trade_date"] for r in reversed(broad[code]) if r["trade_date"] <= "2026-05-13")
        first = next((r for r in rows if r["trade_date"] == anchor), None)
        parts = valuation_parts(float(prices[anchor]["close_price"]), float(prices[cutoff]["close_price"]), float(first["pe_ttm"]), float(last["pe_ttm"])) if first and last["trade_date"] == cutoff else None
        valuations.append({"code": code, "start": rows[0]["trade_date"], "date": last["trade_date"], "pe": last["pe_ttm"],
                           "sample_count": len(prior), "history_percentile": rank, "anchor": anchor, "decomposition": parts})
    monthly = visible_months(data["macro_observations"], extra["as_of_at"])
    monthly_current = []
    keys = {"m1_yoy": "M1同比", "m2_yoy": "M2同比", "tsf_stock_yoy": "社融存量同比", "pmi_manufacturing": "制造业PMI",
            "pmi_new_orders": "新订单PMI", "core_cpi_yoy": "核心CPI同比", "ppi_yoy": "PPI同比", "industrial_profit_month_yoy": "工业利润当月同比"}
    for key, name in keys.items():
        candidates = [r for r in monthly if r["series_key"] == key and r["period_kind"] == "monthly"]
        latest = max(candidates, key=lambda r: (r["period_end"], r["available_at"]))
        same_basis = [r for r in candidates if r["basis_version"] == latest["basis_version"]]
        monthly_current.append({**latest, "name": name, "change_3m": monthly_change(monthly, latest, 3),
                                "change_6m": monthly_change(monthly, latest, 6), "same_basis_start": same_basis[0]["period_end"],
                                "independent_months": len(same_basis), "replay_eligible_months": sum(bool(r["replay_eligible"]) for r in same_basis)})
    global_changes = []
    for label, rows, key, multiplier in (("美国10Y名义利率", data["us_yields"], "yield_10y", 100),
                                         ("美国10Y实际利率", data["us_yields"], "yield_real_10y", 100),
                                         ("HY OAS", data["us_credit"], "high_yield_oas", 100)):
        series = [r for r in rows if r.get(key) is not None and r["trade_date"] <= extra["as_of_at"][:10]
                  and (r.get("available_at") is None or r["available_at"] <= extra["as_of_at"])]
        last = series[-1]
        changes = {f"change_{w}": (float(last[key]) - float(series[-1-w][key])) * multiplier if len(series) > w else None for w in (3, 20, 60)}
        global_changes.append({"name": label, "value": last[key], "date": last["trade_date"], "unit": "bp", **changes})
    for code, label in (("UDI", "美元指数"), ("USDJPY", "美元兑日元"), ("USDCNH", "离岸美元兑人民币")):
        series = [r for r in data["fx"] if r["symbol_code"] == code and r.get("latest_price") is not None
                  and r["trade_date"] <= extra["as_of_at"][:10]]
        last = series[-1]
        global_changes.append({"name": label, "value": last["latest_price"], "date": last["trade_date"], "unit": "%",
                               **{f"change_{w}": (float(last["latest_price"]) / float(series[-1-w]["latest_price"]) - 1) * 100 if len(series) > w else None for w in (3, 20, 60)}})
    conditions = []
    whole = broad["sh000985"]
    for e in history["synchronized_breaks"]["events"]:
        i = next(i for i, r in enumerate(whole) if r["trade_date"] == e["date"])
        count, recovery = 0, None
        for j in range(i + 1, min(i + 251, len(whole))):
            count = count + 1 if whole[j]["close_price"] > whole[j]["ma60"] else 0
            if count == 5:
                recovery = j - i
                break
        conditions.append({"date": e["date"], "recovery_confirm_sessions": recovery,
                           "observed_sessions": min(250, len(whole)-i-1),
                           **{f"csi1000_{w}": forward(broad["sh000852"], e["date"], w) for w in (20, 60, 120)}})
    closes = [float(r["close_price"]) for r in broad["sh000852"][-61:]]
    volatility = stdev([closes[i] / closes[i-1] - 1 for i in range(1, len(closes))])
    vol_stress = [{"sessions": w, "move_pct": -volatility * sqrt(w) * 100, "price": closes[-1] * (1-volatility * sqrt(w))} for w in (20, 60)]
    annual_slopes = []
    for code, rows in broad.items():
        last = rows[-1]
        def ma60(r_index):
            return sum(float(r["close_price"]) for r in rows[r_index-59:r_index+1]) / 60
        annual_slopes.append({"code": code, "name": NAMES[code], "ma250_change_pct": last["ma250_slope_20d_pct"],
                              "ma60_change_pct": (ma60(len(rows)-1)/ma60(len(rows)-21)-1)*100})
    etf_counterexample = []
    for code, rows in broad.items():
        by_day = {r["trade_date"]: r for r in rows}
        etf_counterexample.append({"name": NAMES[code], "return_pct": (float(by_day["2024-06-28"]["close_price"]) / float(by_day["2023-12-29"]["close_price"])-1)*100})
    common_followups = []
    for label, day in (("2013年流动性压力", "2013-06-25"), ("2016年大盘接力观察", "2016-05-13"),
                       ("2020年全球急跌", "2020-03-23"), ("2021年抱团回撤", "2021-03-09"),
                       ("2022年熊市反弹起点", "2022-04-26"), ("2024年春季反弹", "2024-02-05"),
                       ("2026年全面受损", "2026-08-03")):
        common_followups.append({"label": label, "date": day, "rows": [
            {"code": code, **{f"window_{w}": forward(broad[code], day, w) for w in (20, 60, 120)}}
            for code in ("sh000985", "sh000300", "sh000905", "sh000852")]})
    return {"as_of_at": extra["as_of_at"], "market_date": cutoff, "research_only": True,
            "proxy_metrics": metrics, "style_periods": style_periods, "financing": financing, "valuations": valuations,
            "monthly": monthly_current, "global_changes": global_changes, "conditional_events": conditions,
            "volatility_stress": vol_stress, "annual_slopes": annual_slopes, "etf_2024_price_comparison": etf_counterexample,
            "common_followups": common_followups, "strategy_comparison": data["strategy_comparison"], "strict_joint_historical_replay": False,
            "missing_sector_codes": [c for c in extra["requested_index_codes"] if not proxy.get(c)]}


def sections_for(a):
    sectors = [r for r in a["proxy_metrics"] if r["code"] in SECTOR_CODES]
    positive = sum(r["return_20d_pct"] > 0 for r in sectors)
    above = sum(r["above_ma60"] for r in sectors)
    persistent = sum(r["positive_20d_days"] >= 15 for r in sectors)
    f = a["financing"]
    finance_tables = [table("融资：严格连续交易日，两所同日才合并", ["窗口", "起止", "净买入 / 亿元", "缺失日期"],
        [[f"{r['sessions']}交易日", f"{r['start']}至{r['end']}", fmt(r["net_buy_cny"]/1e8 if r["net_buy_cny"] is not None else None, "", False), ", ".join(r["missing_dates"]) or "无"] for r in f["windows"]],
        "研究交易日" + f["reference_trade_date"] + "使用前一交易日" + f["source_date"] + "；正常发布滞后为可用，来源日和计算日分开，窗口内真实缺口不跳过。")]
    style_table = table("行业/风格当前接力证据", ["代理", "20日", "60日", "相对全指20日", "MA60/250上方", "20日上涨窗口数", "成交活跃倍数"],
        [[r["name"],fmt(r["return_20d_pct"]),fmt(r["return_60d_pct"]),fmt(r["relative_20d_pct"]),f"{int(r['above_ma60'])}/{int(r['above_ma250'])}",f"{r['positive_20d_days']}/20",fmt(r["turnover_5_vs_prior20"],"倍",False)] for r in a["proxy_metrics"]],
        "截至9月30日。相对强弱用价格比值；成交活跃为自身最近5日均额/此前20日均额，仅同来源可算，不是全市场成交集中度。上证成长/价值仅覆盖沪市。")
    history_table = table("补充跨周期风格比较", ["事后描述区间", "全指", "沪深300", "中证500", "中证1000", "沪市成长", "沪市价值", "中证红利"],
        [[r["label"]+" "+r["start"]+"至"+r["end"],*[fmt(v["return_pct"]) for v in r["values"]]] for r in a["style_periods"]],
        "均为价格收益、不含分红；事后挑选案例只能说明机制，不计算类似当前的发生概率。")
    followup_table = table("相同观察日、相同后续窗口：收益 / 最低价变化", ["案例 / 观察日", "指数", "20交易日", "60交易日", "120交易日"],
        [[c["label"]+" / "+c["date"], NAMES[r["code"]], *[fmt(r[f"window_{w}"]["return_pct"])+" / "+fmt(r[f"window_{w}"]["lowest_pct"]) for w in (20,60,120)]] for c in a["common_followups"] for r in c["rows"]],
        "观察日是事后挑选案例，不是当时发出的信号；所有结果统一以观察日收盘为基准、不含当日低点，未来不足保持空值。")
    macro_table = table("货币信用至需求：独立月份与发布时滞", ["指标 / 口径", "所属期", "原值", "3月变化", "6月变化", "可用时间", "同口径月份 / 已标记可重放月"],
        [[r["name"]+" / "+r["basis_version"],r["period_end"],fmt(r["value"],"点" if r["unit"] == "points" else r["unit"],False),fmt(r["change_3m"],"点" if r["unit"] == "points" else "pp"),fmt(r["change_6m"],"点" if r["unit"] == "points" else "pp"),r["available_at"],f"{r['independent_months']} / {r['replay_eligible_months']}"] for r in a["monthly"]],
        "PMI变化为指数点，其他变化为百分点。可重放月只是库内版本标记，不代表已逐条认证首次发布时间或整套跨周期宏观都通过时点认证；未核验首次发布的旧值只用于诊断。")
    global_table = table("全球冲击：短期与中期不能混用", ["系列", "原值", "来源日", "3观测变化", "20观测变化", "60观测变化"],
        [[r["name"],str(r["value"])+("%" if r["unit"] == "bp" else ""),r["date"],*[fmt(r[f"change_{w}"],r["unit"]) for w in (3,20,60)]] for r in a["global_changes"]],
        "利率和利差原值为百分比、变动用bp；美元指数原值为点，汇率为报价、变动为百分比。各序列有效观测数及来源日不同，盘中外汇不冒充收盘；HY历史公开时间尚未逐笔认证。")
    conditions_table = table("全部同步失守事件：中证1000后续与全指修复", ["观察日", "20日收益 / 最低", "60日收益 / 最低", "120日收益 / 最低", "全指MA60连续5日修复 / 已观察"],
        [[r["date"],*[fmt(r[f"csi1000_{w}"]["return_pct"])+" / "+fmt(r[f"csi1000_{w}"]["lowest_pct"]) for w in (20,60,120)],
          f"{r['recovery_confirm_sessions'] if r['recovery_confirm_sessions'] is not None else '未确认'} / {r['observed_sessions']}交易日"] for r in a["conditional_events"]],
        "事件沿用五宽基同时低于MA60/250连续5日、间隔120交易日的固定条件；后续最低不含触发日。修复仅代表MA60，不代表重回牛市；250日观察不足不当作永不修复。")
    strategy = a["strategy_comparison"]
    strategy_table = table("情绪强化测试：环境开关的机会成本", ["版本", "区间收益", "最大回撤", "阻止原策略买入", "收益减少", "回撤减少"],
        [[r["label"],fmt(r["return_pct"]),fmt(r["mdd_pct"],signed=False),str(r["blocked_baseline_buys"]),fmt(r["missed_return_pp"],"pp"),fmt(r["drawdown_reduction_pp"],"pp")] for r in strategy["results"]],
        f"{strategy['start_date']}至{strategy['end_date']}，执行ETF {strategy['execution_asset']}，次日开盘、相同仓位规则；主表费用为零。现库重放，不是历史实盘或截至9月30日的新回测。")
    sources = ["csi", "sector_method"]
    result = [
      {"id":"relay","title":"扩展一：行业与风格接力","verdict":f"已核验{len(sectors)}个行业代表：20日绝对上涨{positive}/{len(sectors)}，MA60上方{above}/{len(sectors)}，近20天至少15个上涨窗口{persistent}/{len(sectors)}。相对抗跌不能自动当新牛市。","paragraphs":[
        p("计算","下表把绝对收益、相对全指强弱、均线位置、持续性和自身成交活跃分开。只有绝对走强且有持续性的行业，才是接力的候选；相对上涨但绝对仍跌，是防御轮动。",*sources),
        p("计算","当前医药20日上涨1.59%，能源60日上涨8.20%但20日跌5.37%；金融20日下跌却相对抗跌。医药仅2/20个近期滚动窗口为正，接力尚短。不能说没有任何行业机会，也不能说已有广泛接力。", "csi"),
        p("判断","2013至2014与2016至2017的补充对照说明，领导权可以从大盘转中小盘，也可以反向转大盘质量；沪市成长与全A小盘不是同一个概念。2021是同一年错位见顶的具体反例。当前不能把旧科技主线回调直接命名为全A牛市结束，也不能仅靠一个能源或红利方向相对抗跌证明新行情已经接力。"),
        p("限制",f"当前有{len(sectors)}条行业代表长历史。通信、公用事业、房地产的当前同口径历史仍未取得；金融地产000992为合并行业，不能冒充新分类中的纯金融，也不能再加入房地产凑成11行业扩散率。行业优选与全行业指数保持分开，未采集行业不算未上涨。", "sector_method"),
        p("判断","能源价格上涨可能抬升资源利润、压低下游利润；银行与红利抗跌也可能是风险偏好收缩。研究上将‘增长型接力’与‘防御型避险’分开：前者更有利于中证500/1000牛市波段，后者未必恢复目标指数趋势。")],"tables":[style_table,history_table,followup_table]},
      {"id":"earnings_quality","title":"扩展二：上市公司盈利质量与估值拆解","verdict":"利润总量与现金流提供韧性反证；尚不能证明盈利改善已经扩散到中证500/1000。","paragraphs":[
        p("事实","上交所半年报汇总：2318家公司的收入同比6.3%、净利润17.6%、扣非17.2%；实体公司经营现金流同比35.1%、覆盖净利润1.2倍。924家公司净利润增长，另披露142家扭亏。", "sse_h1"),
        p("计算","924/2318约39.86%，所以总利润增长不等于大多数公司增长；但剩余公司也不能全部算作利润下滑，扭亏、基数和分类交叉需要逐公司核验。现金流覆盖改善支持盈利质量，并不消除下半年成本冲击。", "sse_h1"),
        p("计算","下表将5月13日到9月30日价格变化拆为PE变化和价格/PE残差。等式可复算，但残差只称‘隐含盈利尺度’，不是官方可比EPS：成分调整、亏损剔除、股本与计算规则都会影响它。不能从残差直接宣称上市公司真实利润下降多少。", "csi"),
        p("计算","沪深300与中证1000 PE分别位于各自此前有效历史约56.59%和61.71%分位。大盘相对小盘有更高盈利收益率，不等于大盘自身处在历史极便宜位置；不同结构指数的PE也不能直接当风险溢价差。", "csi"),
        p("判断","价格跌、PE压缩而盈利仍增长，可能是贴现率或风险溢价修正；价格与同成分现金流、扣非利润一起转差，才更像盈利周期下行。当前有沪市总量反证，缺少当时成分的目标指数财务面板，故保留两种路径，不用工业利润代替指数EPS。"),
        p("限制","未完成全A逐季首发财报、历史成分和退市样本的联合面板。分指数/行业扣非、现金流及增长覆盖率尚不能给出严格跨周期回测；本章已补官方总量和估值诊断，不把未取得的数据写成验证通过。")],"tables":[table("估值历史与本次价格拆解",["指数","PE / 此前历史分位","历史起点 / 样本","5月13日起价格","PE变化","隐含盈利尺度变化"],
        [[NAMES[r["code"]],fmt(r["pe"],"倍",False)+" / "+fmt(r["history_percentile"],signed=False),f"{r['start']} / {r['sample_count']}",*[fmt(r["decomposition"][key]) if r["decomposition"] else "缺失" for key in ("price_change_pct","pe_change_pct","implied_earnings_scale_change_pct")]] for r in a["valuations"]],
        "历史分位是此前全部有效PE中间秩，排除当日；不是固定目标倍数或盈利预测。") ]},
      {"id":"stock_funding","title":"扩展三：股票资金、杠杆与供给","verdict":"银行宽松、ETF增持与股票风险敞口不是同一件事；融资必须按完整交易日研究。","paragraphs":[
        p("计算",f"研究日{f['reference_trade_date']}按前一交易日口径使用{f['source_date']}两所完整数据：余额{f['balance_cny']/1e12:.4f}万亿元，较近120交易日内完整记录峰值下降{abs(f['balance_change_from_observed_peak_pct']):.2f}%；完整日{f['valid_sessions']}/{f['required_sessions']}。正常一天发布滞后不算缺失，但余额仍不能代表已完成去杠杆。", "margin", "szmargin"),
        p("计算","截至9月29日的连续5交易日融资净流出429.77亿元，20交易日净流出556.49亿元，两所窗口完整，可用于9月30日研究。这支持主动减仓/去杠杆压力；无需等9月30日自身融资值才判断，但余额仍较大，不能说杠杆风险已经出清。", "margin", "szmargin"),
        p("事实","2024年上半年股票ETF净流入3886亿元，ETF总体也持续净流入。但同期宽基表现分化，下表显示资金托底没有自动带来小盘趋势恢复。基金买入可以是逆势配置或替换原有股票仓位，不等于全市场新增同额购买力。", "etf2024"),
        p("事实","2026年3月股票基金份额由39209.08增至39349.05亿份，资产净值却由56297.06降至51128.57亿元；8月则份额由40485.99降至39696.84亿份，净值由49874.09增至50370.70亿元。两个方向相反的例子说明净值增减不是净申赎。", "amac_mar", "amac_aug"),
        p("判断","真实份额变化适合观察申赎，但份额×净值只是金额估计，不冒充官方日成交净流入，也不能识别购买者是谁。官方ETF清算份额有入口，当前未形成完整同口径历史面板；本次不把商业‘主力净流入’字段拿来补缺。", "etf_shares"),
        p("判断","实际回购和实际新增融资要分别看，计划上限与已募集金额不能相减得‘全A净资金’。分红会离开股票账户也可能再投资，衍生品保证金与现货配置也非可直接相加。当前证据支持资金承受力仍需验证，不支持‘存款很多，所以股市一定上涨’。")],"tables":finance_tables+[table("2024上半年：股票ETF流入的反例",["宽基","2023年末至2024年6月28日价格收益"],[[r["name"],fmt(r["return_pct"])] for r in a["etf_2024_price_comparison"]],"官方资金统计为半年总量，9月13日才发布；历史机制解释，不能放入6月交易决策。"),
            table("8月公募份额与市值分开看", ["类别","7月 / 8月份额（亿份）","7月 / 8月净值（亿元）","份额变化","净值变化"],
              [["股票", "40485.99 / 39696.84", "49874.09 / 50370.70", "-789.15亿份", "+496.61亿元"],
               ["混合", "24899.45 / 24846.82", "38325.02 / 40892.95", "-52.63亿份", "+2567.93亿元"]],
              "来源为基金业协会9月18日官方PDF；分类和份额随产品变化，差值是存量变化，不是可直接合并的市场现金流。官方原表存在四舍五入。") ]},
      {"id":"macro_transmission","title":"扩展四：货币信用到需求与盈利的传导","verdict":"低资金利率支持估值，但信用活化减速；需要分清政府托底、企业融资与居民需求。","paragraphs":[
        p("计算","使用独立月份观察3月及6月变化，下表不把日更延用的同一个月值当新增样本，M1新旧口径分别保存。新口径包括官方后来提供的2024可比数据，但不能倒称2024当时已经公布；其31个月覆盖也远不足以跨多轮牛熊，不能拿旧口径混成长期分位。", "pbc"),
        p("计算","8月社融单月1.6577万亿元，其中政府债券1.0097万亿元，占约60.91%；剔除政府债后的派生增量0.6480万亿元。该剩余仍含企业贷款、债券等公共部门相关融资，不叫私人信用。1至8月企业中长期贷款5.64万亿元，居民中长期仅188亿元，均为累计口径，不能冒充8月当月。", "pbc"),
        p("判断","传导分四步：银行资金宽松→信用真实使用→订单与收入→利润和现金流。当前前一步较稳，居民需求仍弱；PMI新订单与利润可以提供后两步确认。企业中长期贷款增加也可能用于置换或政策项目，并非直接等于投资需求。", "pbc", "pmi", "profits"),
        p("判断","比较2021，信用减速未阻止成长小盘接力，宏观弱不能做所有策略的停买开关；比较2022和2024春季，宽松与反弹未能保证持续上行。信用与价格存在双向反应，应比较1至3个月、3至6个月传导，并允许价格先于利润恢复。", "pbc2021q2", "pbc2021policy"),
        p("限制","本次补全可见月份及覆盖，但尚无足够多轮次的全套宏观首发版本联合样本，无法给可靠时滞相关系数或因果胜率。旧值可展示，未经首次公开认证不能用于声称可交易的宏观拐点模型；不因这一限制删除当前宏观解释。")],"tables":[macro_table]},
      {"id":"shock_types","title":"扩展五：外部冲击分类与行业传导","verdict":"当前更像利率与能源成本压力，不是已经得到确认的全球信用危机。","paragraphs":[
        p("计算","短期3个观测看重定价，中期20/60个观测看持续压力；下面保持原单位和来源日。名义利率上升但信用稳定，可是通胀或期限溢价压力；实际利率、美元、信用同时上行并伴全球股市下跌，风险性质才更接近去杠杆。", "dgs10", "dfii10", "credit", "sina"),
        p("判断","增长/信用冲击通常股票跌、油铜跌、信用利差扩大；能源供给冲击则可能油涨、实际需求受损、利润向上游转移；贴现率冲击可能先压高估值成长。黄金与白银也要分货币避险和工业需求，不能把商品全部归为一个方向。", "iea", "gold"),
        p("判断","2020为信用和增长急挫后的紧急宽松修复；2022为加息及通胀环境中的熊市反弹；2021局部抱团估值下修却有小盘接力。当前实际利率和能源压力与2020不同，但全球股市/信用尚未全面恐慌，也不能直接套用2022最终跌幅。", "fed2020", "fed2022", "csi"),
        p("判断","日本加息只增加融资成本脆弱性；要结合数日日元急升、全球股市同跌、VIX与信用急升确认套利去杠杆。人民币相对稳定是中国风险溢价的缓冲，不会消除能源进口成本和美元融资成本。", "boj", "jgb", "sina"),
        p("限制","现有日本长债、商品与部分外盘首次发布历史不齐，本次不输出未经对齐的回归系数或行业因果弹性；冲击路径为有依据的机制判断，已实现价格比较与情景预测分开。")],"tables":[global_table,table("三类冲击对应的A股观察",["路径","联合证据","潜在受益 / 承压","使该解释失效的证据"],[
          ["贴现率重估","实际利率↑，信用未爆发","低估值现金流相对占优；长久期成长承压","实际利率↓且成长仍持续弱，需查盈利"],
          ["增长 / 信用危机","股票、油、铜↓，信用↑","防御可能相对抗跌；需求敏感行业承压","股市扩散上涨、信用收窄、订单恢复"],
          ["能源供给成本","能源↑，需求弱、下游利润挤压","资源可能获利；制造消费运输成本承压","供给恢复、运费回落、下游利润回升"]],"机制方向不等于可保证的行业收益，也不将相关指标重复加权计票。") ]},
      {"id":"policy_delivery","title":"扩展六：政策宣布与资金落地","verdict":"政策能先改变预期，但持续行情要看实际执行和盈利，不把宣布额度当已到账。","paragraphs":[
        p("事实","回购增持再贷款规则要求已披露回购/增持方案，并经银行授信与贷款发放。央行工具额度、银行贷款和公司实际买入是不同环节，必须分别保存日期和规模。", "repurchase_rule"),
        p("事实","4月3日上交所转载报道：海尔智家计划回购30至60亿元，当时累计实际回购3.3亿元。这是计划与兑现差异的具体例子，不能把计划上限60亿元提前记为股票需求，也不代表该公司10月实际进展。", "repurchase"),
        p("判断","托底资金可能降低尾部风险，却不必带来全市场牛市。2024上半年ETF流入和2022熊市反弹是反例；2024年9月的预期改善则说明价格可先于月度需求起动。政策往往因经济转弱而推出，‘政策后涨/跌’不是它独立导致涨/跌的因果证明。", "etf2024", "csi"),
        p("判断","国际贸易安排也走同样链路：公布共识→法律清单/生效→通关订单→企业收入与利润。能源、运费、出口限制改变成本和可达市场；单次缓和不等于所有关税撤销。中国财政支出要看执行与受益行业，政府融资和居民消费不直接画等号。", "trade", "fiscal"),
        p("限制","尚未取得全市场实际回购、融资到账、政策工具逐日使用额的完整联合档案。下面是已核验事件和传导账本，不是已估计政策收益回归；不拼造‘政策资金总净流入’。")],"tables":[table("政策/事件账本：已公布与已实现分开",["发布日期","事件","可以确认","不能提前确认"],[
          ["2024-10-18","回购增持再贷款机制","方案→授信→贷款的路径","全部额度已用于股票购买"],
          ["2026-04-03","海尔智家回购报道","当时实际3.3亿元，计划30至60亿元","10月实际累计与全市场规模"],
          ["2026-09-18","日本央行政策","目标1.25%，9月24日生效","全球套利平仓必然发生"],
          ["2026-09-28","经贸磋商共识","已公布安排","全部法律落地和未来订单利润"]],"引用原始日期；只有日期无时分时不虚构时刻。") ]},
      {"id":"conditional_bottom","title":"扩展七：条件低点与修复时间","verdict":"相同价格失守状态既出现继续下跌，也出现恢复；不能把过去平均低点当预测。","paragraphs":[
        p("计算","沿用预先固定的五宽基同步失守条件，列全部事件，新增目标指数自身20/60/120日结果和全指恢复时间。与2021局部风格更替不同，此条件刻画全面受损；2020修复和2008/2015后续深跌都保留，不能只挑相似成功样本。", "csi"),
        p("判断","当前应把中证1000的观察区说成约7200、6700、6300附近：第一是已发生低点，第二混合旧低点与固定回撤刻度，第三是压力刻度。没有经联合基本面认证的条件分布，不能给这些区间附80%之类概率；旧低点和25%跌幅重合不算独立验证。"),
        p("情景","下表再给一份波动尺度：最近60个日收益标准差×根号20或60，假设均值为零、波动保持。只是风险刻度，不是正态置信区间，跳跃和波动聚集会让实际尾部更大。盈利与PE敏感性另列，三种刻度不能重复当‘三票支撑’。"),
        p("判断","修复先看停止创新低与新接力，再看均线重返和信用/盈利扩散。连续5日在MA60之上只是中期价格修复，不是牛市认证；2022反弹说明短暂修复也能失败。低点失效来自持续更低高低点、风险外溢及盈利成本恶化，而不是价格恰好碰到某个整数点。")],"tables":[conditions_table,table("中证1000波动压力尺度",["持有尺度","负向1倍波动幅度","对应条件点位"],[[f"{r['sessions']}交易日",fmt(r["move_pct"]),str(round(r["price"]/100)*100)+"附近"] for r in a["volatility_stress"]],"以9月30日收盘为基准；单一历史波动假设，不代表公允价值、置信区间或最大损失。") ]},
      {"id":"strategy_value","title":"扩展八：环境判断对策略到底有什么用","verdict":"保守可以降低回撤，也会误停低吸；不能只比较风险判断是否提前变黄。","paragraphs":[
        p("计算","读取9月27日已经归档的同规则重放，未改保存策略。旧全A暂停规则较不限制少7.35pp收益、减少8.76pp回撤；旧中证1000暂停少18.52pp收益、同样减少8.76pp回撤。现有新环境开关在此区间没有阻止原策略买入，因而收益回撤相同。"),
        p("判断","这并非‘永不停买最好’：同一段里既有2025年1月误停反弹机会，也有2026年7月减少下跌暴露。指标要评价阻止的买入是否真该阻止、恢复有多晚，并与现金占用和逆向幅度一起比较；只要变黄就暂停，会把牛市内部低点也拒之门外。"),
        p("限制",f"该归档有{len(strategy['signal_data_quality']['missing_emotion_dates'])}个交易日缺原始情绪，现有引擎默认50，另有融资缺失及图像估算。严格重放完整标记为false；因此本表只是现库机制复现，不能把58.33%当完整真实历史成绩。主表零成本，成本敏感性另保留归档。"),
        p("判断","研究建议：环境判断负责大周期适配，风险负责仓位和冲击，波段规则负责具体入场；三者不应被一个临时均线失守开关完全替代。新机制必须同时披露错过的收益和避免的损失，不自动修改你现有牛市、熊市策略、停买或通知。")],"tables":[strategy_table]},
      {"id":"cross_listing","title":"扩展九：A/H与中国资产相对全球","verdict":"同公司价差有助区分风险溢价；当前证据不足以据此确认中国资产独立转熊。","paragraphs":[
        p("事实","恒生AH溢价指数使用同时A/H上市公司样本，反映A股相对H股的加权价差。官方页面可核验9月11日09:50为124.20，意为该指标口径下约24.20%溢价；它不是9月30日收盘，也不能代表所有A股尤其小盘。", "ah"),
        p("判断","A弱H强、且同公司溢价收窄，可提示内地相对风险偏好或资金约束；A/H同跌而全球稳定，更支持中国盈利或制度风险；中国与全球同跌且信用恶化，则更像共同冲击。需控制公司、币种、行业和交易时段，不能把沪深300减恒生科技收益当作纯中国风险。"),
        p("计算","当前原报告中ACWI/EFA/EEM并没有与A股同幅全面急跌，人民币近20观测基本稳定；所以‘全球危机解释全部A股回调’证据不足。另一方面美元ETF NAV包含汇率及分红影响，用人民币指数价格直接相减只能作方向诊断，不能当严格相对收益或因果系数。", "acwi", "efa", "eem", "sina"),
        p("限制","未取得截至9月30日的AH同公司完整历史与人民币含分红可比序列。保留可核验官方价差和解释路径，不填过期值冒充最新；暂不将AH证据计入牛熊判定或概率。")],"tables":[table("跨市场解释需要哪些联合证据",["观察","支持解释","主要反证/控制"],[
          ["A弱H强、同公司溢价收窄","内地相对风险溢价 / 资金约束","汇率、行业、交易时段和样本调整"],
          ["A/H同跌、全球稳定","中国盈利或政策预期偏弱","中国科技与全球科技是否同行业同跌"],
          ["各地股市同跌、信用急扩","全球共同风险传导","局部指数构成不同和时差"],
          ["中国走强、人民币稳定、盈利扩散","国内接力可抵消外部贴现压力","是否只有少数资源/防御权重上涨"]],"上述是可证伪解释框架，不是已估计事件概率。") ]},
    ]
    synthesis = {"id":"synthesis","title":"独立综述：综合证据后的结论","verdict":"全市场趋势受损、处于转弱观察；牛市延续尚未重新确认，多年熊市也未获充分确认。","paragraphs":[
        p("判断","这次研究的主结论不是简单‘牛市还在’或‘已经结束’。五宽基同步受损已不是茅台式单一主线调整；行业接力、信用活化和实际资金兑现仍需验证。更合适的定位是牛市后段的广泛调整 / 转弱观察，不把当前状态当仍可无条件低吸的健康牛市。"),
        p("计算",f"行业代表中20日绝对上涨{positive}/{len(sectors)}、MA60上方{above}/{len(sectors)}；年线近20日只抬升约0.05%至0.70%，MA60却全面下行。年线为滞后背景，不足以独立支撑牛市继续。相对抗跌不等于新主线，未覆盖行业也不等于没有机会。", "csi"),
        p("判断","反对直接宣布多年熊市的最强证据是：银行资金不紧，上市公司利润和现金流总量改善，多数宽基7月低点仍未破，外盘尚未全面恐慌。支持保持保守的证据是：价格风险跨风格扩散、融资5日净流出约430亿元、信用活化减速、实际利率和能源成本压力较强。正反证并存，不给未经校准的牛熊概率。", "sse_h1", "pbc", "bank", "dfii10", "iea", "margin", "szmargin"),
        p("情景","中证1000约7200附近先观察价格是否稳住；约6700附近是下一层旧低点/压力刻度；约6300附近只在更弱情景中作为压力尺度。它们不是必到目标或买入保证。基本面变好可使市场在更高处止跌，外部跳跃风险和盈利下修也可穿透这些刻度。"),
        p("判断","后续仍可能出现大行情，但需要新的绝对强势行业持续接力、目标指数修复并回踩守住、真实资金与订单利润逐步扩散，外部利率/成本不再持续恶化。价格可以先于宏观改善，不要求所有月度数据转正；若只剩防御权重抗跌，中证1000策略适配仍可能差。"),
        p("判断","判断失效有两边：若全指与500/1000连续形成更低高低点、7月低点失守且反弹无接力、信用与现金流进一步恶化，转熊解释显著增强；若多数代表绝对走强、宽基重新站稳、订单和盈利扩散，则恢复牛市解释增强。一次政策消息或一天长阳不单独改变大周期结论。"),
        p("限制","本次全部扩展方向均已加入，并分别写出实际计算、官方证据及研究阻断点；缺少目标指数财报首发面板、完整行业与ETF份额历史、政策使用额和同公司AH长历史，所以它不是已完成认证的联合牛熊预测模型。报告固定截至10月4日04:00，只用于研究，不改策略和通知。")],"tables":[table("综合证据，不机械重复计票",["维度","支持恢复的证据","支持转弱的证据","当前研究结论"],[
          ["价格与接力","多数7月低点仍守住","五宽基均线失守、接力不确定","健康牛市未确认"],
          ["信用与银行资金","资金价格不紧","M1活化减速、居民信用弱","托底不等于新需求"],
          ["盈利与现金流","沪市总量及现金流改善","改善并未确认扩散至目标指数","有韧性，但不能替代成分财报"],
          ["股票资金","ETF和回购有实际支持","按T-1可用融资5日净流出约430亿元","去杠杆发生但未证实出清"],
          ["全球与政策","未见全面全球恐慌","实际利率、能源成本偏强","有外部约束，不是已确认全球危机"],
          ["策略代价","保留牛市低吸可避免误停","停止买入可降低部分逆向风险","大周期、冲击、入场分工"]],"相关价格、融资和风险分不当独立样本；综述是有边界的判断，不是未经检验的新评分。") ]}
    return [synthesis, *result]
