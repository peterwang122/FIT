"""Publish a validated, read-only research snapshot; no DB, tasks, or strategy writes."""

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.schemas.market_regime import RegimeReport  # noqa: E402


def coverage_gaps(points):
    gaps, current = [], []
    for point in [*points, None]:
        if point is not None and point["state"] == "unavailable":
            current.append(point)
        elif current:
            coverage = [float(row["coverage_pct"]) for row in current if row.get("coverage_pct") is not None]
            gaps.append({"start": current[0]["date"], "end": current[-1]["date"], "days": len(current),
                         "min_coverage_pct": min(coverage) if coverage else None,
                         "max_coverage_pct": max(coverage) if coverage else None,
                         "reasons": sorted({reason for row in current for reason in row.get("missing_reasons", [])})})
            current = []
    return gaps


def publish(inputs: Path, target: Path):
    study = inputs / "legacy-hfq-study"
    manifest = json.loads((study / "manifest.json").read_text())
    if manifest["breadth_kind"] != "legacy_hfq_observed_stocks" or manifest["production_approved"]:
        raise ValueError("Only unapproved, adjusted research snapshots may be published here")
    for filename, digest in manifest.get("input_sha256", {}).items():
        if Path(filename).name != filename or hashlib.sha256((inputs / filename).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Research input changed; recompute before publication: {filename}")
    breadth_as_of = manifest.get("breadth_as_of", manifest["strategy_evaluation_end"])
    series = {}
    for index, name in (("sh000852", "中证1000"), ("sh000985", "中证全指")):
        prices = {row["date"]: row for row in json.loads((inputs / f"{index}.json").read_text())}
        with (study / f"{index}_balanced-daily.csv").open() as file:
            points = []
            for row in csv.DictReader(file):
                point = {key: value or None for key, value in row.items()}
                point.update({key: prices[row["date"]][key] for key in ("open", "high", "low")})
                point["buy_multiplier"] = float(row["buy_multiplier"])
                point["missing_reasons"] = json.loads(row.get("missing_reasons") or "[]")
                if row["date"] > breadth_as_of:
                    for key in ("observed", "traded", "eligible", "coverage_pct"):
                        point[key] = None
                points.append(point)
        with (study / f"{index}_balanced-events.csv").open() as file:
            events = [{key: value or None for key, value in row.items()} for row in csv.DictReader(file)]
        for event in events:
            event["states"] = json.loads(event.get("states") or "[]")
        series[index] = {"index_name": name, "points": points, "events": events, "coverage_gaps": coverage_gaps(points)}
    report = RegimeReport.model_validate({
        "schema_version": "market-regime-research-v1", "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")),
        "research_only": True, "model_approved": False, "rule_name": "balanced",
        "breadth_as_of": breadth_as_of, "strategy_evaluation_end": manifest["strategy_evaluation_end"],
        "breadth_sources": manifest.get("breadth_sources", []), "series": series,
        "notes": [
            "研究候选尚未通过模型验收，不控制策略、买卖或通知。",
            "全A历史观察股票后复权广度；各来源分别计算完整均线后衔接广度，不拼接复权价格。历史退市范围和调整版本待审计。",
            "完整120日窗口不足可能来自停牌、新股或原始缺口；未经逐股核实，不将其直接归因于停牌。缺失区间不算成功停买或风险解除。",
            "静态研究快照，不是实时日更；资金、信用和盈利未进入当前许可规则。",
        ],
    })
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(report.model_dump_json(), encoding="utf-8")
    temporary.replace(target)
    print(f"Published {target}: " + ", ".join(f"{key}={len(value.points)}" for key, value in report.series.items()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "runtime/reports/market_regime/report.json")
    args = parser.parse_args()
    publish(args.input, args.output)
