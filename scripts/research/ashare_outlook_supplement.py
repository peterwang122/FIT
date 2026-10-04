"""Observed gap fills and revised conclusions, isolated from live trading models."""

import copy
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ashare_outlook_content import p
from ashare_outlook_extensions import fmt, table
from ashare_outlook_gap_backfill import number

WB_URL = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
AH_URL = "https://origin-www.hsi.com.hk/data/eng/indexes/01044.00/chart.json"
SOURCES = [
    ("industry_rules", "中证：全指行业优选编制方案", "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/20240510102751-000986_cn.pdf", "2024-05", "与全行业指数分开；旧金融地产为合并行业，不凑成11项"),
    ("ah_history", "恒生：AH溢价官方5年日线", AH_URL, "2026-10-02", "官方公开图表实际日线；9月30日124.53，10月2日126.77单列为假期变化"),
    ("jgb_history", "日本财务省：国债收益率历史", "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv", "2026-09-30", "各期限起点不同，不补造早期10年利率"),
    ("jgb_release", "日本财务省：收益率方法与发布时点", "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/qa.htm", None, "日本15时市场收盘值，下一日本工作日9:30发布；不冒充当日提前可见"),
    ("wb_history", "世界银行：月度商品价格历史工作簿", WB_URL, "2026-10-02", "1960起月度、美元名义口径；当前修订版本仅诊断，非完整首次发布档案"),
    ("pbc_tools", "人民银行：8月实际工具投放", "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/5727710/2026090214213398506/index.html", "2026-09-02T17:00:00+08:00", "按官方八项目分别列出；银行流动性不是股票购买金额"),
    ("pbc_omo", "人民银行：9月30日公开市场操作", "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/125475/2026093008493852899/index.html", "2026-09-30T09:20:30+08:00", "隔夜8335亿元，7天0；不把投放毛额当净额，未核验到期不猜"),
    ("turnover_top5", "Peakstone：前5%成交集中度", "https://panel.peakstone-labs.com/", "2026-09-30T22:00:00+08:00", "既有商业来源的MA5值，不冒充官方原值或未平滑比例"),
    ("margin_release", "深交所：融资数据开市前披露规则", "https://docs.static.szse.cn/www/lawrules/rule/trade/business/margin/W020230217568325595241.pdf", "2023-02-17", "第五章5.1：下一交易日开市前公布前一交易日数据；正常T-1可用，不要求T日同日发布"),
]


def load(folder, name):
    return json.loads((folder / (name + ".json")).read_bytes())


def merge_sector_evidence(extra, folder):
    result = copy.deepcopy(extra)
    rows = load(folder, "sectors")["rows"]
    added = [r for r in rows if r["index_code"] in ("sh000988", "sh000990")]
    lookup = {(r["index_code"], r["trade_date"]): r for r in result["data"]["indexes"]}
    for row in added:
        key = (row["index_code"], row["trade_date"])
        if key in lookup and lookup[key]["close_price"] != row["close_price"]:
            raise ValueError("Conflicting sector close; do not overwrite existing evidence")
        lookup.setdefault(key, row)
    result["data"]["indexes"] = sorted(lookup.values(), key=lambda r: (r["index_code"], r["trade_date"]))
    return result


def parse_ah(payload):
    if payload["indexCode"] != "01044.00":
        raise ValueError("Wrong AH index")
    result = {}
    for timestamp, raw in payload["indexLevels-5y"]:
        day = datetime.fromtimestamp(timestamp / 1000, tz=ZoneInfo("Asia/Hong_Kong")).date().isoformat()
        value = number(raw)
        if value is None or value <= 0:
            raise ValueError("Invalid AH level")
        if day in result and result[day] != value:
            raise ValueError("Conflicting AH date")
        result[day] = value
    return [{"date": day, "value": v} for day, v in sorted(result.items())]


def change(series, key, window, difference=False):
    if len(series) <= window:
        return None
    a, b = float(series[-1-window][key]), float(series[-1][key])
    return b - a if difference else (b / a - 1) * 100


def refreshed_global_metrics(payload, brent, existing, as_of):
    result = []
    for code in ("ACWI_NAV", "EFA_NAV", "EEM_NAV", "BRENT"):
        archive = brent if code == "BRENT" else payload["assets"][code]
        retrieved = archive["retrieved_at"]
        if retrieved > as_of:
            raise ValueError("Global refresh retrieved after review cutoff")
        published = archive["available_at"] if code == "BRENT" else retrieved
        if published > as_of:
            raise ValueError("Unreleased global refresh")
        raw = archive["observations"] if code == "BRENT" else archive["rows"]
        lookup = {r["source_date"]: r for r in existing if r["asset_code"] == code}
        fresh = {}
        for row in raw:
            day = row["source_date"]
            value = number(row["close_value"])
            if day > as_of[:10] or value is None or value <= 0:
                raise ValueError("Invalid global refresh observation")
            if day in fresh and fresh[day] != value:
                raise ValueError("Conflicting global refresh dates")
            fresh[day] = value
            # A current revision may replace the research copy, never the production archive.
            lookup[day] = {"source_date": day, "close_value": value}
        rows = [r for day, r in sorted(lookup.items()) if day <= as_of[:10]]
        last = rows[-1]
        result.append({"asset_code": code, "source_date": last["source_date"], "value": last["close_value"],
                       "available_at": published, "retrieved_at": retrieved, "source_url": archive["url"],
                       "change_10obs_pct": change(rows, "close_value", 10),
                       "change_20obs_pct": change(rows, "close_value", 20),
                       "first_publication_time_verified": False,
                       "current_version_timestamp_verified": code == "BRENT",
                       "availability_note": "当前FRED修订版更新时间，非每条观测首次发布时间" if code == "BRENT" else
                       "本次下载实测已可见时间，官方首发时分未核验；不采用解析器推定的次日08:00",
                       "observations": len(rows)})
    return result


def sector_case_returns(rows, codes, cutoff):
    grouped = defaultdict(dict)
    for row in rows:
        if row["index_code"] in codes and row["trade_date"] <= cutoff:
            grouped[row["index_code"]][row["trade_date"]] = float(row["close_price"])
    result = []
    for code in codes:
        series = grouped[code]
        values = []
        for start, end in (("2021-02-10", "2021-03-09"), ("2021-02-10", "2021-12-31"),
                           ("2021-03-09", "2021-12-31")):
            values.append((series[end]/series[start]-1)*100 if start in series and end in series else None)
        result.append({"code": code, "returns": values})
    return result


def etf_metrics(payload, calendar, cutoff):
    series = defaultdict(dict)
    for row in payload["rows"]:
        if row["date"] > cutoff:
            continue
        if row["date"] not in calendar or number(row["shares_10k"]) is None or row["shares_10k"] <= 0:
            raise ValueError("Invalid ETF observation")
        key = row["date"]
        existing = series[row["code"]].get(key)
        if existing and existing["shares_10k"] != row["shares_10k"]:
            raise ValueError("Conflicting ETF shares")
        series[row["code"]][key] = row
    result = []
    for code, by_day in sorted(series.items()):
        rows = sorted(by_day.values(), key=lambda r: r["date"])
        last = rows[-1]
        windows = []
        i = calendar.index(last["date"])
        for window in (5, 20, 60):
            days = calendar[max(0, i-window):i+1]
            complete = len(days) == window + 1 and all(day in by_day for day in days)
            delta = last["shares_10k"] - by_day[days[0]]["shares_10k"] if complete else None
            windows.append({"sessions": window, "start": days[0], "end": last["date"],
                "delta_shares_10k": delta, "change_pct": delta / by_day[days[0]]["shares_10k"] * 100 if complete else None,
                "missing_dates": [d for d in days if d not in by_day]})
        periods = []
        for start, end in (("2021-02-10", "2021-03-09"), ("2021-02-10", "2021-12-31"),
                           ("2023-12-29", "2024-06-28"), ("2024-09-18", "2026-09-30")):
            a, b = by_day.get(start), by_day.get(end)
            periods.append({"start": start, "end": end,
                "change_pct": (b["shares_10k"]/a["shares_10k"]-1)*100 if a and b else None})
        result.append({"code": code, "name": last["name"], "start": rows[0]["date"], "date": last["date"],
                       "observations": len(rows), "shares_10k": last["shares_10k"], "windows": windows, "periods": periods})
    return result


def policy_metrics(rows, as_of):
    grouped = defaultdict(dict)
    for row in rows:
        if row["published_at"] > as_of or row["coverage_status"] != "official_complete":
            continue
        if row["net_injection_cny"] is None:
            raise ValueError("Incomplete official tool net value")
        if row["injection_cny"] is not None and row["withdrawal_cny"] is not None and abs(
                row["injection_cny"] - row["withdrawal_cny"] - row["net_injection_cny"]) > .01:
            raise ValueError("Tool net identity failed")
        # The same reverse_repo type appears in two distinct official lines.
        key = row["tool_name"]
        if key in grouped[row["period_end"]]:
            raise ValueError("Duplicate monthly tool line")
        grouped[row["period_end"]][key] = row
    return [{"period_end": day, "published_at": max(r["published_at"] for r in items.values()),
             "line_count": len(items), "net_cny": sum(r["net_injection_cny"] for r in items.values()),
             "components": list(items.values())} for day, items in sorted(grouped.items())]


def parse_worldbank(path):
    import pandas as pd
    frame = pd.read_excel(path, sheet_name="Monthly Prices", header=None)
    updated = next(str(v) for v in frame.iloc[:, 0] if str(v).startswith("Updated on "))
    release_date = datetime.strptime(updated.removeprefix("Updated on "), "%B %d, %Y").date().isoformat()
    definitions = pd.read_excel(path, sheet_name="Description", header=None)
    iron_note = next(str(r.iloc[1]) for _, r in definitions.iterrows() if str(r.iloc[1]).startswith("Iron ore, spot in US dollar"))
    wanted = {"Crude oil, Brent": "Brent", "Crude oil, WTI": "WTI", "Coal, Australian": "澳大利亚煤",
              "Coal, South African **": "南非煤", "Natural gas, Europe": "欧洲天然气",
              "Natural gas, US": "美国天然气", "Copper": "铜", "Iron ore, cfr spot": "铁矿石",
              "Aluminum": "铝", "Nickel": "镍", "Gold": "黄金", "Silver": "白银"}
    header = next(i for i in range(len(frame)) if "Copper" in frame.iloc[i].values)
    result = []
    for column, field in enumerate(frame.iloc[header]):
        if field not in wanted:
            continue
        rows = []
        for _, row in frame.iloc[header+2:].iterrows():
            period = str(row.iloc[0])
            if not re.fullmatch(r"\d{4}M\d{2}", period):
                continue
            raw = str(row.iloc[column]).strip()
            if raw in ("…", "...", "nan", "..", ""):
                continue
            value = number(raw)
            if value is None or value <= 0:
                raise ValueError("Invalid World Bank price")
            rows.append({"period": period[:4] + "-" + period[-2:], "value": value})
        unit = str(frame.iloc[header+1, column])
        result.append({"name": wanted[field], "field": field, "unit": unit,
                       "definition_note": iron_note if wanted[field] == "铁矿石" else None, "rows": rows})
    if len(result) != len(wanted):
        raise ValueError("World Bank required columns missing")
    return {"published_date": release_date, "first_publication_times_verified": False,
            "historical_revision_archive_complete": False, "series": result,
            "raw_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def calculate_supplement(folder, calendar, as_of, market_date, sector_rows, sector_codes, global_rows):
    local = load(folder, "local")
    etf = load(folder, "etf")
    ah_rows = [r for r in parse_ah(load(folder, "ah")) if r["date"] <= as_of[:10]]
    ah_at_market = [r for r in ah_rows if r["date"] <= market_date]
    ah = {"start": ah_rows[0]["date"], "observations": len(ah_rows), "latest": ah_rows[-1],
          "market_day": ah_at_market[-1], "change_20d_points": change(ah_at_market, "value", 20, True),
          "change_60d_points": change(ah_at_market, "value", 60, True),
          "holiday_change_points": ah_rows[-1]["value"] - ah_at_market[-1]["value"]}
    jgb_rows = [r for r in load(folder, "jgb")["rows"] if r["date"] <= as_of[:10] and r.get("10Y") is not None]
    jgb_market = [r for r in jgb_rows if r["date"] <= market_date]
    jgb = {"start": jgb_rows[0]["date"], "observations": len(jgb_rows), "latest": jgb_rows[-1],
           "change_20d_bp": change(jgb_rows, "10Y", 20, True)*100,
           "change_60d_bp": change(jgb_rows, "10Y", 60, True)*100,
           "market_day": jgb_market[-1], "annual_reference": []}
    for year in (2007, 2013, 2015, 2018, 2020, 2021, 2022, 2024, 2025):
        part = [r for r in jgb_rows if r["date"].startswith(str(year))]
        if part:
            jgb["annual_reference"].append({"year": year, "date": part[-1]["date"], "yield_10y": part[-1]["10Y"]})
    monthly = policy_metrics(local["tools"], as_of)
    omo = [r for r in local["omo"] if r["operation_date"] == market_date and r["published_at"] <= as_of]
    concentration = [r for r in local["concentration"] if r["trade_date"] <= market_date and r["available_at"] <= as_of]
    margin = load(folder, "margin_official")
    sse_row = next((r for r in margin["SSE"]["result"] if r["opDate"] == market_date.replace("-", "")), None)
    if sse_row and any(sse_row[k] is None for k in ("rzmre", "rzche", "rzye")):
        raise ValueError("Incomplete SSE margin row")
    financing_partial = {"date": market_date, "exchange": "SSE", "balance_cny": sse_row["rzye"],
        "net_buy_cny": sse_row["rzmre"]-sse_row["rzche"], "SZSE_complete": False} if sse_row else None
    worldbank = parse_worldbank(folder / "raw/worldbank-monthly.xlsx")
    # A date-only publication is conservatively available after that day, not at period end.
    if worldbank["published_date"] >= as_of[:10]:
        raise ValueError("World Bank file not yet conservatively available")
    wb_current = [{"name": r["name"], "unit": r["unit"], "start": r["rows"][0]["period"],
        "observations": len(r["rows"]), "period": r["rows"][-1]["period"], "value": r["rows"][-1]["value"],
        "change_1m_pct": change(r["rows"], "value", 1), "change_3m_pct": change(r["rows"], "value", 3),
        "definition_note": r["definition_note"]} for r in worldbank["series"]]
    wb_history = []
    for start, end in (("2008-06", "2008-12"), ("2015-06", "2015-12"), ("2020-02", "2020-04"),
                       ("2021-02", "2021-12"), ("2022-02", "2022-06")):
        values = {}
        for r in worldbank["series"]:
            part = {v["period"]: v["value"] for v in r["rows"]}
            incomparable = r["name"] == "铁矿石" and start < "2008-12" <= end
            values[r["name"]] = (part[end]/part[start]-1)*100 if start in part and end in part and not incomparable else None
        wb_history.append({"start": start, "end": end, "changes": values})
    inputs = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(folder.glob("*.json"))}
    refreshed = refreshed_global_metrics(load(folder, "global_refresh"), load(folder, "brent_web"), global_rows, as_of)
    return {"as_of_at": as_of, "market_date": market_date, "research_only": True,
            "global_refresh": refreshed,
            "sector_2021": sector_case_returns(sector_rows, sector_codes, market_date),
            "etf": etf_metrics(etf, calendar, market_date), "etf_sampling": etf["sampling"], "etf_errors": etf["errors"],
            "ah": ah, "jgb": jgb, "policy_monthly": monthly, "omo": omo,
            "concentration": concentration[-1], "financing_partial": financing_partial,
            "worldbank": {"published_date": worldbank["published_date"], "raw_sha256": worldbank["raw_sha256"],
                          "current": wb_current, "history": wb_history}, "input_sha256": inputs,
            "strict_joint_historical_replay": False,
            "remaining": [
                {"item": "通信、公用事业、房地产行业历史", "status": "来源阻断", "reason": "中证查询403后停止；新浪仅至2016或空，腾讯新行业为空，东方财富连接失败；不拼11行业"},
                {"item": "目标指数首发财报、当时成分及退市样本", "status": "未完成联合面板", "reason": "沪市汇总不能代替500/1000自身可比利润、扣非与现金流"},
                {"item": "ETF 2013至2025逐日及AH 2021年前", "status": "部分覆盖", "reason": "ETF本次月末及指定历史锚点，2026逐日；AH官网公开5年，未获得更早同口径序列"},
                {"item": "宏观首发修订联合档案", "status": "时点认证不足", "reason": "补当前历史不能还原所有当时版本；未经核验只诊断，不声称可执行回测"},
                {"item": "情绪策略61日原始情绪", "status": "来源缺失", "reason": "当前原始表未找到，不用50、插值或图像猜数补成真实值"},
                {"item": "全市场实际回购和股票资金到账", "status": "未取得同口径全量", "reason": "已补央行工具实际使用，但它与公司实际买入不是同一总量"},
                {"item": "2026年8月后60/120日结果", "status": "待验证", "reason": "未来交易窗口尚未走完，不属于采集失败"},
            ]}


def apply_supplement(report, evidence):
    report["version"] = "ashare-outlook-2026-10-04-v5"
    report["supplement"] = evidence
    report["sources"].extend({"id": id_, "title": title, "url": url, "published_at": published, "note": note}
                             for id_, title, url, published, note in SOURCES)
    for source in report["sources"]:
        if source["id"] == "etf_shares":
            source.update(published_at="2026-09-30", note="官方清算份额单位万份；2013起月末及历史锚，2026逐日；首次发布时分未认证")
        if source["id"] == "ah":
            source.update(published_at="2026-10-02", note="已补官方5年图表，替代过期盘中值；港股假期变化与9月30日分开")
        if source["id"] == "jgb":
            source["note"] = "10月1日观测，按官方下一工作日9:30发布；历史首次发布档案未逐条认证"
        if source["id"] in ("acwi", "efa", "eem"):
            source.update(published_at=None, note="官方NAV所属日10月2日；本次10月4日下载已可见，首发时分未核验，假期信息不回贴9月30日")
        if source["id"] == "oil":
            source.update(published_at="2026-10-01T01:18:00+08:00", note="当前FRED版本9月30日12:18 CDT更新，观测最新9月29日113.96美元/桶，下一发布10月7日；不猜9月30日价格")
    for fresh in evidence["global_refresh"]:
        row = next(r for r in report["global_markets"] if r["asset_code"] == fresh["asset_code"])
        row.update({key: fresh[key] for key in ("value", "source_date", "available_at", "source_url", "change_10obs_pct", "change_20obs_pct")})
        row["note"] = fresh["availability_note"] + "；同序列有效观测，不是自然日或含分红总回报，不回贴A股9月30日。"
    sections = {s["id"]: s for s in report["sections"]}
    funding, policy, cross, shock, synthesis = [sections[k] for k in ("stock_funding", "policy_delivery", "cross_listing", "shock_types", "synthesis")]
    etf_table = table("补齐官方ETF份额：申赎，不是现金流", ["ETF", "日末 / 万份", "5日变化 / 万份", "20日变化 / 万份", "60日变化 / 万份", "历史起点 / 观测数"],
        [[r["code"]+" "+r["name"],fmt(r["shares_10k"],"",False),*[fmt(w["delta_shares_10k"],"") for w in r["windows"]],f"{r['start']} / {r['observations']}"] for r in evidence["etf"]],
        "清算后官方原始披露精度，单位万份。2026窗口逐个核验交易日；此前月末采样不冒充逐日。长期份额折算/合并事件尚未逐只认证，因此变化不是认证后的纯申赎现金流；份额×NAV不作为官方现金净流入，也不能识别买入者。")
    etf_history = table("ETF份额历史对照 / 变化百分比", ["ETF", "2021春节至3月9日", "2021春节至年末", "2024上半年", "924起点至当前"],
        [[r["code"],*[fmt(v["change_pct"]) for v in r["periods"]]] for r in evidence["etf"]],
        "分别使用2021-02-10、2021-03-09、2021-12-31、2023-12-29、2024-06-28、2024-09-18和2026-09-30原始份额；缺任一锚保持空。申赎和价格收益不是同一指标。")
    funding["tables"].extend([etf_table, etf_history])
    funding["paragraphs"][4] = p("计算", "四只代表ETF近20和60交易日份额均增加，这是托底的正向证据；近5日则50/500份额下降、300/1000增加，短期方向分化。已补长周期月末与2026逐日记录；长期折算事件尚未逐只认证，因此不将全部份额变化认证成纯申赎。即便份额增加，也不等同全A新增现金购买力，不证明价格已经形成接力。", "etf_shares", "csi")
    partial = evidence["financing_partial"]
    funding["paragraphs"].append(p("事实", f"9月30日研究使用9月29日两市融资，是正常发布滞后的可用输入。9月30日沪市原值另行留档：余额{partial['balance_cny']/1e12:.4f}万亿元，买入减偿还{partial['net_buy_cny']/1e8:.2f}亿元；当天深市未齐，不混成两市指标，也不要求它填齐才能使用T-1证据。", "margin", "szmargin", "margin_release"))
    f = report["extensions"]["financing"]
    funding["tables"].insert(0, table("融资可用日期：正常T-1不算缺失", ["研究交易日", "应使用来源日", "实际来源日", "滞后 / 交易日", "可用状态"],
        [[f["reference_trade_date"],f["expected_source_date"],f["source_date"],str(f["lag_trade_days"]),"可用（正常发布滞后）" if not f["latest_target_missing"] else "数据不完整"]],
        "按真实A股交易日而非昨天自然日取T-1；周末、春节、国庆不顺延造数。5/20日窗口从来源日往前计算，窗口断档仍为缺失。未保存首发时分的观测以次一交易日开市作为保守可用边界，不冒充精确首发时间。"))
    c = evidence["concentration"]
    sections["valuation"]["paragraphs"][2] = p("事实", f"9月30日按T-1口径可用融资来源日为9月29日：约2.5715万亿元，当日净买入-20.48亿元，5/20日累计完整。9月30日前5%成交集中度MA5原值为{c['top5_pct']:.2f}%，22:00可用。旧风险看板总分仍为空且本次未重算，但不能将该存储空值解释成融资证据不可用，也不把全球17.5分当完整总风险低。", "margin", "szmargin", "turnover_top5", "margin_release")
    months = evidence["policy_monthly"]
    latest = months[-1]
    policy["tables"].append(table("央行实际使用：最新完整月份", ["官方项目", "投放 / 亿元", "回笼 / 亿元", "净投放 / 亿元"],
        [[r["tool_name"],fmt(r["injection_cny"]/1e8,"",False),fmt(r["withdrawal_cny"]/1e8,"",False),fmt(r["net_injection_cny"]/1e8,"")] for r in latest["components"]],
        f"所属期{latest['period_end']}，{latest['published_at']}已公布；八项目分别核对投放－回笼。不是股票购买金额。"))
    policy["tables"].append(table("央行工具历史与当前操作", ["所属期 / 操作日", "原值 / 亿元", "发布时间", "含义与限制"],
        [[r["period_end"],fmt(r["net_cny"]/1e8,""),r["published_at"],f"披露{r['line_count']}项目合计，银行系统口径"] for r in months]
        + [[r["operation_date"]+" "+r["tenor_label"],fmt(r["awarded_amount_cny"]/1e8,"",False),r["published_at"],"操作毛额；实际到期未核验，不推算当日净额"] for r in evidence["omo"]],
        "月度数据只有公布后可用；月份未公布不写零。7天零操作为官方明确值，不掩盖同日隔夜操作。"))
    policy["paragraphs"][4] = p("计算", f"实际工具缺口已补入：2025年5月起129条记录，2026年8月八项目净投放合计{latest['net_cny']/1e8:.0f}亿元，其中短期逆回购回笼、其他期限与结构性投放并存。9月30日隔夜8335亿元、7天0亿元。不能仅因月度净回笼就判银行紧张，也不能把隔夜毛额当永久资金或股票净流入；全市场公司实际回购面板仍不完整。", "pbc_tools", "pbc_omo", "bank")
    ah = evidence["ah"]
    cross["paragraphs"][0] = p("事实", f"恒生官方公开图表已补{ah['observations']}个日线点，覆盖{ah['start']}至{ah['latest']['date']}。9月30日AH溢价指数{ah['market_day']['value']:.2f}，其口径下A股相对H股约{ah['market_day']['value']-100:.2f}%溢价；前20/60观测变化分别{ah['change_20d_points']:+.2f}/{ah['change_60d_points']:+.2f}点。它是加权同公司指数，不代表所有小盘。", "ah_history")
    cross["paragraphs"][3] = p("计算", f"10月2日官方值{ah['latest']['value']:.2f}，比9月30日增加{ah['holiday_change_points']:.2f}点；A股国庆休市，不能把港股交易带来的假期比值变化回贴到9月30日。5年历史修复了原先过期盘中值，但更早历史及逐公司人民币含分红可比面板仍未取得，不能据小幅价差变化认证牛熊。", "ah_history", "calendar")
    cross["tables"].insert(0, table("AH官方历史回补", ["截至", "原值", "20观测变化 / 点", "60观测变化 / 点", "覆盖"],
        [[market,fmt(value,"",False),fmt(ah["change_20d_points"],"") if market == report["market_date"] else "不回贴A股日期",fmt(ah["change_60d_points"],"") if market == report["market_date"] else "不回贴A股日期",f"{ah['start']}起"]
         for market, value in ((ah["market_day"]["date"],ah["market_day"]["value"]),(ah["latest"]["date"],ah["latest"]["value"]))],
        "毫秒时间戳按香港交易所时区还原日期，避免UTC日期提前一天；指数变化是点，不是同公司平均收益差。"))
    jgb = evidence["jgb"]
    shock["tables"].append(table("补齐日本10年国债：跨周期参考", ["观测日", "10年收益率 / %"],
        [[r["date"],fmt(r["yield_10y"],"",False)] for r in jgb["annual_reference"]]
        + [[jgb["market_day"]["date"],fmt(jgb["market_day"]["10Y"],"",False)],[jgb["latest"]["date"],fmt(jgb["latest"]["10Y"],"",False)]],
        f"10年有效日值{jgb['observations']}条，自{jgb['start']}起。年末只是事后背景，不与不同窗口收益凑概率；官方下一日本工作日9:30发布。"))
    shock["paragraphs"][4] = p("计算", f"日本10年国债长历史已补齐至当前官方日值：10月1日{jgb['latest']['10Y']:.3f}%，20/60观测上升{jgb['change_20d_bp']:.1f}/{jgb['change_60d_bp']:.1f}bp。水平和变化支持日本融资成本约束加强，但套利去杠杆仍要日元急升、股票同跌和波动/信用联合确认；不能仅由长债变动计算未对齐的行业因果弹性。", "jgb_history", "jgb_release", "sina")
    wb = evidence["worldbank"]
    oil = next(r for r in evidence["global_refresh"] if r["asset_code"] == "BRENT")
    sections["commodities"]["paragraphs"][0] = p("事实", f"补取FRED公开页后，Brent现货最新来源日为9月29日、{oil['value']:.2f}美元/桶，近20有效观测变化{oil['change_20obs_pct']:+.2f}%；页面在北京时间10月1日01:18更新，下一发布10月7日，缺9月30日原值不猜。COMEX铜原序列截至9月30日约涨0.69%，不同日期不称同日同步。IEA9月报告预计2026年油供给降570万桶/日、需求降250万桶/日，供给收缩更深。", "oil", "copper", "iea")
    navs = [r for r in evidence["global_refresh"] if r["asset_code"] != "BRENT"]
    sections["dollar"]["paragraphs"].append(p("计算", "补取官方10月2日NAV后，ACWI/EFA/EEM近20有效观测变化分别为" +
        "/".join(f"{r['change_20obs_pct']:+.2f}%" for r in navs) +
        "。这项假期信息仍不支持全球股票已经全面急跌；美元计价NAV含汇率与分红影响，不与人民币指数直接相减推因果。官方首发时分未核验，本研究只记录实际下载可见时间。", "acwi", "efa", "eem"))
    cross["tables"].append(table("全球ETF更新：假期信息单列", ["系列", "NAV / 美元", "10观测变化", "20观测变化", "所属日", "本次实测可见"],
        [[r["asset_code"],fmt(r["value"],"",False),fmt(r["change_10obs_pct"]),fmt(r["change_20obs_pct"]),r["source_date"],r["retrieved_at"]] for r in navs],
        "本次下载时间不是官方首发时间；当前修订值只更新研究，不倒写此前风险点。"))
    sections["limits"]["paragraphs"][2] = p("事实", f"本次补数复核截止北京时间{evidence['as_of_at'].replace('T', ' ')}；原始04:00数据库与外部快照保留不变，各项来源日单列。A股最后交易日9月30日，10月8日恢复交易。10月1至2日外盘及10月2日商品工作簿不回贴9月30日。只读快照可复算当前数字，不代表所有历史首次发布和修订档案已认证。", "calendar", "jobs", "wb_history")
    sections["commodities"]["tables"] = sections["commodities"].get("tables", []) + [
        table("补齐世界银行月度商品：成本与需求分开", ["品种", "所属月", "官方原值 / 单位", "1月变化", "3月变化", "有效历史起点 / 月份"],
          [[r["name"],r["period"],fmt(r["value"],"",False)+" "+r["unit"],fmt(r["change_1m_pct"]),fmt(r["change_3m_pct"]),f"{r['start']} / {r['observations']}"] for r in wb["current"]],
          "10月2日更新版本，只有发布日期则保守当日结束后可用，不回贴9月30日。官方月均价及披露精度，不是日线。铁矿表头$/dmtu保留原文，但定义注明2008年12月后为美元/干吨现货；跨切换区间不比较。澳煤2022年2月起转期货口径。"),
        table("商品跨周期同比例变化：月末窗口，不是日交易回测", ["事后区间", "Brent", "铜", "铁矿", "澳煤", "黄金", "白银"],
          [[r["start"]+"至"+r["end"],*[fmt(r["changes"][key]) for key in ("Brent","铜","铁矿石","澳大利亚煤","黄金","白银")]] for r in wb["history"]],
          "当前修订版仅用于跨周期诊断；月均端点、价格指数与期货口径不同。煤2022换口径，跨该节点不作为严格收益比较。")]
    current = {r["name"]: r for r in wb["current"]}
    sections["commodities"]["paragraphs"].append(p("计算", f"新增9月月均：Brent较8月{current['Brent']['change_1m_pct']:+.2f}%，铜{current['铜']['change_1m_pct']:+.2f}%，铁矿石{current['铁矿石']['change_1m_pct']:+.2f}%；黄金{current['黄金']['change_1m_pct']:+.2f}%，白银{current['白银']['change_1m_pct']:+.2f}%。油铜并未共跌，这更支持成本/贴现压力与需求分化，不支持已发生全面增长崩塌；月均价不能定位突发冲击日。", "wb_history"))
    synthesis["paragraphs"][2]["text"] += " 补数加强了一项韧性证据：四只ETF近20/60日份额均增加，但5日方向分化，托底未转化为宽基价格接力；央行实际使用也只证明银行工具落地，不等于股票购买力。"
    synthesis["paragraphs"][-1] = p("限制", "本次已将可核验的行业、ETF份额、AH日线、日本长债、商品月度、央行实际投放与集中度纳入复算，不再沿用‘这些都未取得’的说法。剩余源阻断、首发版本缺口和未走完的未来窗口逐项列出。行业同口径11项与目标指数财报联合面板仍未认证，所以不输出牛熊概率，也不把历史类比当未来保证。", "industry_rules", "ah_history", "wb_history", "pbc_tools")
    synthesis["paragraphs"].insert(-1, p("判断", f"按T-1融资口径复核不改变主结论：行业代表仍缺广泛绝对接力，两市截至9月29日5日净流出429.77亿元、商品成本上升增加压力；AH9月30日约24.53%溢价、银行工具与利润现金流韧性又不足以证明多年熊市。融资证据是可用而偏弱，不是缺失。保留‘转弱观察，健康牛市未恢复确认’。后续大行情需要价格与接力修复、融资抛压稳定及需求盈利扩散。", "csi", "margin", "wb_history", "ah_history", "bank", "sse_h1", "margin_release"))
    synthesis["tables"][0]["rows"][3] = ["股票资金", "四只ETF20/60日份额均增，有托底证据", "5日份额分化；融资5日约430亿元净流出", "资金托底与风险偏好分开"]
    names = {r["code"]: r["name"] for r in report["extensions"]["proxy_metrics"]}
    sections["relay"]["tables"].append(table("补齐行业后再对照2021：春节调整与年底接力", ["行业代表", "春节至3月9日", "春节至年末", "3月9日至年末"],
        [[names[r["code"]],*[fmt(v) for v in r["returns"]]] for r in evidence["sector_2021"]],
        "2021-02-10、03-09、12-31相同价格端点，不含分红；不是逐股广度，也不假定代表行业等于全行业。与当前20日不直接比较收益大小。"))
    gaps = {"id": "gap_audit", "title": "数据回补：已补证据与剩余阻断", "verdict": "已补入真实观测并复算；来源限制与未来窗口不伪装成完成。", "paragraphs": [
        p("事实", "补数和融资时点修正只写研究档案与报告，没有修改生产原始表、风险规则、市场环境、策略或通知。原始响应和快照保留校验指纹；旧报告v3/v4保留供对照。9月30日的融资输入使用前一交易日9月29日，正常T-1不再列入缺失清单。", "margin_release"),
        p("限制", "官方历史新下载不等于所有历史首发时间和修订版本都已认证。描述性跨周期比较可以使用，不能据此自动补成严格实时预测模型。剩余项需要新的数据权利、源恢复或独立的历史成分财报工程，不用估算代替。"),
    ], "tables": [table("实际回补清单", ["数据", "已取得范围", "使用方式"], [
        ["工业、必选消费", "各5311日，2005至9月30日", "扩展至8个行业代表，不冒充11行业"],
        ["4只ETF清算份额", "2013起月末/锚点，2026逐日", "严格5/20/60日与历史份额对照，不估现金"],
        ["AH溢价", f"{ah['observations']}日，{ah['start']}至10月2日", "9月30日与国庆假期分开"],
        ["日本10年国债", f"{jgb['observations']}有效日，{jgb['start']}起", "成本约束和跨周期背景"],
        ["12条商品月均价", "各有效起点至2026年9月", "10月2日更新修订版，月频诊断"],
        ["全球ETF NAV与Brent", "NAV至10月2日；Brent至9月29日", "假期公开信息与A股最后交易日分开，不假定首发时间"],
        ["央行实际工具", "129条月度、3278条操作已有档案", "补实际投放，不当股票净流入"],
        ["9月30日融资输入与集中度", "融资用9月29日两市；集中度MA5为42.96%", "融资T-1正常可用，不将未发布T日值混入"],
    ], "实际覆盖和数据精度分别披露。"), table("未补成的项：原因而非默认值", ["项", "状态", "具体原因"],
        [[r["item"],r["status"],r["reason"]] for r in evidence["remaining"]], "待验证窗口随时间推进，其他项待源恢复或独立工程，均不写成功。") ]}
    report["sections"].append(gaps)
    report["quality"][2] = "融资按前一A股交易日使用：9月30日对应9月29日两市完整输入，正常发布滞后不算缺失；旧风险总分尚未重算，其空值不用于否定融资证据。"
    report["quality"][8] = "融资5/20日按9月29日真实连续交易日复算，作为9月30日T-1可用证据；没有覆盖生产看板或填造9月30日原始融资值。"
    report["quality"][3] = "官方ETF NAV已补至10月2日；FRED Brent已补至官方最新9月29日，下一发布10月7日；不同资产、日线与月均来源日期不混称今日。"
    report["quality"][4] = "商品补入官方月均历史，不补造日线；表头、定义变化和当前修订版本不混进实时回测。"
    report["quality"][9] = "行业代表已增至8个；ETF与AH公开历史已补，覆盖及剩余首发财报/原始情绪等阻断详见回补清单。"
    report["provenance"]["supplement_input_sha256"] = evidence["input_sha256"]
    report["provenance"]["worldbank_sha256"] = wb["raw_sha256"]
    report["provenance"]["research_backfill_command"] = "python scripts/research/ashare_outlook_gap_backfill.py <action>"
    return report
