"""Publish the independent snapshot and a descriptive, non-trading validation report."""

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import SessionLocal
from app.services.market_regime_research import publish_snapshot


def evaluate(points):
    """Chronological annual cohorts; future outcomes never enter today's features."""
    groups = defaultdict(list)
    daily = []
    for i, point in enumerate(points):
        row = {k: point[k] for k in ("date", "close", "trend_supportive", "trend_plus_participation",
                                     "index_participation_ma60_pct", "index_participation_ma120_pct")}
        for horizon in (20, 60, 120):
            future = points[i + 1:i + horizon + 1]
            complete = len(future) == horizon
            row[f"return_{horizon}d_pct"] = (future[-1]["close"] / point["close"] - 1) * 100 if complete else None
            row[f"worst_close_{horizon}d_pct"] = (min(p["close"] for p in future) / point["close"] - 1) * 100 if complete else None
        daily.append(row)
        for candidate in ("trend_supportive", "trend_plus_participation"):
            if row[candidate] is not None:
                groups[(str(row["date"])[:4], candidate, row[candidate])].append(row)
    summary = []
    for (year, candidate, state), rows in sorted(groups.items()):
        result = {"year": year, "candidate": candidate, "supportive": state, "days": len(rows)}
        for horizon in (20, 60, 120):
            values = [r[f"return_{horizon}d_pct"] for r in rows if r[f"return_{horizon}d_pct"] is not None]
            result[f"valid_{horizon}d"] = len(values)
            result[f"mean_{horizon}d_return_pct"] = sum(values) / len(values) if values else None
        summary.append(result)
    return daily, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("target_date", type=date.fromisoformat)
    parser.add_argument("--as-of", type=datetime.fromisoformat)
    args = parser.parse_args()
    with SessionLocal() as db:
        report = publish_snapshot(db, args.target_date, args.as_of)
    daily, evaluation = evaluate(report["daily_points"])
    output = ROOT / "runtime/reports/market_regime"
    with (output / "lightweight_daily.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(daily[0]))
        writer.writeheader()
        writer.writerows(daily)
    (output / "lightweight_evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, default=str, indent=2))
    lines = ["# 市场环境轻量模型候选验证", "", f"截至：{report['as_of_at']}（上海时间）；指数至{args.target_date}。",
             "", "## 结论边界", "", "旧牛熊模型与交易权限未修改。本报告不是批准上线的新牛熊规则。",
             "趋势候选固定为中证全指站上MA120且MA120较20交易日前上升；参与度候选额外要求至少2/3宽基指数站上MA120。未围绕已知拐点调参。",
             "趋势及参与度按年度列出后续20/60/120交易日表现，尾部不足窗口不纳入均值。重叠窗口有相关性，不把样本数当独立交易次数。",
             "宏观历史归档从本次抓取才有版本留存，不能伪造2005年以来当时可见的严格回测。宏观增量模型暂不排名、不定权。",
             "牛市误停、牛转熊识别、熊转牛延迟尚需冻结参考周期标注及候选切换规则；未将上述描述性统计冒充这三项验收。",
             "", "## 官方覆盖", "", "|序列|口径|频率|最早所属期|最新所属期|独立月份|", "|---|---|---|---|---|---|"]
    for r in report["coverage"]:
        lines.append(f"|{r['series_key']}|{r['basis_version']}|{r['period_kind']}|{r['first_period']}|{r['last_period']}|{r['independent_months']}|")
    lines += ["", "## 历史缺口", "", "下列为各系列已覆盖区间内未找到原值的月份；不插值、不估算。工业利润一月单独列作制度性未披露。"]
    for r in report['coverage']:
        if r['missing_periods']:
            lines.append(f"- {r['series_key']} / {r['period_kind']} / {r['basis_version']}：" + ', '.join(r['missing_periods']))
    lines += ["", "## 文件", "", "- `lightweight.json`：每日研究快照与宏观证据。",
              "- `lightweight_daily.csv`：逐日特征和后续表现。", "- `lightweight_evaluation.json`：按年度的候选对照。",
              "", "## 当前缺口", "", ", ".join(report["missing_macro"] + report['stale_macro']) or "本次截止时点所需宏观系列均可读；不代表2005年以来无缺口。"]
    (output / "lightweight_validation.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"target_date": str(args.target_date), "days": len(daily),
                      "macro_evidence": len(report["macro_evidence"]), "missing": report["missing_macro"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
