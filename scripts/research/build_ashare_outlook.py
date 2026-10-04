"""Build a dated, reproducible report from read-only snapshots and cited commentary."""

import argparse
import copy
import hashlib
import json
from pathlib import Path

from ashare_outlook_analysis import calculate
from ashare_outlook_content import SECTIONS, SOURCES, WATCHLIST
from ashare_outlook_history import compare
from ashare_outlook_extensions import SOURCES as EXTENSION_SOURCES, SECTOR_CODES, calculate_extensions, sections_for
from ashare_outlook_supplement import apply_supplement, calculate_supplement, merge_sector_evidence

ROOT = Path(__file__).resolve().parents[2]


def change(rows, key, window):
    usable = [r for r in rows if r.get(key) is not None]
    return (float(usable[-1][key]) / float(usable[-1 - window][key]) - 1) * 100 if len(usable) > window else None


def historical_section(history):
    rows = {r["code"]: r for r in history["spring_2021"]["rows"]}
    panels = {r["date"]: r for r in history["panels"]}
    from ashare_outlook_content import p
    return {"id": "history", "title": "历史对照：领涨股见顶不等于牛市结束",
            "verdict": "2021是错位见顶与风格接力；当前更广泛受损，但2020说明全面均线失守也不能单独确认转熊。",
            "paragraphs": [
        p("计算", f"以2021年春节前最后交易日2月10日收盘为共同基准，到3月9日茅台下跌{abs(rows['600519']['spring_to_march_pct']):.2f}%、沪深300下跌{abs(rows['sh000300']['spring_to_march_pct']):.2f}%；到年底，沪深300仍下跌{abs(rows['sh000300']['spring_to_end_pct']):.2f}%，中证500却上涨{rows['sh000905']['spring_to_end_pct']:.2f}%、中证1000上涨{rows['sh000852']['spring_to_end_pct']:.2f}%。全年涨跌和春节后涨跌使用不同起点，不能混用。茅台为未复权价格，不含分红。", "csi2021", "moutai2021"),
        p("计算", f"逐日核验2021年的日内高点：茅台与沪深300在2月18日，中证500在{rows['sh000905']['peak_date']}，中证1000在{rows['sh000852']['peak_date']}，全指在{rows['sh000985']['peak_date']}。所以‘年底才结束’只能描述部分风格和全市场后段，不是所有资产有同一天牛熊分界；这些终点是事后观察，不能拿年底信息回写春节判断。", "csi", "moutai2021"),
        p("计算", f"2021年3月9日虽然五指数全在MA60下方，却有{panels['2021-03-09']['above_ma250_count']}/5仍高于MA250；9月30日也有{panels['2021-09-30']['above_ma250_count']}/5高于MA250，中证500和1000继续承接。当前为0/5，且这两条指数自身都在MA60/250下方。小盘跌得比大盘少只是相对抗跌，不等于绝对上涨的新接力。宽基只是参与度代理，不能据此说每个行业都没有机会。", "csi"),
        p("事实", "2021年信用已经减速：6月社融存量同比11%，比上年末低2.3pp，年末为10.3%；7月和12月又各降准0.5pp。信用放缓与局部牛市延续可以并存，降准也不是牛市保证。宏观通常改变约束和行业分配，不能单独当即时牛熊开关；旧新M1口径不可跨期比绝对差值。官方报告及年度汇编的发布日期晚于所属期，这里只作机制解释。", "pbc2021q2", "pbc2021tsf", "pbc2021policy"),
        p("计算", "反例必须一起列：2020年3月23日五宽基也全部低于MA60/250，随后重新上涨；2007、2015及2018则在随后区间跨风格下行。2022年4至6月和2024年春季的强反弹，仍要与之后的结果一起看，不能把熊市中途反弹切成新牛市。下表日期为事后描述性区间，不是统一持有期收益比较、买卖点或历史拟合概率。", "csi"),
        p("判断", "2020外部冲击后，美联储紧急宽松；2022进入加息周期。当前外部名义/实际利率和能源压力与2020不同，不能仅凭类似跌幅复制修复速度。但2021即使信用走弱仍有中小盘接力，又说明宏观偏弱不能直接证明所有A股机会结束。价格扩散、是否有接力、资金约束和盈利分布要联合比较，不能只找一个相似年份。", "fed2020", "fed2022", "dgs10", "dfii10", "iea"),
        p("判断", "修订结论：目前可以确认短中期全市场趋势受损，不能确认本轮大牛市已经结束；与2021相比，尚未看到指数层面的强接力，与2022全面转弱相比，五条年线仍上行、多数7月低点未破。下一步区分三条路径：旧主线下跌但新风格绝对走强，是接力；全市场暂跌后重新站稳，是牛市修复；多数风格持续更低高低点、反弹无接力并伴资金/盈利恶化，才更支持全面转熊。研究建议按目标指数适配，不因茅台式下跌停掉所有机会，也不因为仍可能是牛市而忽略风险。"),
    ]}


def build(snapshot, external, snapshot_hash, external_hash, history_extra=None, history_hash=None,
          extension_extra=None, extension_hash=None, supplement_folder=None):
    original_cutoff = snapshot["as_of_at"]
    if supplement_folder and (supplement_folder / "cutoff.json").exists():
        review_cutoff = json.loads((supplement_folder / "cutoff.json").read_bytes())["as_of_at"]
        if review_cutoff < original_cutoff:
            raise ValueError("Review cutoff cannot precede the source snapshot")
        snapshot, external, history_extra, extension_extra = copy.deepcopy((snapshot, external, history_extra, extension_extra))
        for item in (snapshot, external, history_extra, extension_extra):
            if item is not None:
                item["as_of_at"] = review_cutoff
    analysis = calculate(snapshot)
    data = snapshot["data"]
    cutoff = snapshot["as_of_at"]
    if external["as_of_at"] != cutoff:
        raise ValueError("Evidence cutoffs must match")
    indexes = analysis["indexes"]
    if len({r["source_date"] for r in indexes}) != 1:
        raise ValueError("Index comparison needs a common source date")
    macro = data["macro_daily"][-1]
    liquidity = data["bank_liquidity"][-1]
    yields = data["us_yields"][-1]
    credit = data["us_credit"][-1]
    precious = [{**row, "source_url": external["evidence"]["sge"]["url"],
                 "note": external["evidence"]["sge"]["availability_note"]}
                for row in external["evidence"]["sge"]["recent"]]
    global_rows = []
    for code in ("ACWI_NAV", "EFA_NAV", "EEM_NAV", "KOSPI", "BRENT", "COPPER_HG"):
        rows = [r for r in data["global_assets"] if r["asset_code"] == code]
        last = rows[-1]
        global_rows.append({"asset_code": code, "name": last["asset_name"], "value": last["close_value"],
                            "source_date": last["source_date"], "available_at": last["available_at"],
                            "change_10obs_pct": change(rows, "close_value", 10),
                            "change_20obs_pct": change(rows, "close_value", 20),
                            "source": last["data_source"], "source_url": last["source_url"],
                            "note": "同序列有效观测数，不是自然日；NAV非含分红总回报。"})
    for code in ("sp500", "vix"):
        raw = external["evidence"][code]
        global_rows.append({"asset_code": code.upper(), "name": "标普500" if code == "sp500" else "VIX",
                            "value": raw["latest"]["value"], "source_date": raw["latest"]["date"],
                            "available_at": None, "change_10obs_pct": change(raw["recent"], "value", 10),
                            "change_20obs_pct": change(raw["recent"], "value", 20),
                            "source": "FRED" if code == "sp500" else "Cboe", "source_url": raw["url"],
                            "note": raw["availability_note"]})
    fx = []
    for code in ("UDI", "USDCNH", "USDJPY"):
        rows = [r for r in data["fx"] if r["symbol_code"] == code]
        fx.append({"code": code, "name": rows[-1]["symbol_name"], "value": rows[-1]["latest_price"],
                   "source_date": rows[-1]["trade_date"], "source": rows[-1]["data_source"],
                   "change_20obs_pct": change(rows, "latest_price", 20),
                   "note": "最新为盘中快照，不是日K最终收盘；来源未保存逐笔发布时间。"})
    valuation = []
    for code, field in (("sh000300", "hs300_pe_ttm"), ("sh000852", "csi1000_pe_ttm")):
        index = next(r for r in indexes if r["index_code"] == code)
        pe = float(macro[field])
        valuation.append({"index_code": code, "index_name": index["index_name"], "pe_ttm": pe,
                          "earnings_yield_pct": 100 / pe,
                          "equity_bond_spread_pp": 100 / pe - float(macro["cn_gov_bond_10y_yield_pct"]),
                          "source_date": macro["trade_date"],
                          "stress": [{"pe_change_pct": p, "eps_change_pct": e,
                                      "value": index["close"] * (1 + p / 100) * (1 + e / 100)}
                                     for p, e in ((-10, 0), (-20, 0), (-10, -10), (-20, -10))]})
    labels = {"m1_yoy": "M1同比（新口径）", "m2_yoy": "M2同比", "tsf_stock_yoy": "社融存量同比",
              "core_cpi_yoy": "核心CPI同比", "cpi_yoy": "CPI同比", "ppi_yoy": "PPI同比",
              "industrial_profit_ytd_yoy": "工业企业利润累计同比"}
    selected = []
    for key, name in labels.items():
        rows = [r for r in data["monthly_macro"] if r["series_key"] == key]
        if rows:
            latest = max(rows, key=lambda r: (r["period_end"], r["available_at"]))
            selected.append({**latest, "name": name})
    history = compare(snapshot, history_extra) if history_extra else None
    sections = copy.deepcopy(SECTIONS)
    if history:
        sections.insert(1, historical_section(history))
    if supplement_folder:
        extension_extra = merge_sector_evidence(extension_extra, supplement_folder)
    extensions = calculate_extensions(snapshot, extension_extra, history) if extension_extra and history else None
    if extensions:
        additions = sections_for(extensions)
        sections = [additions[0], *sections, *additions[1:]]
        # Preserve v2 prose elsewhere, but remove the overstrong annual-MA claim.
        history_section = next(s for s in sections if s["id"] == "history")
        history_section["paragraphs"][-1]["text"] = history_section["paragraphs"][-1]["text"].replace(
            "五条年线仍上行、多数7月低点未破", "多数7月低点未破且银行资金和已披露盈利仍有韧性；年线仅微升是滞后弱证据")
        regime_section = next(s for s in sections if s["id"] == "regime")
        regime_section["paragraphs"][2]["text"] = "不能直接判定多年熊市已确认：多数7月低点未失守，银行资金没有紧张，上市公司利润和现金流总量仍改善。但年线近20日仅微升，不能作为牛市延续的强证据；月度宏观也可能落后于价格。当前更适合转弱观察，不是健康牛市的无条件低吸环境。"
        bottom_section = next(s for s in sections if s["id"] == "bottom")
        bottom_section["paragraphs"][1]["text"] = "中证1000按约7200、6700、6300附近三层观察，避免将7193至7247等窄区间误解为精准预测。前两层来自已发生低点及算术压力，第三只是30%压力刻度；它们不是买入指令，恐慌可能穿透。沪深3004478已失守，不能继续当下方支撑。"
    report = {
        "version": "ashare-outlook-2026-10-04-v3" if extensions else "ashare-outlook-2026-10-04-v2" if history else "ashare-outlook-2026-10-04-v1", "title": "A股：牛市是否还在，下一轮机会在哪里",
        "as_of_at": cutoff + "+08:00", "market_date": indexes[0]["source_date"],
        "research_only": True, "live": False,
        "summary": [
            {"label": "当前阶段", "value": "全市场趋势受损 · 转弱观察", "detail": "不再是单一主线调整；盈利与资金仍有韧性，但尚未确认广泛接力或多年熊市。"},
            {"label": "下跌低点", "value": "观察锚 + 条件压力区间", "detail": "中证1000约7200、6700、6300附近，分别说明价格锚与压力假设，不给必到点。"},
            {"label": "后续大行情", "value": "仍有可能 · 需要接力", "detail": "价格修复、信用活化与盈利扩散，外部能源/真实利率压力缓解。"},
        ],
        "indexes": indexes, "valuation": valuation, "global_markets": global_rows, "fx": fx,
        "precious_metals": precious,
        "financing": analysis["financing"], "monthly_macro": selected,
        "domestic": {"china_10y_pct": macro["cn_gov_bond_10y_yield_pct"], "date": macro["trade_date"],
                     "liquidity_score": liquidity["liquidity_tightness_score"], "liquidity_state": liquidity["liquidity_state"],
                     "fdr007_pct": liquidity["fdr007_pct"], "policy_rate_pct": liquidity["reverse_repo_7d_policy_rate_pct"]},
        "external_rates": {"us_10y_pct": yields["yield_10y"], "us_real_10y_pct": yields["yield_real_10y"],
                           "source_date": yields["trade_date"], "us_hy_oas_pct": credit["high_yield_oas"],
                           "credit_date": credit["trade_date"], "japan": external["evidence"]["jgb_current"]["latest"]},
        "sections": sections, "history_comparison": history, "extensions": extensions, "watchlist": WATCHLIST,
        "sources": [{"id": id_, "title": title, "url": url, "published_at": date, "note": note}
                    for id_, title, url, date, note in SOURCES + (EXTENSION_SOURCES if extensions else [])],
        "quality": [
            "这是日期固定的研究版本，不是自动日更预警，也不产生交易或通知。",
            "A股停在9月30日是国庆休市，不是把10月假期误当成行情漏采。",
            "沪深300/1000最新完整风险总分缺失，融资窗口和集中度空值不当作零或安全。",
            "ETF NAV到9月29日，油现货到9月22日；上金所金银到9月30日，美元黄金8月末仅作背景。",
            "中间价旧数据未用于当前判断；人民币金银合约不冒充美元现货，未核验铁矿/煤炭日线不补造数值。",
            "信用利差库内available_at早于当前FRED公开更新时间；当前研究已可见，历史实时回测未获此项认证。",
            "当前快照用于复算，不是所有日频数据历史首次发布/修订版本的完整档案。",
            "指数回溯历史、存活/指数规则变化及未计分红影响历史类比；不把样本频率当未来保证。",
            "扩展研究融资5/20日按9月29日连续交易日复算，不回填生产看板9月30日空值。",
            "行业只覆盖六个代表；目标指数可比首发财报、ETF份额长历史及AH同公司长历史仍不完整，不声称联合模型认证完成。",
            "情绪策略对照截至9月24日，61日缺原始情绪，含默认50及图像估算；不是完整真实实盘回测。",
        ],
        "methods": analysis["methods"], "missing_dashboard": analysis["missing_dashboard"],
        "provenance": {"snapshot_sha256": snapshot_hash, "external_sha256": external_hash, "history_snapshot_sha256": history_hash,
                       "extension_snapshot_sha256": extension_hash,
                       "original_snapshot_as_of_at": original_cutoff,
                       "snapshot_command": "python scripts/research/ashare_outlook_snapshot.py --as-of 2026-10-04T04:00:00 --output runtime/reports/ashare_outlook/2026-10-04/snapshot.json",
                       "build_command": "python scripts/research/build_ashare_outlook.py", "production_writes": False},
    }
    if supplement_folder:
        calendar = sorted({r["trade_date"] for r in snapshot["data"]["indexes"]
                           if r["index_code"] == "sh000985" and r["trade_date"] <= report["market_date"]})
        evidence = calculate_supplement(supplement_folder, calendar, cutoff, report["market_date"],
                                        extension_extra["data"]["indexes"], SECTOR_CODES, data["global_assets"])
        report = apply_supplement(report, evidence)
    return report


def markdown(report):
    source_map = {s["id"]: s for s in report["sources"]}
    lines = [f"# {report['title']}", "", f"截至：{report['as_of_at']}；A股来源日：{report['market_date']}。", "",
             "研究用途，不构成确定价格预测、买卖指令或投资收益保证。", ""]
    for item in report["summary"]:
        lines.extend([f"## {item['label']}：{item['value']}", item["detail"], ""])
    lines += ["## 宽基价格证据", "|指数|收盘|MA60|MA120|MA250|本轮高点回撤|20日涨跌|", "|---|---:|---:|---:|---:|---:|---:|"]
    for r in report["indexes"]:
        lines.append(f"|{r['index_name']}|{r['close']:.2f}|{r['ma60']:.2f}|{r['ma120']:.2f}|{r['ma250']:.2f}|{r['cycle_drawdown_pct']:.2f}%|{r['return_20d_pct']:.2f}%|")
    for section in report["sections"]:
        lines += ["", f"## {section['title']}", section["verdict"], ""]
        for para in section["paragraphs"]:
            citations = " ".join(f"[{source_map[k]['title']}]({source_map[k]['url']})" for k in para["sources"])
            lines += [f"**{para['kind']}** {para['text']} {citations}", ""]
        for t in section.get("tables", []):
            lines += [f"### {t['title']}", "|" + "|".join(t["columns"]) + "|", "|" + "|".join("---" for _ in t["columns"]) + "|"]
            lines += ["|" + "|".join(cell.replace("|", "/") for cell in row) + "|" for row in t["rows"]]
            lines += [t["note"], ""]
        if section["id"] == "history":
            h = report["history_comparison"]
            fmt = lambda v: "数据缺失" if v is None else f"{v:+.2f}%"
            lines += ["### 2021年错位见顶与接力", h["spring_2021"]["note"], "",
                      "|资产|全年涨跌|春节前至3月9日|春节前至年底|3月9日至年底|全年日内高点日期|", "|---|---:|---:|---:|---:|---|"]
            for r in h["spring_2021"]["rows"]:
                lines.append(f"|{r['name']}|{fmt(r.get('year_return_pct'))}|{fmt(r.get('spring_to_march_pct'))}|{fmt(r.get('spring_to_end_pct'))}|{fmt(r.get('march_to_end_pct'))}|{r.get('peak_date', '缺失')}|")
            lines += ["", "### 相同口径的宽基参与状态", "每个分母均为五条宽基，不是个股广度。", "",
                      "|交易日|MA60上方|MA250上方|MA250仍上行|近20日上涨|", "|---|---:|---:|---:|---:|"]
            for r in h["panels"]:
                lines.append(f"|{r['date']}|{r['above_ma60_count']}/5|{r['above_ma250_count']}/5|{r['rising_ma250_count']}/5|{r['positive_20d_count']}/5|")
            lines += ["", "### 多轮次情境对照", "不等长的事后区间，只展示已发生路径，不能按收益排序推断下一轮概率。", "",
                      "|案例|共同起止|上证|全指|沪深300|中证500|中证1000|", "|---|---|---:|---:|---:|---:|---:|"]
            for case in h["cases"]:
                lines.append(f"|{case['title']}|{case['start']}至{case['end']}|" + "|".join(fmt(r['return_pct']) for r in case['rows']) + "|")
                if case["rebound_end"]:
                    lines.append(f"|其中：反弹阶段|{case['start']}至{case['rebound_end']}|" + "|".join(fmt(r['return_pct']) for r in case['rebound_rows']) + "|")
            lines += ["", "### 五宽基同步失守后的全部事件", h["synchronized_breaks"]["method"], h["synchronized_breaks"]["note"], "",
                      "|触发日|20日期末|20日最低价变化|60日期末|60日最低价变化|120日期末|120日最低价变化|", "|---|---:|---:|---:|---:|---:|---:|"]
            for r in h["synchronized_breaks"]["events"]:
                lines.append(f"|{r['date']}|" + "|".join(fmt(r[f'{key}_{w}d_pct']) for w in (20, 60, 120) for key in ('return', 'lowest')) + "|")
            lines += ["", *[f"- {v}" for v in h["limitations"]], ""]
    lines += ["## 各指数观察锚与压力刻度", "压力刻度不是底部预测；原值保留在JSON，以下仅显示到两位小数。", ""]
    for r in report["indexes"]:
        lines += [f"### {r['index_name']}", "|类别|日期/压力假设|点位|距当前收盘|", "|---|---|---:|---:|"]
        for a in r["anchors"]:
            lines.append(f"|{a['label']} {a.get('status', '')}|{a['date']}|{a['value']:.2f}|{a['distance_pct']:.2f}%|")
        for a in r["stress_levels"]:
            lines.append(f"|算术压力|高点回撤{a['peak_drawdown_pct']}%|{a['value']:.2f}|{a['distance_pct']:.2f}%|")
        lines += ["", "|后续窗口|完整事件数|最低价变化中位|最低价变化Q25/Q75|期末收益中位|最低价较事件低逾10%数|", "|---|---:|---:|---|---:|---:|"]
        for h in r["historical_breaks"]["summaries"]:
            lines.append(f"|{h['window']}交易日|{h['sample_count']}|{h['worst_median_pct']:.2f}%|{h['worst_q25_pct']:.2f}% / {h['worst_q75_pct']:.2f}%|{h['return_median_pct']:.2f}%|{h['loss_over_10pct_count']}|")
    lines += ["", "## 全球市场比较", "变化按同序列有效观测数；NAV非含分红总回报。不同来源日不冒充同日。", "",
              "|资产|原值|近10观测变化|近20观测变化|来源日|", "|---|---:|---:|---:|---|"]
    for g in report["global_markets"]:
        value = "仅比较同序列变动" if g["asset_code"] == "COPPER_HG" else f"{g['value']:.4f}"
        lines.append(f"|{g['name']}|{value}|{g['change_10obs_pct']:.2f}%|{g['change_20obs_pct']:.2f}%|{g['source_date']}|")
    lines += ["", "## 外汇盘中快照", "|指标|原值|近20观测变化|来源日|", "|---|---:|---:|---|"]
    for fx in report["fx"]:
        lines.append(f"|{fx['name']}|{fx['value']:.4f}|{fx['change_20obs_pct']:.2f}%|{fx['source_date']}|")
    lines += ["", "## 官方人民币贵金属合约", "|合约|收盘原值|单位|交易日|", "|---|---:|---|---|"]
    for metal in report["precious_metals"]:
        lines.append(f"|{metal['contract']}|{metal['value']}|{metal['unit']}|{metal['date']}|")
    lines += ["", "## 盈利与估值压力敏感性", "假设不是公允价值，PE与EPS变化分别列示。", "",
              "|指数|PE变化|EPS变化|条件点位|", "|---|---:|---:|---:|"]
    for v in report["valuation"]:
        for stress in v["stress"]:
            lines.append(f"|{v['index_name']}|{stress['pe_change_pct']}%|{stress['eps_change_pct']}%|{stress['value']:.2f}|")
    lines += ["", "## 情景检查清单", "|模块|当前基线|改善条件|恶化条件|", "|---|---|---|---|"]
    for w in report["watchlist"]:
        lines.append(f"|{w['topic']}|{w['baseline']}|{w['improves']}|{w['worsens']}|")
    lines += ["", "## 数据边界", *[f"- {q}" for q in report["quality"]], "", "## 来源与日期"]
    for s in report["sources"]:
        lines.append(f"- [{s['title']}]({s['url']})；{s['published_at']}；{s['note']}")
    lines += ["", "## 复算指纹", f"数据库快照 SHA256：`{report['provenance']['snapshot_sha256']}`", f"外部快照 SHA256：`{report['provenance']['external_sha256']}`",
              f"扩展快照 SHA256：`{report['provenance']['extension_snapshot_sha256']}`", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "runtime/reports/ashare_outlook/2026-10-04")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/research")
    args = parser.parse_args()
    raw, ext = (args.input / "snapshot.json").read_bytes(), (args.input / "external.json").read_bytes()
    hist = (args.input / "history_snapshot.json").read_bytes() if (args.input / "history_snapshot.json").exists() else None
    extension = (args.input / "extension_snapshot.json").read_bytes() if (args.input / "extension_snapshot.json").exists() else None
    report = build(json.loads(raw), json.loads(ext), hashlib.sha256(raw).hexdigest(), hashlib.sha256(ext).hexdigest(),
                   json.loads(hist) if hist else None, hashlib.sha256(hist).hexdigest() if hist else None,
                   json.loads(extension) if extension else None, hashlib.sha256(extension).hexdigest() if extension else None,
                   args.input / "gap_backfill" if (args.input / "gap_backfill/local.json").exists() else None)
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / "ashare_outlook_2026-10-04.json"
    if path.exists():
        prior = json.loads(path.read_bytes())
        if prior["version"] != report["version"]:
            archive = args.output / f"{prior['version']}.json"
            if not archive.exists():
                archive.write_bytes(path.read_bytes())
                (args.output / f"{prior['version']}.md").write_bytes((args.output / "ASHARE_OUTLOOK_2026-10-04.md").read_bytes())
    path.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n", encoding="utf-8")
    (args.output / "ASHARE_OUTLOOK_2026-10-04.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"report": str(path), "bytes": path.stat().st_size, "sections": len(report["sections"]),
                      "sources": len(report["sources"]), "snapshot": report["provenance"]["snapshot_sha256"]}))


if __name__ == "__main__":
    main()
