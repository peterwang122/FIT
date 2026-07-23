#!/usr/bin/env python3
"""Import balanced VIX research templates as saved quant index strategies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.db.session import SessionLocal  # noqa: E402
from app.models.quant_strategy_config import QuantStrategyConfig  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.quant_service import QuantService  # noqa: E402


DEFAULT_REPORT = REPO_ROOT / "runtime" / "reports" / "vix_option_analysis" / "report.json"
INDEX_CODES = {
    "上证50": "sh000016",
    "沪深300": "sh000300",
    "中证500": "sh000905",
    "科创50": "sh000688",
    "中证1000": "sh000852",
}
REFERENCE_VIX_FIELDS = {
    "沪深300": "reference-vix-hs300-high",
    "中证500": "reference-vix-csi500-high",
}
DEFAULT_INDICATOR_PARAMS = {
    "ma": {"periods": [5, 10, 20, 60]},
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "kdj": {"period": 9, "kSmoothing": 3, "dSmoothing": 3},
    "wr": {"period": 14},
    "rsi": {"period": 14},
    "boll": {"period": 20, "multiplier": 2},
}
EXPIRY_BUCKET_KEYS = {
    "当月": "current",
    "下月": "next",
    "季月1": "quarter_1",
    "季月2": "quarter_2",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--username", default="root")
    return parser.parse_args()


def _balanced_model(summary: dict) -> dict:
    for model in summary.get("threshold_models") or []:
        if model.get("mode") == "balanced":
            return model
    raise ValueError(f"{summary.get('index_name') or '未知指数'}缺少综合最优模板")


def _rule_groups(index_name: str, model: dict) -> list[dict]:
    source_thresholds = model.get("source_thresholds") or []
    if source_thresholds:
        groups = []
        for item in source_thresholds:
            source_name = str(item.get("source_name") or "").strip()
            field = REFERENCE_VIX_FIELDS.get(source_name)
            if not field:
                raise ValueError(f"{index_name}存在未支持的参考VIX来源：{source_name}")
            groups.append(
                {
                    "conditions": [
                        {
                            "type": "numeric",
                            "field": field,
                            "operator": "episode_start",
                            "value": float(item["threshold"]),
                        }
                    ]
                }
            )
        return groups

    threshold = model.get("threshold")
    if threshold is None:
        raise ValueError(f"{index_name}综合最优模板缺少绝对阈值")
    return [
        {
            "conditions": [
                {
                    "type": "numeric",
                    "field": "vix-high",
                    "operator": "episode_start",
                    "value": float(threshold),
                }
            ]
        }
    ]


def _threshold_text(model: dict) -> str:
    source_thresholds = model.get("source_thresholds") or []
    if source_thresholds:
        return " 或 ".join(
            f"{item['source_name']}采集VIX高>={float(item['threshold']):g}"
            for item in source_thresholds
        )
    return f"采集VIX高>={float(model['threshold']):g}"


def _notes(report: dict, index_name: str, model: dict) -> str:
    rec = model.get("recommendation") or {}
    generated_at = str(report.get("generated_at") or "")[:10]
    return (
        f"研究成果综合最优模板（报告{generated_at}）。信号：{_threshold_text(model)}；"
        f"执行：{rec.get('exchange', '-')}/{rec.get('product_name', '-')}，"
        "按信号前走势动态选择单买认购或认沽，"
        f"{rec.get('dte_bucket', '-')}，{rec.get('moneyness_label', '-')}，"
        f"下一交易日开盘买入，持有{rec.get('holding_days', '-')}个交易日。"
        "原研究报告用于确定产品、期限、档位和持有周期；逐笔方向、成交与收益以下方动态回放为准。"
        "仅用于复现研究信号，不代表未来收益。"
    )


def _research_option_template(report: dict, model: dict) -> dict:
    recommendation = model.get("recommendation") or {}
    expiry_label = str(recommendation.get("dte_bucket") or "").strip()
    expiry_bucket = EXPIRY_BUCKET_KEYS.get(expiry_label)
    if not expiry_bucket:
        raise ValueError(f"研究模板存在未支持的到期月份：{expiry_label or '-'}")
    return {
        "enabled": True,
        "report_generated_at": report.get("generated_at"),
        "direction_mode": "dynamic",
        "product_code": recommendation.get("product_code"),
        "product_name": recommendation.get("product_name"),
        "exchange": recommendation.get("exchange"),
        "option_type": recommendation.get("option_type"),
        "strategy_type": recommendation.get("strategy_type"),
        "expiry_bucket": expiry_bucket,
        "expiry_bucket_label": expiry_label,
        "moneyness": recommendation.get("moneyness"),
        "moneyness_label": recommendation.get("moneyness_label"),
        "holding_days": recommendation.get("holding_days"),
        "slippage": float((report.get("methodology") or {}).get("slippage") or 0.005),
        "initial_capital": 1_000_000,
        "contracts_per_trade": 1,
    }


def _payload(report: dict, summary: dict) -> dict:
    index_name = str(summary["index_name"])
    model = _balanced_model(summary)
    return {
        "name": f"研究综合最优-{index_name}-VIX期权",
        "notes": _notes(report, index_name, model),
        "strategy_engine": "snapshot",
        "sequence_mode": "single_target",
        "strategy_type": "index",
        "target_market": "cn",
        "target_code": INDEX_CODES[index_name],
        "target_name": index_name,
        "indicator_params": DEFAULT_INDICATOR_PARAMS,
        "buy_sequence_groups": [],
        "sell_sequence_groups": [],
        "scan_trade_config": {},
        "research_option_template": _research_option_template(report, model),
        "blue_filter_groups": _rule_groups(index_name, model),
        "red_filter_groups": [],
        "blue_filters": {},
        "red_filters": {},
        "blue_boll_filter": {},
        "red_boll_filter": {},
        "signal_buy_color": "blue",
        "signal_sell_color": "red",
        "purple_conflict_mode": "sell_first",
        "start_date": None,
        "scan_start_date": None,
        "scan_end_date": None,
        "buy_position_pct": 1,
        "sell_position_pct": 1,
        "execution_price_mode": "next_open",
    }


def _verify_strategy(service: QuantService, item: QuantStrategyConfig) -> tuple[int, str, dict]:
    candles = service.stock_service.list_index_daily_kline(item.target_code, market="cn")
    snapshots = service._build_index_snapshots_for_market(
        "cn",
        item.target_code,
        item.target_name,
        item.indicator_params or {},
        candles,
    )
    signal_map = service._build_signal_map(item, snapshots)
    signal_dates = sorted(signal_map)
    if not signal_dates:
        raise ValueError(f"{item.name}回放后没有任何命中")
    option_result = service.calculate_research_option_trades(item.id, int(item.owner_user_id))
    return len(signal_dates), signal_dates[-1], option_result["summary"]


def main() -> int:
    args = parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    summaries = report.get("index_summaries") or []
    missing = set(INDEX_CODES) - {str(item.get("index_name") or "") for item in summaries}
    if missing:
        raise ValueError(f"研究报告缺少指数：{', '.join(sorted(missing))}")

    with SessionLocal() as db:
        owner = db.query(User).filter(User.username == args.username).first()
        if owner is None:
            raise ValueError(f"用户不存在：{args.username}")
        service = QuantService(db)
        for summary in summaries:
            index_name = str(summary.get("index_name") or "")
            if index_name not in INDEX_CODES:
                continue
            payload = _payload(report, summary)
            existing = (
                db.query(QuantStrategyConfig)
                .filter(
                    QuantStrategyConfig.owner_user_id == owner.id,
                    QuantStrategyConfig.name == payload["name"],
                )
                .first()
            )
            if existing is None:
                saved = service.create_strategy(payload, owner.id)
                action = "created"
            else:
                saved = service.update_strategy(existing.id, payload, owner.id)
                action = "updated"
            saved_item = db.query(QuantStrategyConfig).filter(QuantStrategyConfig.id == saved["id"]).one()
            hit_count, latest_hit, trade_summary = _verify_strategy(service, saved_item)
            print(
                f"{action}: id={saved['id']} {saved['name']} "
                f"groups={len(saved['blue_filter_groups'])} hits={hit_count} latest={latest_hit} "
                f"option_trades={trade_summary['completed_count']} "
                f"pending={trade_summary['pending_count']} "
                f"direction_mismatch={trade_summary['direction_mismatch_count']} "
                f"not_listed={trade_summary['not_listed_count']} "
                f"unavailable={trade_summary['unavailable_count']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
