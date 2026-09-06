"""Publish a validated, read-only research snapshot; no DB, tasks, or strategy writes."""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.schemas.market_regime import RegimeReport  # noqa: E402


def publish(inputs: Path, target: Path):
    study = inputs / "legacy-hfq-study"
    manifest = json.loads((study / "manifest.json").read_text())
    if manifest["breadth_kind"] != "legacy_hfq_observed_stocks" or manifest["production_approved"]:
        raise ValueError("Only unapproved, adjusted research snapshots may be published here")
    series = {}
    for index, name in (("sh000852", "中证1000"), ("sh000985", "中证全指")):
        prices = {row["date"]: row for row in json.loads((inputs / f"{index}.json").read_text())}
        with (study / f"{index}_balanced-daily.csv").open() as file:
            points = []
            for row in csv.DictReader(file):
                point = {key: value or None for key, value in row.items()}
                point.update({key: prices[row["date"]][key] for key in ("open", "high", "low")})
                point["buy_multiplier"] = float(row["buy_multiplier"])
                if row["date"] > manifest["strategy_evaluation_end"]:
                    for key in ("observed", "traded", "eligible"):
                        point[key] = None
                points.append(point)
        with (study / f"{index}_balanced-events.csv").open() as file:
            events = [{key: value or None for key, value in row.items()} for row in csv.DictReader(file)]
        series[index] = {"index_name": name, "points": points, "events": events}
    report = RegimeReport.model_validate({
        "schema_version": "market-regime-research-v1", "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")),
        "research_only": True, "model_approved": False, "rule_name": "balanced",
        "breadth_as_of": manifest["strategy_evaluation_end"], "series": series,
        "notes": [
            "研究候选尚未通过模型验收，不控制策略、买卖或通知。",
            "旧表后复权广度，未与未复权数据拼接；历史退市范围和调整版本待审计。",
            "2005至2011年及2015年部分日期广度覆盖不足，不视为风险解除。",
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
