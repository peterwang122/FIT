"""Verify persisted turnover and refresh only affected CSI500 caches."""
from hashlib import sha256
import json
from pathlib import Path

from sqlalchemy import text

from app.core.redis_client import redis_client
from app.db.session import SessionLocal
from app.models.quant_strategy_config import QuantStrategyConfig
from app.services.csi500_swing_features import PUBLIC_FIELDS, feature_points
from app.services.quant_service import QuantService

OUT = Path(__file__).resolve().parents[2] / "runtime/backfill/szse_159922_turnover"


def strategies_hash(db):
    rows = [dict(r) for r in db.execute(text("SELECT * FROM quant_strategy_configs ORDER BY id")).mappings()]
    return sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def run():
    patterns = ["quant:csi500-swing:*", "fit:quant:index_dashboard:*:cn:sh000905:*",
                "fit:quant:strategy_target_chart:*:*:48:*", "fit:quant:strategy_target_chart:*:*:49:*"]
    deleted = {}
    for pattern in patterns:
        keys = list(redis_client.scan_iter(match=pattern, count=200))
        deleted[pattern] = redis_client.delete(*keys) if keys else 0
    with SessionLocal() as db:
        before = strategies_hash(db)
        coverage = [dict(r) for r in db.execute(text("""
            SELECT YEAR(trade_date) AS year,COUNT(*) AS contract_rows,
                   SUM(turnover IS NOT NULL) AS amount_rows,
                   MIN(CASE WHEN turnover IS NOT NULL THEN trade_date END) AS first_amount_date,
                   MAX(CASE WHEN turnover IS NOT NULL THEN trade_date END) AS last_amount_date
            FROM option_exchange_contract_daily_data
            WHERE exchange='SZSE' AND underlying_code='159922'
            GROUP BY YEAR(trade_date) ORDER BY year
        """)).mappings()]
        target = [dict(r) for r in db.execute(text("""
            SELECT option_type,COUNT(*) AS contracts,SUM(turnover) AS amount_yuan
            FROM option_exchange_contract_daily_data
            WHERE exchange='SZSE' AND underlying_code='159922' AND trade_date='2026-09-30'
            GROUP BY option_type
        """)).mappings()]
        points = feature_points(db)
        fields = [key for key in PUBLIC_FIELDS if "159922" in key and "turnover" in key]
        features = {}
        for field in fields:
            valid = [p for p in points if p["values"].get(field) is not None]
            features[field] = {"valid_days": len(valid), "first_date": valid[0]["trade_date"] if valid else None,
                               "last_date": valid[-1]["trade_date"] if valid else None,
                               "latest_value": valid[-1]["values"][field] if valid else None}
        charts = {}
        for strategy_id in (48, 49):
            strategy = db.get(QuantStrategyConfig, strategy_id)
            assert strategy.target_code == "sh000905"
            chart = QuantService(db).get_strategy_target_chart(strategy_id, strategy.owner_user_id)
            charts[strategy_id] = {"name": strategy.name, "data_coverage": chart.get("data_coverage"),
                                  "highlight_days": len(chart["highlight_bands"])}
        assert before == strategies_hash(db), "Strategy configuration changed"
        result = {"persisted_annual_coverage": coverage, "target_amounts": target,
                  "feature_coverage": features, "strategy_charts": charts,
                  "all_strategy_configs_unchanged": True, "cleared_cache_keys": deleted}
        (OUT / "verification.json").write_text(json.dumps(result, ensure_ascii=False, default=str, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    run()
