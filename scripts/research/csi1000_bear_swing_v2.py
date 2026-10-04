"""Frozen, fail-closed re-study. This command never updates saved strategies."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from bear_swing_v2_features import ROOT, coverage, features, json_default, save_json, snapshot
from csi1000_bear_swing import episodes, turning_points
from app.db.session import SessionLocal

OUT = ROOT / "runtime/reports/csi1000_bear_swing_v2"
VERSION = "bear-swing-restudy-v2.0"
POLICY = {
    "version": VERSION,
    "cutoff": "22:30 Asia/Shanghai; execution next A-share session open",
    "basic": {"train": ["2018-01-01", "2020-12-31"], "validation": ["2021-01-01", "2021-12-31"], "evaluation_start": "2022-01-01"},
    "enhanced": {"train": ["2022-07-22", "2024-12-31"], "validation": ["2025-01-01", "2025-12-31"], "evaluation_start": "2026-01-01"},
    "thresholds": {"positions_low": [10, 20, 30], "positions_high": [70, 80, 90], "wr_low": [80, 90, 95], "wr_high": [20, 10, 5]},
    "setup_memory_sessions": 5,
    "confirmation": ["none", "return1", "return3", "return5", "break1", "break3"],
    "max_factors": 3,
    "admission": {"train_events": 8, "validation_events": 5, "coverage_pct": 95,
        "favorable_first_min_pct": 45, "adverse_first_max_pct": 35,
        "pivot_coverage_min_pct": 40, "median_mae20_max_pct": 5,
        "median_return20_min_pct": 0, "neighbor_positive_min_pct": 50},
    "rank": "min(train, validation) of favorable%-adverse%+0.5*pivot_coverage%-2*median_MAE; complexity tie break",
    "outcomes": "first day of each contiguous signal; next open; 5/10/20/60 sessions; +5%/-3% first touch; same-bar order unknown; split-crossing windows purged",
    "selection": "train and validation only; evaluation periods never enter selection or threshold changes",
    "historical_review_warning": "2022+ and 2026 have been inspected previously. This is a frozen retrospective re-study, not a fresh untouched holdout or live performance.",
    "publish_policy": "No automatic production strategy replacement. A top-ranked rejected candidate remains rejected.",
    "margin_availability": "SSE/SZSE previous-session data announced before next session open. Use one actual trading-session lag; deadline is an availability upper bound, not an observed capture time.",
    "sources": ["https://investor.szse.cn/knowledge/stock/margin/t20190724_568897.html",
        "https://www.sse.com.cn/lawandrules/sselawsrules2025/trade/specific/margin/c/c_20250616_10782015.shtml"],
}
NAMES = {"wr": "WR14", "position60_pct": "60D价格位置分位", "position120_pct": "120D价格位置分位",
    "bear-momentum20-pct": "20D动量分位", "finance30_pct": "沪深融资30D累计分位(T-1)",
    "finance30_intensity_pct": "沪深融资30D强度分位(T-1)", "core_known_pct": "可知时点核心情绪分位",
    "bear-bank-tightness": "银行紧张度", "bear-vix9d-pct": "已发布VIX9D分位", "bear-vvix-pct": "已发布VVIX分位",
    "bear-mo-vix-pct": "MO隐波分位", "bear-mo-turnover-pc-pct": "MO成交额P/C分位",
    "im_basis_rate_pct": "IM期现差率分位", "bear-citic14-pct": "中信IM净空14D分位",
    "bear-mo-term-pct": "MO期限结构分位"}
for n in (1, 3, 5):
    NAMES[f"finance_change{n}"] = f"已知融资30D累计{n}日变化"


def specs(model, side):
    setup_fields = ["wr", "position60_pct", "position120_pct", "bear-momentum20-pct", "core_known_pct", "finance30_pct", "finance30_intensity_pct"]
    for field in setup_fields:
        bounds = POLICY["thresholds"]["wr_" + side] if field == "wr" else POLICY["thresholds"]["positions_" + side]
        higher = (side == "low") == (field == "wr")
        for limit in bounds:
            for turn in POLICY["confirmation"]:
                base = {"model": model, "side": side, "setup": field, "operator": "ge" if higher else "le",
                        "threshold": limit, "confirmation": turn, "lookback": 1 if turn == "none" else 5}
                extras = []
                if model == "basic":
                    extras.append(None)
                    if not field.startswith("finance") and field != "core_known_pct":
                        extras += [(f"finance_change{n}", "gt" if side == "low" else "lt", 0) for n in (1, 3, 5)]
                        extras += [("finance30_pct", "le" if side == "low" else "ge", t)
                                   for t in ([10, 20, 30] if side == "low" else [70, 80, 90])]
                    for extra in ("bear-bank-tightness", "bear-vix9d-pct", "bear-vvix-pct"):
                        extras += [(extra, "le", t) for t in (70, 80, 90)]
                else:
                    for extra in ("bear-mo-vix-pct", "bear-mo-turnover-pc-pct", "im_basis_rate_pct", "bear-citic14-pct", "bear-mo-term-pct"):
                        high = (side == "low") != (extra in ("im_basis_rate_pct", "bear-mo-term-pct"))
                        extras += [(extra, "ge" if high else "le", t) for t in ([70, 80, 90] if high else [10, 20, 30])]
                for extra in extras:
                    yield {**base, "extra": list(extra) if extra else None,
                           "family": "extreme" if turn == "none" and extra is None else "turn" if extra is None else "filtered",
                           "factors": 1 + (turn != "none") + bool(extra)}


def compare(series, op, threshold):
    return {"ge": series.ge, "le": series.le, "gt": series.gt, "lt": series.lt}[op](threshold)


def signals(f, spec):
    value = f[spec["setup"]]
    setup = compare(value, spec["operator"], spec["threshold"]).astype(float).where(value.notna())
    if spec["lookback"] > 1:
        setup = setup.rolling(spec["lookback"], min_periods=spec["lookback"]).max()
    known = setup.notna()
    match = setup.eq(1)
    turn = spec["confirmation"]
    if turn != "none":
        col = turn if turn.startswith("return") else f"break_{'high' if spec['side']=='low' else 'low'}{turn[-1]}"
        turn_value = f[col]
        known &= turn_value.notna()
        match &= compare(turn_value, "gt" if spec["side"] == "low" else "lt", 0)
    if spec["extra"]:
        col, op, threshold = spec["extra"]
        known &= f[col].notna()
        match &= compare(f[col], op, threshold)
    return (match & known).to_numpy(), known.to_numpy()


def all_outcomes(f, side):
    # Alternating single-day episodes let the existing independent evaluator
    # calculate forward outcomes for every possible start exactly once.
    rows = []
    for parity in (0, 1):
        mask = pd.Series(np.arange(len(f)) % 2 == parity, index=f.index)
        rows.extend(episodes(f, mask, side))
    return pd.DataFrame(rows).set_index("index").reindex(range(len(f)))


def stats(f, mask, known, outcomes, pivots, side, start, end):
    dates = f.index.to_numpy()
    inside = (dates >= start) & (dates <= end)
    onset = mask & ~np.r_[False, mask[:-1]]
    candidates = np.flatnonzero(onset & inside)
    complete = outcomes.loc[candidates]
    complete = complete[complete.complete_20d & complete.window_end_20d.le(end)]
    idx = complete.index.to_numpy()
    labels = [p["index"] for p in pivots if p["side"] == side and start <= dates[p["index"]] <= end and dates[p["confirmed_index"]] <= end]
    near = np.abs(np.asarray(labels)[:, None] - idx[None, :]) <= 5 if labels and len(idx) else np.zeros((len(labels), 0), bool)
    n = len(complete)
    def median(col):
        return float(complete[col].median()) if n else None
    return {"start": start, "end": end, "events": len(candidates), "evaluated": n,
        "known_pct": 100 * float(known[inside].mean()) if inside.any() else 0,
        "favorable_first_pct": 100 * float(complete.first_touch.eq("favorable").mean()) if n else None,
        "adverse_first_pct": 100 * float(complete.first_touch.eq("adverse").mean()) if n else None,
        "unknown_order": int(complete.first_touch.eq("unknown").sum()),
        "neither": int(complete.first_touch.eq("neither").sum()),
        "pivot_count": len(labels), "covered_pivots": int(near.any(axis=1).sum()),
        "pivot_coverage_pct": 100 * float(near.any(axis=1).mean()) if labels else None,
        "median_mae20": median("mae_20d"), "median_mfe20": median("mfe_20d"),
        "median_return20": median("return_20d"),
        "worst_mae20": float(complete.mae_20d.max()) if n else None}


def rejection(metrics, phase):
    p = POLICY["admission"]
    result = []
    checks = [("evaluated", p[phase + "_events"], "min"), ("known_pct", p["coverage_pct"], "min"),
        ("favorable_first_pct", p["favorable_first_min_pct"], "min"),
        ("adverse_first_pct", p["adverse_first_max_pct"], "max"),
        ("pivot_coverage_pct", p["pivot_coverage_min_pct"], "min"),
        ("median_mae20", p["median_mae20_max_pct"], "max"),
        ("median_return20", p["median_return20_min_pct"], "min")]
    for key, limit, direction in checks:
        v = metrics[key]
        if v is None or (v < limit if direction == "min" else v > limit):
            result.append(f"{phase}.{key}: {v} ({direction} {limit})")
    return result


def quality(m):
    if not m["evaluated"]:
        return -1000
    return (m["favorable_first_pct"] - m["adverse_first_pct"] +
            .5 * (m["pivot_coverage_pct"] or 0) - 2 * m["median_mae20"])


def selection_key(r):
    # Holdout/evaluation metrics must never be referenced here.
    return (-r["selection_score"], r["spec"]["factors"], r["id"])


def describe(s):
    op = {"ge": ">=", "le": "<=", "gt": ">", "lt": "<"}
    setup = f"{NAMES.get(s['setup'],s['setup'])}{op[s['operator']]}{s['threshold']}"
    if s["lookback"] > 1:
        setup = f"近{s['lookback']}日曾满足({setup})"
    turn = s["confirmation"]
    if turn != "none":
        setup += " 且 " + (f"{turn[-1]}日涨跌幅{'大于' if s['side']=='low' else '小于'}0" if turn.startswith("return") else
            f"收盘{'突破' if s['side']=='low' else '跌破'}此前{turn[-1]}日{'最高' if s['side']=='low' else '最低'}价")
    if s["extra"]:
        k, o, v = s["extra"]
        setup += f" 且 {NAMES.get(k,k)}{op[o]}{v}"
    return setup


def research(f):
    pivots = turning_points(f)
    outcomes = {side: all_outcomes(f, side) for side in ("low", "high")}
    attempts, results = [], {}
    for model in ("basic", "enhanced"):
        results[model] = {}
        for side in ("low", "high"):
            trials = []
            for i, spec in enumerate(specs(model, side)):
                mask, known = signals(f, spec)
                first = str(f.index[np.flatnonzero(known)[0]]) if known.any() else "9999-12-31"
                train_start = POLICY[model]["train"][0] if model == "basic" else max(first, POLICY[model]["train"][0])
                development = stats(f, mask, known, outcomes[side], pivots, side, train_start, POLICY[model]["train"][1])
                validation = stats(f, mask, known, outcomes[side], pivots, side, *POLICY[model]["validation"])
                rejected = rejection(development, "train") + rejection(validation, "validation")
                if model == "enhanced" and len(f.loc[train_start:POLICY[model]["train"][1]]) < 252:
                    rejected.append("train.complete_history: less than 252 sessions")
                if model == "basic" and first > "2022-01-01":
                    rejected.append("basic.not_ready_by_2022")
                trials.append({"id": f"{model}-{side}-{i:04d}", "spec": spec, "first_complete": first,
                    "train": development, "validation": validation, "rejection": rejected,
                    "selection_score": min(quality(development), quality(validation))})
            # Nearby setup thresholds must retain a positive payoff ordering.
            grouped = {}
            for r in trials:
                s = {k:v for k,v in r["spec"].items() if k != "threshold"}
                grouped.setdefault(json.dumps(s, sort_keys=True), []).append(r)
            for group in grouped.values():
                for r in group:
                    others = [x for x in group if x is not r]
                    positive = [x for x in others if all(x[p]["evaluated"] >= POLICY["admission"][p+"_events"] and
                        x[p]["favorable_first_pct"] > x[p]["adverse_first_pct"] for p in ("train", "validation"))]
                    r["neighbor_positive_pct"] = 100 * len(positive) / len(others) if others else 0
                    if r["neighbor_positive_pct"] < POLICY["admission"]["neighbor_positive_min_pct"]:
                        r["rejection"].append("neighbors.positive_payoff: below 50%")
                    r["accepted"] = not r["rejection"]
            # The diagnostic candidate also needs adequate sample/coverage. Never
            # allow a one-event winner to masquerade as the best research result.
            eligible = [r for r in trials if r["train"]["evaluated"] >= 8 and r["validation"]["evaluated"] >= 5
                        and r["train"]["known_pct"] >= 95 and r["validation"]["known_pct"] >= 95]
            accepted = sorted([r for r in eligible if r["accepted"]], key=selection_key)
            ranked = sorted(eligible, key=selection_key)
            winner = accepted[0] if accepted else ranked[0] if ranked else None
            families = {family: min((r for r in eligible if r["spec"]["family"] == family), key=selection_key, default=None)
                        for family in ("extreme", "turn", "filtered")}
            results[model][side] = {"attempts": len(trials), "accepted_count": len(accepted),
                "candidate": winner, "family_candidates": families, "top5": ranked[:5]}
            attempts.extend(trials)
            print(model, side, "trials", len(trials), "accepted", len(accepted),
                  describe(winner["spec"]) if winner else "NO_ELIGIBLE_CANDIDATE", flush=True)
    # Everything below is reporting only, after selection has been frozen.
    for model, sides in results.items():
        for side, result in sides.items():
            r = result["candidate"]
            if not r:
                continue
            mask, known = signals(f, r["spec"])
            start = max(r["first_complete"], "2022-01-01")
            mask &= f.index.to_numpy() >= start
            r["evaluation"] = {str(y): stats(f, mask, known, outcomes[side], pivots, side, f"{y}-01-01", f"{y}-12-31") for y in range(2022, 2027)}
            r["evaluation"]["2023_to_2024_09"] = stats(f, mask, known, outcomes[side], pivots, side, "2023-01-01", "2024-09-18")
            ev = episodes(f, pd.Series(mask, index=f.index), side)
            for e in ev:
                nearest = min((p for p in pivots if p["side"]==side), key=lambda p:abs(p["index"]-e["index"]), default=None)
                e["nearest_pivot_date"] = str(f.index[nearest["index"]]) if nearest else None
                e["pivot_distance_sessions"] = e["index"]-nearest["index"] if nearest else None
                e["pivot_distance_pct"] = 100*(f.close.iloc[e["index"]]/f.close.iloc[nearest["index"]]-1) if nearest else None
            pd.DataFrame(ev).to_csv(OUT / f"{model}_{side}_events.csv", index=False)
            fields = {r["spec"]["setup"], "finance_source_date", "open", "high", "low", "close"}
            if r["spec"]["extra"]: fields.add(r["spec"]["extra"][0])
            daily = f[sorted(fields)].copy()
            daily["signal"] = pd.array(np.where(known, mask.astype(float), np.nan), dtype="Float64")
            daily["as_of_at"] = daily.index + "T22:30:00+08:00"
            daily["decision_trade_date"] = pd.Series(f.index, index=f.index).shift(-1)
            daily.to_csv(OUT/f"{model}_{side}_daily.csv", index_label="signal_date")
            r["events"] = ev
    return results, attempts


def markdown(report):
    lines = ["# 中证1000熊市波段重新研究", "", f"数据截止：{report['as_of']}；版本：{VERSION}", "",
        "本轮是历史已被查看后的冻结重研，不宣称新的独立样本外验证。原始历史是当前数据库保存版本。",
        "未达到准入门槛的候选不会替换正式策略。已有策略44/45保持不变。", "", "## 准入标准",
        "开发至少8段、验证至少5段；输入覆盖至少95%；开发和验证均需先有利5%比例≥45%、先不利3%比例≤35%、低/高点覆盖≥40%、中位最大逆向≤5%、20日中位方向收益≥0；至少一半相邻参数仍有正向优势。",
        "基本版2018–2020开发、2021验证；增强版真实预热完成日至2024开发、2025验证。2022+ / 2026只做冻结后的诊断。",
        "", "## 结果"]
    for model,sides in report["models"].items():
        for side,x in sides.items():
            title = ("基础版" if model=="basic" else "增强版") + ("低点" if side=="low" else "高点")
            lines += [f"### {title}", f"尝试{x['attempts']}组，达标{x['accepted_count']}组。"]
            r=x["candidate"]
            if not r:
                lines.append("没有满足最低样本量和覆盖的候选。")
                continue
            lines += ["研究候选："+describe(r["spec"]), "状态："+("通过开发/验证门槛，仍需冻结后评价" if r["accepted"] else "未达标，不替换现有策略"),
                "未达标项："+"；".join(r["rejection"]), "",
                "| 区间 | 有效段数 | 先有利5% | 先不利3% | 中位最大逆向 | 极值覆盖 |", "|---|---:|---:|---:|---:|---:|"]
            for stage,m in {"开发":r["train"],"验证":r["validation"],**r["evaluation"]}.items():
                fmt=lambda v:"--" if v is None else f"{v:.1f}%"
                lines.append(f"|{stage}|{m['evaluated']}|{fmt(m['favorable_first_pct'])}|{fmt(m['adverse_first_pct'])}|{fmt(m['median_mae20'])}|{fmt(m['pivot_coverage_pct'])}|")
            lines.append("")
    lines += ["## 数据与口径", *["- "+s for s in report["data_notes"]], "", "## 来源"]
    lines += [f"- [融资披露规则{i+1}]({url})" for i,url in enumerate(POLICY["sources"])]
    return "\n".join(lines)+"\n"


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshot",action="store_true")
    p.add_argument("--run",action="store_true")
    args=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    frozen=OUT/"protocol.json"
    if frozen.exists():
        assert json.loads(frozen.read_text())["policy"] == POLICY, "Protocol changed: use a new version/output directory"
    else:
        save_json(frozen,{"frozen_at":datetime.now().astimezone().isoformat(),"policy":POLICY})
    if args.snapshot:
        with SessionLocal() as db:
            raw=snapshot(db)
        save_json(OUT/"inputs.json",raw)
        f=features(raw)
        f.to_json(OUT/"features.json",orient="table",indent=2)
        save_json(OUT/"coverage.json",coverage(f))
        print("SNAPSHOT",len(f),f.index[-1],flush=True)
    if args.run:
        f=pd.read_json(OUT/"features.json",orient="table")
        f.index=f.index.astype(str)
        models,attempts=research(f)
        report={"version":VERSION,"generated_at":datetime.now().astimezone().isoformat(),"as_of":f.index[-1],
            "protocol_sha256":hashlib.sha256(frozen.read_bytes()).hexdigest(),
            "data_sha256":hashlib.sha256((OUT/"inputs.json").read_bytes()).hexdigest(),
            "models":models,"production_updated":False,"data_notes":[
                "沪深融资按真实A股交易日滞后1日；公布时点使用交易所开市前披露上界，不伪称抓取时间；不混入2023年才开始的北交所。",
                "融资30D和其变化按所属交易日先计算后滞后；缺任一交易所或窗口内任一日则空缺。",
                "核心情绪重新按当时已知融资计算，五个分项全部有效才输出；只作为独立候选，不与融资重复加条件。",
                "银行流动性和全球序列继续按available_at映射；市场总风险分底层时点未全部核验，不充作严格实时输入。",
                "估值和汇率保存覆盖证据，但表内缺原始发布时间及历史版本，本轮未用作准入规则。",
                "M1/M2与社融有较早原文，但严格replay_available_at最早2026-09-20；不将后来观察的版本回贴到训练期。",
                "MO收盘隐波缺失日保留缺失；不以前日或开盘值冒充收盘值。",
                "信号当日22:30截止；下一交易日开盘评价；高点方向收益不是实际做空收益。",
                "原策略、策略44/45、市场环境、通知、数据库数据和服务未修改。"]}
        save_json(OUT/"attempts.json",attempts)
        save_json(OUT/"report.json",report)
        (OUT/"report.md").write_text(markdown(report),encoding="utf-8")
        print("REPORT",OUT/"report.md",flush=True)


if __name__=="__main__":
    main()
