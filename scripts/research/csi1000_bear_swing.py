"""Frozen-grid bear swing research. Reads source data; never writes to the DB."""
import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.session import SessionLocal
from app.services.bear_swing_features import VERSION, load_features

OUT = ROOT / "runtime/reports/csi1000_bear_swing"
WINDOWS = (5, 10, 20, 60)
BASE_POSITIONS = ("wr", "bear-momentum20-pct", "bear-position60-pct")
ENHANCED = ("bear-mo-turnover-pc-pct", "bear-im-basis-pct", "bear-citic14-pct", "bear-mo-vix-pct", "bear-mo-term-pct")
FILTERS = ("bear-bank-tightness", "bear-vix9d-pct", "bear-vvix-pct")
LABELS = {"wr": "WR14", "bear-momentum20-pct": "20D动量历史分位", "bear-position60-pct": "60D价格位置历史分位",
          "bear-bank-tightness": "银行流动性紧张度", "bear-vix9d-pct": "VIX9D历史分位（已发布）",
          "bear-vvix-pct": "VVIX历史分位（已发布）", "bear-mo-turnover-pc-pct": "MO成交额P/C历史分位",
          "bear-im-basis-pct": "IM主力期现差历史分位", "bear-citic14-pct": "中信IM净空14D增量历史分位",
          "bear-mo-vix-pct": "MO隐含波动率历史分位", "bear-mo-term-pct": "MO波动率期限结构历史分位"}
LABELS.update({f"bear-return-{n}d": f"指数{n}D涨跌幅" for n in (1, 3, 5)})


def rule_mask(frame, conditions):
    mask = pd.Series(True, index=frame.index)
    for c in conditions:
        values = frame[c["field"]]
        compared = values >= c["value"] if c["operator"] == "gte" else values <= c["value"]
        mask &= values.notna() & compared
    return mask


def condition(field, operator, value):
    return {"type": "numeric", "field": field, "operator": operator, "value": value}


def candidates(side, enhanced=False):
    for field in BASE_POSITIONS:
        values = (80, 90, 95) if side == "low" and field == "wr" else (20, 10, 5) if field == "wr" else (10, 20, 30) if side == "low" else (70, 80, 90)
        op = "gte" if (side == "low") == (field == "wr") else "lte"
        for value in values:
            core = [condition(field, op, value)]
            for turn in (0, 1, 3, 5):
                rules = core + ([condition(f"bear-return-{turn}d", "gte" if side == "low" else "lte", 0)] if turn else [])
                if not enhanced:
                    yield {"family": "extreme" if not turn else "turn", "conditions": rules}
                    for extra in FILTERS:
                        for limit in (70, 80, 90):
                            yield {"family": "filter", "conditions": rules + [condition(extra, "lte", limit)]}
                else:
                    for extra in ENHANCED:
                        # Rebound lows: depressed basis, elevated protection/shorting.
                        high = (side == "low") != (extra in ("bear-im-basis-pct", "bear-mo-term-pct"))
                        for threshold in ((70, 80, 90) if high else (10, 20, 30)):
                            yield {"family": "derivative", "conditions": rules + [condition(extra, "gte" if high else "lte", threshold)]}


def turning_points(frame, reversal=.05):
    """Ex-post close-based 5% zigzag; final unconfirmed extreme is excluded."""
    result, direction, high, low = [], 0, 0, 0
    prices = frame.close.to_numpy()
    for i in range(1, len(frame)):
        if direction == 0:
            if prices[i] > prices[high]: high = i
            if prices[i] < prices[low]: low = i
            if prices[i] >= prices[low] * (1 + reversal):
                result.append({"index": low, "side": "low", "confirmed_index": i})
                direction, high = 1, i
            elif prices[i] <= prices[high] * (1 - reversal):
                result.append({"index": high, "side": "high", "confirmed_index": i})
                direction, low = -1, i
        elif direction > 0:
            if prices[i] > prices[high]: high = i
            if prices[i] <= prices[high] * (1 - reversal):
                result.append({"index": high, "side": "high", "confirmed_index": i})
                direction, low = -1, i
        else:
            if prices[i] < prices[low]: low = i
            if prices[i] >= prices[low] * (1 + reversal):
                result.append({"index": low, "side": "low", "confirmed_index": i})
                direction, high = 1, i
    return result


def episodes(frame, mask, side):
    first = mask & ~mask.shift(1, fill_value=False)
    values, result = frame[["open", "high", "low", "close"]].to_numpy(), []
    for i in np.flatnonzero(first):
        end = i
        while end + 1 < len(mask) and mask.iloc[end + 1]: end += 1
        row = {"index": int(i), "date": frame.index[i], "end_date": frame.index[end], "days": int(end - i + 1), "side": side}
        entry = values[i + 1, 0] if i + 1 < len(frame) else None
        row.update(entry_date=frame.index[i + 1] if entry else None, entry=entry)
        sign = 1 if side == "low" else -1
        for w in WINDOWS:
            future = values[i + 1:i + w + 1]
            complete = len(future) == w and entry and np.isfinite(future).all()
            row[f"complete_{w}d"] = bool(complete)
            row[f"return_{w}d"] = float(sign * (future[-1, 3] / entry - 1) * 100) if complete else None
            row[f"mfe_{w}d"] = float((future[:, 1].max() / entry - 1 if side == "low" else 1 - future[:, 2].min() / entry) * 100) if complete else None
            row[f"mae_{w}d"] = float((1 - future[:, 2].min() / entry if side == "low" else future[:, 1].max() / entry - 1) * 100) if complete else None
            row[f"window_end_{w}d"] = frame.index[i + w] if complete else None
        row["first_touch"] = "pending" if not row["complete_20d"] else "neither"
        if row["complete_20d"]:
            for _, hi, lo, _ in values[i + 1:i + 21]:
                favorable = hi >= entry * 1.05 if side == "low" else lo <= entry * .95
                adverse = lo <= entry * .97 if side == "low" else hi >= entry * 1.03
                if favorable or adverse:
                    row["first_touch"] = "unknown" if favorable and adverse else "favorable" if favorable else "adverse"
                    break
        result.append(row)
    return result


def summarize(events, start, end, labels, frame):
    # Purge forward outcomes crossing the split boundary. A new split cannot
    # use the returns of a signal whose window runs into the next split.
    all_events = [e for e in events if start <= e["date"] <= end]
    complete = [e for e in all_events if e["complete_20d"] and e["window_end_20d"] <= end]
    pivots = [p for p in labels if start <= frame.index[p["index"]] <= end and frame.index[p["confirmed_index"]] <= end]
    covered = sum(any(abs(e["index"] - p["index"]) <= 5 for e in complete) for p in pivots)
    n = len(complete)
    return {"count": len(all_events), "evaluated": n, "pending_or_purged": len(all_events) - n,
            "favorable_first_pct": 100 * sum(e["first_touch"] == "favorable" for e in complete) / n if n else None,
            "adverse_first_pct": 100 * sum(e["first_touch"] == "adverse" for e in complete) / n if n else None,
            "unknown_order": sum(e["first_touch"] == "unknown" for e in complete),
            "median_mfe20": float(np.median([e["mfe_20d"] for e in complete])) if n else None,
            "median_mae20": float(np.median([e["mae_20d"] for e in complete])) if n else None,
            "worst_mae20": max((e["mae_20d"] for e in complete), default=None),
            "pivot_coverage_pct": 100 * covered / len(pivots) if pivots else None,
            "pivot_count": len(pivots), "covered_pivots": covered,
            "false_positive_pct": 100 * sum(e["first_touch"] != "favorable" for e in complete) / n if n else None}


def quality(metrics):
    if not metrics["evaluated"]: return -1000
    return (metrics["favorable_first_pct"] - metrics["adverse_first_pct"] +
            .5 * (metrics["pivot_coverage_pct"] or 0) - 2 * metrics["median_mae20"])


def evaluate(frame, rule, side, start, end, labels):
    mask = rule_mask(frame, rule["conditions"])
    ev = episodes(frame, mask, side)
    return summarize(ev, start, end, labels, frame)


def select(frame, side, enhanced, labels):
    train = ("2022-07-22", "2024-12-31") if enhanced else ("2018-01-01", "2020-12-31")
    validation = ("2025-01-01", "2025-12-31") if enhanced else ("2021-01-01", "2021-12-31")
    attempts = []
    for idx, rule in enumerate(candidates(side, enhanced)):
        mask = rule_mask(frame, rule["conditions"])
        fields = [c["field"] for c in rule["conditions"]]
        complete = frame[fields].notna().all(axis=1)
        available = frame.index[complete]
        events = episodes(frame, mask, side)
        development = summarize(events, *train, labels, frame)
        valid = summarize(events, *validation, labels, frame)
        # Count/loss caps fixed before any holdout evaluation. Low coverage is
        # explicitly penalized, so one lucky signal cannot win the search.
        eligible = development["evaluated"] >= 8 and valid["evaluated"] >= 3
        annual = [summarize(events, f"{year}-01-01", f"{year}-12-31", labels, frame)
                  for year in range(int(train[0][:4]), int(train[1][:4]) + 1)]
        rank = min(quality(development), quality(valid)) - .1 * len(fields)
        rank -= 5 * sum(m["evaluated"] == 0 for m in annual)
        attempts.append({"id": idx, "side": side, **rule, "first_complete_date": available[0] if len(available) else None,
                         "train": development, "validation": valid, "eligible": eligible, "selection_score": rank})
    ranked = sorted([a for a in attempts if a["eligible"]], key=lambda a: (-a["selection_score"], len(a["conditions"]), a["id"]))
    if not ranked:
        raise RuntimeError(f"{side} enhanced={enhanced}: no candidate passed minimum event counts; do not relax using holdout")
    return ranked[0], attempts


def describe(rule):
    return " 且 ".join(f"{LABELS.get(c['field'], c['field'])}{'>=' if c['operator']=='gte' else '<='}{c['value']:g}" for c in rule["conditions"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cached = OUT / "features.json"
    if args.refresh or not cached.exists():
        with SessionLocal() as db:
            frame = load_features(db)
        frame.to_json(cached, orient="table", indent=2)
    else:
        frame = pd.read_json(cached, orient="table")
    frame.index = frame.index.astype(str)
    pivots = turning_points(frame)
    models, attempts = {}, []
    for name, enhanced in (("basic", False), ("enhanced", True)):
        model = {}
        for side in ("low", "high"):
            labels = [p for p in pivots if p["side"] == side]
            rule, trials = select(frame, side, enhanced, labels)
            model[side] = rule
            attempts.extend({"model": name, **a} for a in trials)
            print(name, side, describe(rule), flush=True)
        start = max("2022-01-01", *(model[s]["first_complete_date"] for s in ("low", "high")))
        # Both sides are unavailable before the selected feature set is warmed up.
        model["start_date"] = start
        model["config_sha256"] = hashlib.sha256(json.dumps({s: model[s]["conditions"] for s in ("low", "high")}, sort_keys=True).encode()).hexdigest()
        for side in ("low", "high"):
            mask = rule_mask(frame, model[side]["conditions"]) & (frame.index >= start)
            ev = episodes(frame, mask, side)
            for e in ev:
                near = min((p for p in pivots if p["side"] == side), key=lambda p: abs(p["index"] - e["index"]), default=None)
                e["nearest_pivot_date"] = frame.index[near["index"]] if near else None
                e["pivot_distance_days"] = e["index"] - near["index"] if near else None
                e["pivot_distance_pct"] = float((frame.close.iloc[e["index"]] / frame.close.iloc[near["index"]] - 1) * 100) if near else None
            model[side]["events"] = ev
            labels = [p for p in pivots if p["side"] == side]
            model[side]["periods"] = {str(y): summarize(ev, f"{y}-01-01", f"{y}-12-31", labels, frame) for y in range(2022, 2027)}
            model[side]["periods"]["2023_to_2024_09"] = summarize(ev, "2023-01-01", "2024-09-18", labels, frame)
            model[side]["periods"]["post_2024_09"] = summarize(ev, "2024-09-19", frame.index[-1], labels, frame)
            for phase, origin in (("bull_up_swings", "low"), ("bull_adjustments", "high")):
                ranges = [(a["index"], b["index"]) for a, b in zip(pivots, pivots[1:]) if a["side"] == origin]
                in_phase = lambda i: frame.index[i] >= "2024-09-19" and any(a <= i < b for a, b in ranges)
                model[side]["periods"][phase] = summarize(
                    [e for e in ev if in_phase(e["index"])], "2024-09-19", frame.index[-1],
                    [p for p in labels if in_phase(p["index"])], frame)
            pd.DataFrame(ev).to_csv(OUT / f"{name}_{side}_events.csv", index=False)
        daily = pd.DataFrame(index=frame.index)
        daily["red_low"] = rule_mask(frame, model["low"]["conditions"]) & (frame.index >= start)
        daily["blue_high"] = rule_mask(frame, model["high"]["conditions"]) & (frame.index >= start)
        daily["information_cutoff"] = daily.index + "T22:30:00+08:00"
        fields = sorted({c["field"] for side in ("low", "high") for c in model[side]["conditions"]})
        daily[fields] = frame[fields]
        daily.index.name = "signal_date"
        daily.to_csv(OUT / f"{name}_daily_signals.csv")
        models[name] = model
    overlap = models["enhanced"]["start_date"]
    for model in models.values():
        model["common_period"] = {side: summarize(model[side]["events"], max(overlap, "2026-01-01"), frame.index[-1],
                                 [p for p in pivots if p["side"] == side], frame) for side in ("low", "high")}
    report = {"version": VERSION, "generated_at": datetime.now().astimezone().isoformat(), "as_of": frame.index[-1],
              "data_sha256": hashlib.sha256(cached.read_bytes()).hexdigest(), "models": models,
              "selection_protocol": {"basic": "2018-2020 develop; 2021 validate; 2022+ holdout", "enhanced": "real coverage through 2024 develop; 2025 validate; 2026 holdout", "minimum_train_events": 8, "minimum_validation_events": 3, "score": "min(train, validation) of favorable%-adverse%+0.5*pivot_coverage%-2*median_MAE; sparse annual penalty; complexity tie break", "windows_crossing_split": "purged"},
              "excluded": {"emotion": "原始情绪不覆盖2022，禁止默认50或图像估计用于本研究", "core_financing_risk": "原自建核心/融资/完整风险分缺乏可核验逐日发布时间，未进入正式选型", "valuation_fx": "现有日频表缺少可核验历史可用时间，未进入正式规则", "monthly_macro": "历史首次发布版本不能覆盖2018训练期；仅解释，不作为规则", "qvix_proxy": "不使用上市前的代理隐波历史"},
              "notes": ["每日22:30截止；指数信号次日开盘评价；ETF回测另按现有引擎。", "高点后的跌幅不是实际做空收益，无融资成本、基差或合约换月。", "历史日线为当前存储版本，未持有全部当时归档快照；这是因果计算重放，不是历史实盘业绩。", "全球数据使用available_at；国内期权/期货收盘数据按照当日收市后可用，未伪造逐笔抓取时间。", "银行数据按三条来源最晚available_at映射；缺失不填0，超7日不沿用。", "5%事后波段基于收盘反转，匹配容差前后5个交易日；最后未确认极值不参与。", "bull_up_swings/bull_adjustments仅为2024-09-19后已确认5%波段的事后上行/调整分层，不用于选型或开关；尚未确认的尾段不分类。", "首次触达5%/3%同日双越界为顺序未知；未到完整20日不计胜负。", "两端均需8个开发事件及3个验证事件；所有参数尝试完整存档。", "不修改任何旧策略、市场环境、通知或交易引擎。"]}
    (OUT / "attempts.json").write_text(json.dumps(attempts, ensure_ascii=False, indent=2))
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    lines = ["# 中证1000熊市波段研究", f"数据截止：{report['as_of']}", "", "## 规则（冻结后样本外评价）"]
    for name, model in models.items():
        lines += [f"### {'基础版' if name=='basic' else '增强版'}", f"起点：{model['start_date']}",
                  "- 红色低点：" + describe(model["low"]), "- 蓝色高点：" + describe(model["high"]),
                  f"- 规则指纹：{model['config_sha256']}", "", "| 年份 | 端点 | 有效事件 | 先盈利5% | 先不利3% | 中位最大逆向 | 极值覆盖 |", "|---|---|---:|---:|---:|---:|---:|"]
        for side in ("low", "high"):
            for period, m in {"开发期": model[side]["train"], "验证期": model[side]["validation"], **model[side]["periods"]}.items():
                fmt = lambda x: "待验证" if x is None else f"{x:.1f}%"
                lines.append(f"|{period}|{side}|{m['evaluated']}|{fmt(m['favorable_first_pct'])}|{fmt(m['adverse_first_pct'])}|{fmt(m['median_mae20'])}|{fmt(m['pivot_coverage_pct'])}|")
    lines += ["", "## 数据限制", *[f"- {k}：{v}" for k, v in report["excluded"].items()], "", *[f"- {n}" for n in report["notes"]]]
    (OUT / "report.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: {s: v["common_period"][s] for s in ("low", "high")} for k, v in models.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
