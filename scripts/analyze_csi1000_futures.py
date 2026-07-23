from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.services.csi1000_futures_analysis import build_report  # noqa: E402


REPORT_DIR = REPO_ROOT / "runtime" / "reports" / "csi1000_futures_analysis"
LEGACY_REPORT_FILES = ("cycle_methods.csv", "trades.csv")


def money(value: object) -> str:
    try:
        return f"{float(value):,.2f}元"
    except (TypeError, ValueError):
        return "-"


def write_markdown(report: dict) -> None:
    sample = report["sample"]
    lines = [
        f"# {report['title']}",
        "",
        f"生成时间：{report['generated_at']}",
        f"数据区间：{report['data_range']['start']} 至 {report['data_range']['end']}",
        (
            f"20% ZigZag共识别{sample['wave_count']}段："
            f"上涨{sample['up_wave_count']}段、下跌{sample['down_wave_count']}段，"
            f"其中{sample['provisional_wave_count']}段尚未由反向20%行情确认。"
        ),
        "",
        "## 逐波段合约收益",
        "",
    ]
    for wave in report["waves"]:
        best = next(
            (item for item in wave["contract_results"] if item["result_id"] == wave["best_result_id"]),
            None,
        )
        lines.extend(
            [
                f"### 波段{wave['wave_id']} · {wave['direction_label']}{'（进行中）' if not wave['complete'] else ''}",
                "",
                (
                    f"- {wave['start_date']} {wave['start_value']} → "
                    f"{wave['end_date']} {wave['end_value']}，指数变化 {wave['index_change_pct']}%。"
                ),
                (
                    f"- 回望收益最高：{best['start_contract']}（{best['tenor_label']}），"
                    f"净收益 {money(best['net_pnl'])}，路径 "
                    + " → ".join(item["contract"] for item in best["contract_path"])
                    + "。"
                ) if best else "- 没有可完整计算的合约。",
                "",
            ]
        )
    lines.extend(
        [
            "## 口径",
            "",
            "- 波段完全由中证1000日K按20% ZigZag划分，与任何保存策略或红蓝信号无关。",
            "- 上涨段：指数低点日按各期货合约当日最低价做多，高点日按当日最高价平仓。",
            "- 下跌段：指数高点日按各期货合约当日最高价做空，低点日按当日最低价平仓。",
            "- 波段起点当日所有实际挂牌且有成交的IM数字合约逐份计算，不限制为四份。",
            "- 持仓期间禁止主动换月；只有旧合约到期后，才在下一交易日开盘接入新的近月合约。",
            "- 这是使用已知高低点及当日最优成交价的回望收益上限，不是可实时复制的交易信号。",
        ]
    )
    (REPORT_DIR / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(report: dict) -> None:
    columns = [
        "wave_id",
        "direction",
        "complete",
        "start_date",
        "start_index",
        "end_date",
        "end_index",
        "index_change_pct",
        "rank",
        "tenor_label",
        "start_contract",
        "start_expiry",
        "entry_price",
        "exit_contract",
        "exit_price",
        "roll_count",
        "gross_points",
        "gross_pnl",
        "fee",
        "net_pnl",
        "notional_return_pct",
        "contract_path",
    ]
    with (REPORT_DIR / "wave_contract_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for wave in report["waves"]:
            for result in wave["contract_results"]:
                writer.writerow(
                    {
                        "wave_id": wave["wave_id"],
                        "direction": wave["direction"],
                        "complete": wave["complete"],
                        "start_date": wave["start_date"],
                        "start_index": wave["start_value"],
                        "end_date": wave["end_date"],
                        "end_index": wave["end_value"],
                        "index_change_pct": wave["index_change_pct"],
                        "rank": result.get("rank"),
                        "tenor_label": result.get("tenor_label"),
                        "start_contract": result.get("start_contract"),
                        "start_expiry": result.get("start_expiry"),
                        "entry_price": result.get("entry_price"),
                        "exit_contract": result.get("exit_contract"),
                        "exit_price": result.get("exit_price"),
                        "roll_count": result.get("roll_count"),
                        "gross_points": result.get("gross_points"),
                        "gross_pnl": result.get("gross_pnl"),
                        "fee": result.get("fee"),
                        "net_pnl": result.get("net_pnl"),
                        "notional_return_pct": result.get("notional_return_pct"),
                        "contract_path": " → ".join(
                            f"{item['contract']}({item['start_date']}~{item['end_date']})"
                            for item in result.get("contract_path") or []
                        ),
                    }
                )


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    for filename in LEGACY_REPORT_FILES:
        (REPORT_DIR / filename).unlink(missing_ok=True)
    with SessionLocal() as db:
        report = build_report(db)
    (REPORT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(report)
    write_csv(report)
    print(
        json.dumps(
            {
                "report": str(REPORT_DIR / "report.json"),
                "sample": report["sample"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
