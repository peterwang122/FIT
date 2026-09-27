"""Recompute fixed candidate regimes and save an auditable historical comparison."""
import argparse
from collections import Counter, defaultdict
from datetime import date, datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.session import SessionLocal
from app.services.market_regime_research import publish_snapshot
from app.services.market_regime_model import cycle_points, MODEL_VERSION, RULES
from app.services.market_regime_service import _proxy_points, _events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target_date", type=date.fromisoformat)
    args = parser.parse_args()
    with SessionLocal() as db:
        snapshot = publish_snapshot(db, args.target_date)
    summary = {"model": MODEL_VERSION, "generated_at": datetime.now().isoformat(),
               "target_date": str(args.target_date), "rules": RULES, "indexes": {}}
    output = ROOT / "runtime/reports/market_regime"
    for code in ("sh000985", "sh000300", "sh000852"):
        current = cycle_points(snapshot, code)
        old = {str(p["date"]): p for p in _proxy_points(snapshot, code)}
        price_snapshot = {**snapshot, "macro_regime_timeline": []}
        price_only = cycle_points(price_snapshot, code)
        annual = defaultdict(Counter)
        for p in current:
            annual[p["date"][:4]][p["state"]] += 1
            annual[p["date"][:4]]["macro_complete"] += int(p["macro_complete"])
        transitions = []
        for i, p in enumerate(current):
            if i and p["state"] == current[i-1]["state"]:
                continue
            entry = {"date": p["date"], "state": p["state"], "macro_complete": p["macro_complete"]}
            for n in (20, 60, 120):
                future = current[i+1:i+1+n]
                complete = len(future) == n and all(q.get("low") is not None for q in future)
                entry[f"return_{n}d_pct"] = (future[-1]["close"] / p["close"] - 1) * 100 if complete else None
                entry[f"worst_{n}d_pct"] = (min(q["low"] for q in future) / p["close"] - 1) * 100 if complete else None
            transitions.append(entry)
        detail = {"points": current, "transitions": transitions, "events": _events(current),
                  "previous_states": {day: p["state"] for day, p in old.items()}}
        (output / f"cycle_{code}.json").write_text(json.dumps(detail, default=str, ensure_ascii=False))
        summary["indexes"][code] = {"latest": current[-1], "annual": annual,
            "changed_days": sum(p["state"] != old[p["date"]]["state"] for p in current if p["date"] in old),
            "macro_changed_days": [p["date"] for p, b in zip(current, price_only) if p["state"] != b["state"]],
            "recent_transitions": [t for t in transitions if t["date"] >= "2024-09-18"],
            "strict_macro_start": next((p["date"] for p in current if p["macro_complete"]), None)}
    (output / "cycle_validation.json").write_text(json.dumps(summary, default=str, ensure_ascii=False, indent=2))
    lines = ["# 市场环境重算：market-cycle-v1", "", f"截至{args.target_date}",
             "规则在本次计算前固定，没有按9·24之后收益挑选阈值；仍属研究候选，不是独立样本外验证。",
             "未接入任何实际策略、停买或通知。宏观缺少当时版本时，仅计算指数基线，不能冒充完整宏观回测。",
             "M1/M2剪刀差的3个月变化与社融同比变化同向构成一组；PMI及新订单三月均值与变化构成一组；工业利润及营收官方累计同比同向构成一组。",
             "至少两组宏观走弱可将结构性转弱/转熊确认由10日缩短至5日；至少两组改善可将价格修复确认由5日缩短至3日。宏观单独不能翻转状态。",
             "缺失不是中性：无宏观确认时保留明确标注的指数基线；不使用未来值，不跨M1口径计算变化。",
             "物价、信贷结构等仍展示为背景，不在未验证情况下重复计入。", "",
             *[f"- {key}: {value}" for key, value in RULES.items()], "",
             "暂未宣称牛熊拐点提前命中率：需要预先冻结独立历史周期标签；状态切换后收益不等于可交易收益。"]
    for code, data in summary["indexes"].items():
        lines += ["", f"## {code}", f"最新状态：{data['latest']['state']}；宏观：{data['latest']['macro_status']}",
                  f"严格宏观完整起点：{data['strict_macro_start']}；与纯指数模型不同的日数：{len(data['macro_changed_days'])}",
                  "", "|年份|牛市|牛市内调整|转弱|熊市|修复|宏观完整日|", "|---|---:|---:|---:|---:|---:|---:|"]
        for year, counts in sorted(data["annual"].items()):
            lines.append(f"|{year}|" + "|".join(str(counts[k]) for k in ("valid", "adjustment", "warning", "invalid", "repair", "macro_complete")) + "|")
    (output / "cycle_validation.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({code: {"latest": {k: row["latest"].get(k) for k in ("date", "state", "state_since", "trigger_rule", "macro_status")},
                            "strict_macro_start": row["strict_macro_start"], "macro_changed_days": row["macro_changed_days"]}
                      for code, row in summary["indexes"].items()}, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
