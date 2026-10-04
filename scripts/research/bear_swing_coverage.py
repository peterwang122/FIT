"""Coverage-first retrospective condition search; production install is separate."""
import argparse
import hashlib
import itertools
import json
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import text

from bear_swing_v2_features import ROOT, save_json
from csi1000_bear_swing import episodes, turning_points
from csi1000_bear_swing_v2 import all_outcomes, stats
from app.db.session import SessionLocal
from app.services.bear_swing_features import load_features

OUT = ROOT / "runtime/reports/csi1000_bear_swing_coverage"
POLICY = {
    "version": "coverage-first-v1", "signal_cutoff": "22:30 Asia/Shanghai; next session open",
    "extreme": "Confirmed 5% close-reversal low, mapped to minimum intraday low from 5 sessions before close pivot through confirmation; 120-session new low and >=15% decline from 120-session high",
    "coverage": "Every labeled extreme on/after saved strategy start must be red and not blue; early signals allowed",
    "max_red_day_pct": 35, "min_train_events": 8, "min_validation_events": 3,
    "rank": "min(train,validation) of favorable_first%-adverse_first%-2*median_MAE20; minus 0.1*red_day_pct; ties fewer conditions then ID",
    "periods": {"basic": [["2018-01-01", "2020-12-31"], ["2021-01-01", "2021-12-31"]],
                "enhanced": [["2023-08-24", "2024-12-31"], ["2025-01-01", "2025-12-31"]]},
    "grid": {"wr": [60, 70, 80, 90, 95], "rsi": [20, 25, 30, 35, 40, 45],
             "position": [5, 10, 20, 30, 40], "iv": [50, 60, 70, 80, 90]},
    "scope": "Only red conditions and descriptive notes of existing IDs44/45; blue, positions, execution and all other strategies unchanged",
    "limitation": "Retrospectively selected using 2022+ extreme coverage; not untouched out-of-sample. Historical coverage is not a promise about future bottoms.",
}


def cond(field, op, value):
    return {"type": "numeric", "field": field, "operator": op, "value": value}


def groups(*branches):
    return [{"conditions": list(branch)} for branch in branches]


def matches(f, rule):
    matched = np.zeros(len(f), bool)
    all_false = np.ones(len(f), bool)
    for group in rule:
        is_true = np.ones(len(f), bool)
        any_false = np.zeros(len(f), bool)
        for c in group["conditions"]:
            v = f[c["field"]]
            op = {"gte": v.ge, "lte": v.le, "gt": v.gt, "lt": v.lt}[c["operator"]]
            hit = op(c["value"]).to_numpy()
            present = v.notna().to_numpy()
            is_true &= hit & present
            any_false |= ~hit & present
        matched |= is_true
        all_false &= any_false
    return matched, matched | all_false


def candidates(model):
    grid = POLICY["grid"]
    price = [("wr", "gte", grid["wr"]), ("rsi", "lte", grid["rsi"])]
    if model == "basic":
        for field, op, limits in [*price, ("bear-position60-pct", "lte", grid["position"])]:
            for limit in limits:
                yield groups([cond(field, op, limit)])
        for field, op, limits in price:
            for limit, position in itertools.product(limits, grid["position"]):
                yield groups([cond(field, op, limit), cond("bear-position60-pct", "lte", position)])
        for wr, wp, rsi, rp in itertools.product(grid["wr"], grid["position"], grid["rsi"], grid["position"]):
            yield groups([cond("wr", "gte", wr), cond("bear-position60-pct", "lte", wp)],
                         [cond("rsi", "lte", rsi), cond("bear-position60-pct", "lte", rp)])
    else:
        for field, op, limits in price:
            for limit, panic, position, iv in itertools.product(limits, limits, grid["position"], grid["iv"]):
                if not (panic > limit if op == "gte" else panic < limit):
                    continue
                # Explicit alternative: extreme-price branch does not require IV.
                # This is not filling missing IV or falling back before warmup.
                yield groups([cond(field, op, panic), cond("bear-position60-pct", "lte", position)],
                             [cond(field, op, limit), cond("bear-position60-pct", "lte", position),
                              cond("bear-mo-vix-pct", "gte", iv)])


def extreme_labels(f):
    labels = {}
    for pivot in turning_points(f):
        if pivot["side"] != "low":
            continue
        a, b = max(0, pivot["index"] - 5), pivot["confirmed_index"] + 1
        i = a + int(f.low.iloc[a:b].to_numpy().argmin())
        if i < 119:
            continue
        lo, hi = float(f.low.iloc[i]), float(f.high.iloc[i - 119:i + 1].max())
        if lo <= f.low.iloc[i - 119:i + 1].min() and lo <= hi * .85:
            labels[i] = {"index": i, "date": f.index[i], "low": lo,
                         "decline_pct": (lo / hi - 1) * 100,
                         "confirmed_date": f.index[pivot["confirmed_index"]]}
    return list(labels.values())


def title(rule):
    names = {"wr": "WR14", "rsi": "RSI14", "bear-position60-pct": "60D价格位置历史分位",
             "bear-mo-vix-pct": "MO收盘隐波历史分位"}
    return " 或 ".join("(" + " 且 ".join(f"{names.get(c['field'],c['field'])}{'>=' if c['operator']=='gte' else '<='}{c['value']}"
                        for c in b["conditions"]) + ")" for b in rule)


def bottom_rows(f, mask, blue, labels, start):
    result = []
    for label in labels:
        if label["date"] < start:
            continue
        i, first = label["index"], label["index"]
        hit = bool(mask[i] and not blue[i])
        if hit:
            while first > 0 and f.index[first-1] >= start and mask[first-1] and not blue[first-1]:
                first -= 1
        entry = float(f.open.iloc[first+1]) if hit and first+1 <= i else None
        result.append({**label, "hit": hit, "first_signal": f.index[first] if hit else None,
                       "lead_sessions": i-first if hit else None,
                       "first_entry_to_low_pct": (label["low"]/entry-1)*100 if entry else None})
    return result


def run():
    f = pd.read_json(OUT / "features.json", orient="table")
    f.index = f.index.astype(str)
    saved = json.loads((OUT / "saved.json").read_text())
    labels, pivots, outcomes = extreme_labels(f), turning_points(f), all_outcomes(f, "low")
    attempts, models = [], {}
    for model, sid in (("basic", 44), ("enhanced", 45)):
        old = next(r for r in saved if r["id"] == sid)
        start = old["start_date"]
        old_red, old_known = matches(f, old["red_filter_groups"])
        blue, _ = matches(f, old["blue_filter_groups"])
        active = f.index.to_numpy() >= start
        targets = [r["index"] for r in labels if r["date"] >= start]
        assert targets
        trials = []
        for n, rule in enumerate(candidates(model)):
            mask, known = matches(f, rule)
            effective = mask & ~blue
            covered = int(effective[targets].sum())
            days = 100 * float(effective[active].mean())
            reasons = []
            if covered != len(targets): reasons.append("extreme_coverage")
            if days > POLICY["max_red_day_pct"]: reasons.append("red_days")
            train, validation = [stats(f, effective, known, outcomes, pivots, "low", *period)
                                 for period in POLICY["periods"][model]]
            if train["evaluated"] < 8 or validation["evaluated"] < 3: reasons.append("sample_size")
            def q(m):
                return -1000 if not m["evaluated"] else m["favorable_first_pct"]-m["adverse_first_pct"]-2*m["median_mae20"]
            score = min(q(train), q(validation)) - .1*days
            trials.append({"id": f"{model}-{n:04d}", "model": model, "rule": rule, "coverage": covered,
                           "targets": len(targets), "red_day_pct": days, "train": train, "validation": validation,
                           "score": score, "rejected": reasons,
                           "complexity": sum(len(g["conditions"]) for g in rule)})
        eligible = sorted((r for r in trials if not r["rejected"]), key=lambda r: (-r["score"], r["complexity"], r["id"]))
        if not eligible:
            save_json(OUT / f"{model}_attempts.json", trials)
            raise RuntimeError(f"{model}: no coverage-complete candidate; do not silently relax")
        chosen = eligible[0]
        mask, known = matches(f, chosen["rule"])
        effective = mask & ~blue & active
        chosen.update(strategy_id=sid, start_date=start, old_rule=old["red_filter_groups"],
                      blue_rule=old["blue_filter_groups"], eligible_count=len(eligible))
        chosen["bottoms"] = bottom_rows(f, mask, blue, labels, start)
        chosen["old_bottoms"] = bottom_rows(f, old_red, blue, labels, start)
        chosen["periods"] = {}
        for key, low in (("old", old_red), ("new", mask)):
            chosen["periods"][key] = {str(y): stats(f, low & ~blue & active, old_known if key=="old" else known, outcomes, pivots, "low", max(start, f"{y}-01-01"), f"{y}-12-31")
                                            for y in range(max(2022, int(start[:4])), 2027)}
        ev = episodes(f, pd.Series(effective, index=f.index), "low")
        pd.DataFrame(ev).to_csv(OUT / f"{model}_low_events.csv", index=False)
        daily = f[["open", "high", "low", "close", "wr", "rsi", "bear-position60-pct", "bear-mo-vix-pct"]].copy()
        daily["red"] = mask & active
        daily["blue"] = blue & active
        daily["known"] = known
        daily["as_of_at"] = daily.index + "T22:30:00+08:00"
        daily.to_csv(OUT / f"{model}_daily.csv", index_label="date")
        models[model] = chosen
        attempts.extend(trials)
        print(model, len(trials), len(eligible), title(chosen["rule"]), flush=True)
    report = {"policy": POLICY, "as_of": f.index[-1], "models": models, "labels": labels,
              "data_sha256": hashlib.sha256((OUT/"features.json").read_bytes()).hexdigest(),
              "attempts": len(attempts), "production_updated": False}
    save_json(OUT/"report.json", report)
    save_json(OUT/"attempts.json", attempts)
    markdown(report)


def markdown(report):
    lines = ["# 中证1000熊市波段：极端低点覆盖优先", "",
             "按用户2026-09-29确认的新目标：允许提前，历史极端低点必须当日命中，再选相对最好条件。",
             "极端标签仅作事后评价，绝不进入在线信号。历史全覆盖不是未来保证；此轮按已看过的历史约束选型，不是独立样本外检验。",
             "只调整现有两条策略红色条件和说明，蓝色条件、仓位、次日开盘、卖出优先均保留。", "",
             "标签：事后5%反转低点附近的日内最低价，创近120个交易日新低且从近120日高点回落至少15%。",
             "按全部2022年以来标签作覆盖硬约束；增强版只要求真实可用起点之后。红色天数不得超过35%，排序看开发与验证中较弱的方向效果，再扣除逆向波动及过长亮红。",
             "首次触发后的统计与最低点当日命中分开披露，不能把一路亮红解释成提前精准预测。", ""]
    if report.get("portfolio_protocol"):
        lines += ["完整策略复核后增加了第二阶段排序：不扩大候选条件，在覆盖合格池里比较熊市区间和全区间的年化收益/最大回撤，选择两者较弱值最高者。",
                  "这一步是在看过第一阶段第一名表现后声明的追加历史选型，协议单独留存，不冒称事前一次冻结或独立样本外。", ""]
    for name, model in report["models"].items():
        lines += ["## " + ("基础版" if name == "basic" else "增强版"),
                  f"现有策略ID {model['strategy_id']}；起点 {model['start_date']}",
                  "新低点条件：" + title(model["rule"]),
                  f"历史极端覆盖 {model['coverage']}/{model['targets']}；红色占比 {model['red_day_pct']:.1f}%；覆盖合格候选 {model['eligible_count']}。",
                  "", "| 极端低点 | 当日命中 | 本段首次信号 | 提前交易日 | 首次次日开盘至低点 |",
                  "|---|---|---|---:|---:|"]
        for row in model["bottoms"]:
            adverse = "--" if row["first_entry_to_low_pct"] is None else f"{row['first_entry_to_low_pct']:.2f}%"
            lines.append(f"|{row['date']}|{row['hit']}|{row['first_signal']}|{row['lead_sessions']}|{adverse}|")
        lines += ["", "| 年份 | 版本 | 有效段数 | 先涨5% | 先跌3% | 20日中位最大逆向 |",
                  "|---|---|---:|---:|---:|---:|"]
        for version, periods in model["periods"].items():
            for year, m in periods.items():
                fmt = lambda v: "--" if v is None else f"{v:.1f}%"
                lines.append(f"|{year}|{version}|{m['evaluated']}|{fmt(m['favorable_first_pct'])}|{fmt(m['adverse_first_pct'])}|{fmt(m['median_mae20'])}|")
        lines.append("")
    lines += ["## 限制", "",
              "- 最低点当天只能在收盘后计算信号；按现有引擎下一交易日开盘执行，不代表可以买到最低价。",
              "- 增强版极端价格分支和期权确认分支是明确的或条件；某独立分支已满足时不要求另一分支存在。不是把缺失隐波填成数值，也不在预热前回退基础版。",
              "- WR/RSI/价格位置存在相关性；它们用于约束同一低位形态，不被包装成多个独立证据或重复评分。",
              "- 使用当前存储的历史版本重放；没有全部原始实时归档，存在修订偏差。",
              "- 本轮用户明确接受提前信号，所以不再沿用上一轮45%有利、35%不利的准入门槛；仍完整报告失败与回撤。",
              "- 未改变原策略1/31、回测引擎、市场环境或通知。未重启服务、未推送远端。", ""]
    (OUT/"report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True, parents=True)
    if (OUT/"protocol.json").exists():
        assert json.loads((OUT/"protocol.json").read_text())["policy"] == POLICY
    else:
        save_json(OUT/"protocol.json", {"frozen_at": datetime.now().astimezone().isoformat(), "policy": POLICY})
    if args.snapshot:
        assert not (OUT/"features.json").exists(), "Do not overwrite a frozen snapshot"
        with SessionLocal() as db:
            f = load_features(db)
            saved = [dict(r) for r in db.execute(text("SELECT * FROM quant_strategy_configs WHERE id IN (44,45)")).mappings()]
        for row in saved:
            for key in ("red_filter_groups", "blue_filter_groups", "indicator_params"):
                if isinstance(row[key], str): row[key] = json.loads(row[key])
        save_json(OUT/"saved.json", saved)
        f.to_json(OUT/"features.json", orient="table", indent=2)
        print("snapshot", len(f), f.index[-1], flush=True)
    if args.run:
        run()


if __name__ == "__main__":
    main()
