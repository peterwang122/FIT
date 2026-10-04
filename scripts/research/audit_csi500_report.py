"""Finish coverage and comparison disclosures without another parameter search."""
import json
from collections import Counter

import numpy as np
import pandas as pd

from csi500_swing import OUT, save_json, snapshot
from app.services.csi500_swing_features import PUBLIC_FIELDS


def main():
    frame, catalog = snapshot()
    report = json.loads((OUT / "report.json").read_text())
    rows = []
    for key, meta in catalog.items():
        values = frame[key] if key in frame else pd.Series(np.nan, index=frame.index)
        valid = values.notna()
        dates = frame.index[valid]
        inside = (frame.index >= dates[0]) & (frame.index <= dates[-1]) if len(dates) else np.zeros(len(frame), dtype=bool)
        unit_verified = meta["unit"] not in {"official source unit", "源成交量单位"}
        if key in PUBLIC_FIELDS:
            unit_verified = True
        rows.append({**{k: meta.get(k) for k in ("key", "label", "source", "unit", "eligibility", "reason", "frequency",
                    "transform", "first_source_date", "first_available_date", "observations", "valid_days", "publication",
                    "research_status", "selection_reason")},
            "unit_verified": unit_verified, "last_valid_date": dates[-1] if len(dates) else None,
            "missing_target_sessions_in_own_span": int((inside & ~valid).sum()),
            "warmup": "prior 252 valid observations; maximum 1260; exclude current" if meta["transform"] == "prior-percentile" else meta["transform"]})
    pd.DataFrame(rows).to_csv(OUT / "coverage.csv", index=False)
    increment = json.loads((OUT / "incremental.json").read_text())
    for row in increment:
        valid = bool(row["candidate"]["evaluated"] and row["baseline"]["evaluated"])
        row["comparison_status"] = "comparable" if valid else "no_evaluated_baseline_or_candidate"
        row["delta_score"] = row["candidate"]["score"] - row["baseline"]["score"] if valid else None
    save_json(OUT / "incremental.json", increment)
    pd.DataFrame([{k: v for k, v in row.items() if k not in {"rules", "candidate", "baseline"}} for row in increment]).to_csv(OUT / "incremental.csv", index=False)
    report["coverage_audit"] = {
        "fields": len(rows), "status_counts": dict(Counter(row["research_status"] for row in rows)),
        "unverified_raw_units": sum(not row["unit_verified"] for row in rows),
        "unscanned_detail_tables": "Explicit blocked inventory in tables.json; no claim that every stock/contract row was trained",
        "backcast": "Pre-publication index history is diagnostic development history, not an executable historical signal. Formal saved strategy replay starts in 2022, after all selected source publications.",
        "invalid_increment_comparisons": sum(row["delta_score"] is None for row in increment),
    }
    save_json(OUT / "report.json", report)
    path = OUT / "report.md"
    lines = ["", "## 覆盖审计与不可比较项", "",
        "逐项可得起点、预热、来源时间、缺口、研究状态及单位核验见coverage.csv；原始表阻断原因见tables.json。",
        "全部现有市场级序列进入候选清单；未聚合的个股、分钟与逐合约明细不当作独立日频市场因子，也未宣称逐行训练。",
        f"{report['coverage_audit']['unverified_raw_units']}项非入选原值/派生值仍沿用源单位说明，未独立核验单位，不能据此跨源比较绝对数值。正式入选项单位已明确。",
        "指数发布前的历史回算只作诊断开发记录，不能称为当时可执行信号。正式保存策略从2022年回溯；选中来源均已公开。",
        "共同窗口里任一侧没有已完成评价的信号区域时，增量为空，不能拿内部无样本哨兵分计算‘提升1000分’。全部原始尝试保留。", "",
        "| 环境 | 方向 | 期权来源 | 记录数 | 可比较数 | 最高可比较增量 |", "|---|---|---|---:|---:|---:|"]
    for regime in ("bull", "bear"):
        for side in ("low", "high"):
            for source in ("sse:510500", "szse:159922"):
                records = [row for row in increment if row["regime"] == regime and row["side"] == side and source in row["source"]]
                comparable = [row["delta_score"] for row in records if row["delta_score"] is not None]
                best = f"{max(comparable):.2f}" if comparable else "无法评价"
                lines.append(f"|{regime}|{side}|{source}|{len(records)}|{len(comparable)}|{best}|")
    current = path.read_text().split("\n## 覆盖审计与不可比较项")[0]
    start = current.index("\n## 两套ETF期权的共同窗口增量")
    end = current.index("\n## 卖出优先后的最终规则与局限", start)
    current = current[:start] + "\n## 两套ETF期权的共同窗口增量\n\n两来源均实际扫描；可比较增量见文末审计表，空基线不计增量。\n" + current[end:]
    path.write_text(current + "\n".join(lines) + "\n", encoding="utf-8")
    print(report["coverage_audit"])


if __name__ == "__main__":
    main()
