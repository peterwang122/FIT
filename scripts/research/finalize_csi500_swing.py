"""Install only the two approved CSI500 snapshots after application parity."""
import argparse
from datetime import date
from hashlib import sha256
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
from sqlalchemy import text

from csi500_swing import OUT, POLICY, matches, save_json, snapshot
from market_regime import evaluate_signals
from app.db.session import SessionLocal
from app.models.quant_strategy_config import QuantStrategyConfig
from app.models.user import User
from app.services.quant_service import QuantService


NAMES = {"bull": "中证500牛市波段", "bear": "中证500熊市波段"}


def payload(regime, model):
    return dict(name=NAMES[regime],
        notes=("全历史开发与选型，无训练/验证/样本外拆分；历史优化不保证未来极端覆盖。"
               "牛熊标签仅作评价，不自动开关。红色低位机会、蓝色高位风险；"
               "22:30已知信息，次日开盘，红买50%蓝卖100%，冲突卖出优先。"
               "基础覆盖2022全年；晚起分支仅在真实可用且预热完成后生效，断档不填50或0。"
               "交易代理510500；ETF成立前只评价指数信号。高点后跌幅不是实际做空收益。"
               + (f"【重要局限】熊市高位只有1段历史区域；当前510500回测最大回撤{model['backtest']['mdd_pct']:.2f}%，退出能力未得到充分证据，不建议自动执行。" if regime == "bear" else
                  "【重要局限】牛市低位只有3段历史区域，样本很少，不建议自动执行。") +
               f"规则指纹{model['config_fingerprint']}；报告runtime/reports/csi500_swing/report.md。"),
        strategy_engine="snapshot", strategy_type="index", sequence_mode="single_target",
        target_market="cn", target_code="sh000905", target_name="中证500",
        indicator_params={"ma": {"periods": [5, 10, 20, 60]}, "macd": {"fast": 12, "slow": 26, "signal": 9},
            "kdj": {"period": 9, "kSmoothing": 3, "dSmoothing": 3}, "wr": {"period": 14},
            "rsi": {"period": 14}, "boll": {"period": 20, "multiplier": 2}},
        red_filter_groups=model["low"]["rules"], blue_filter_groups=model["high"]["rules"],
        red_filters={}, blue_filters={}, red_boll_filter={}, blue_boll_filter={},
        buy_sequence_groups=[], sell_sequence_groups=[], scan_trade_config={}, research_option_template=None,
        signal_buy_color="red", signal_sell_color="blue", purple_conflict_mode="sell_first",
        start_date=date(2022, 1, 1), scan_start_date=None, scan_end_date=None,
        buy_position_pct=.5, sell_position_pct=1, execution_price_mode="next_open")


def untouched(db):
    rows = [dict(r) for r in db.execute(text("SELECT * FROM quant_strategy_configs ORDER BY id")).mappings()
            if not (r["name"] in NAMES.values() and r["target_code"] == "sh000905")]
    return sha256(json.dumps(rows, default=str, sort_keys=True).encode()).hexdigest()


def verify(report, frame):
    from app.services.csi500_swing_features import PUBLIC_FIELDS, feature_points
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        service = QuantService(db)
        before = untouched(db)
        points = feature_points(db)
        bydate = {p["trade_date"]: p["values"] for p in points}
        for day, row in frame.iterrows():
            for field in PUBLIC_FIELDS:
                actual = bydate.get(day, {}).get(field)
                expected = row[field]
                assert (actual is None and pd.isna(expected)) or actual is not None and abs(actual - expected) < 1e-7, (day, field, actual, expected)
        for regime, model in report["models"].items():
            data = payload(regime, model)
            service._validate_strategy_payload(data)
            strategy = SimpleNamespace(**data)
            candles, snapshots = service._load_fixed_strategy_target_chart(strategy)
            red, _ = matches(frame, model["low"]["rules"])
            blue, _ = matches(frame, model["high"]["rules"])
            expected = {d: "purple" if r and b else "red" if r else "blue"
                        for d, r, b in zip(frame.index, red, blue) if r or b}
            actual = service._build_signal_map(strategy, snapshots)
            assert actual == expected, (regime, "backend daily signal mismatch", list(set(actual.items()) ^ set(expected.items()))[:10])
            highlights = service._build_strategy_highlight_bands(strategy, snapshots)
            assert {h["tradeDate"]: h["color"] for h in highlights} == {d: c for d, c in expected.items() if d >= "2022-01-01"}
            for extreme in model["extreme_coverage"]:
                action = service._resolve_action(actual.get(extreme["date"]), strategy)
                assert action == ("buy" if extreme["side"] == "low" else "sell"), (regime, extreme, action)
            filtered, colors, pending, initial = service._build_equity_curve_context(strategy)
            actual_curve = service._simulate_equity_curve(filtered_prices=filtered, signal_map=colors,
                pending_actions=pending, initial_close=initial, buy_ratio=.5, sell_ratio=1,
                execution_price_mode="next_open", include_signals=True)
            prices = [{"date": str(r["trade_date"]), **{k: float(r[k]) for k in ("open", "high", "low", "close")}} for r in filtered]
            independent = evaluate_signals(prices, {d: "red" if service._resolve_action(c, strategy) == "buy" else "blue"
                for d, c in colors.items() if d >= "2022-01-01" and service._resolve_action(c, strategy)}, buy=.5, sell=1, cost=0)
            assert abs(independent["return_pct"] - actual_curve["cumulative_return_pct"]) < 1e-7
            assert abs(independent["mdd_pct"] - actual_curve["max_drawdown_pct"]) < 1e-7
            model["backtest"] = {k: v for k, v in independent.items() if k not in {"points", "trades"}}
            model["backtest"].update(etf_code="510500", start=prices[0]["date"], end=prices[-1]["date"],
                                    costs="Existing FIT snapshot engine: no fee/slippage model; not added here")
            pd.DataFrame(independent["trades"]).to_csv(OUT / f"{regime}_etf_trades.csv", index=False)
            save_json(OUT / f"{regime}_chart_fixture.json", {"candles": candles, "points": points,
                "params": data["indicator_params"], "rules": {"red": data["red_filter_groups"], "blue": data["blue_filter_groups"]},
                "expected_colors": actual})
            print("verified", regime, model["backtest"], flush=True)
        assert before == untouched(db)
        db.rollback()
        report["verification"] = {"features_filters_highlights_daily_parity": True, "sell_first_extremes": True,
                                  "etf_existing_engine_parity": True, "untouched_strategy_sha256": before}
        return before


def install(report, expected_hash):
    with SessionLocal() as db:
        assert untouched(db) == expected_hash, "Unrelated strategy changed during verification; stop"
        root = db.query(User).filter(User.username == "root").with_for_update().one()
        for regime, model in report["models"].items():
            data = payload(regime, model)
            existing = db.query(QuantStrategyConfig).filter(QuantStrategyConfig.owner_user_id == root.id,
                QuantStrategyConfig.name == data["name"], QuantStrategyConfig.target_code == "sh000905").with_for_update().one_or_none()
            if existing is None:
                existing = QuantStrategyConfig(owner_user_id=root.id, **data)
                db.add(existing)
            else:
                for key, value in data.items():
                    setattr(existing, key, value)
            db.flush()
            model["strategy_id"] = existing.id
        assert untouched(db) == expected_hash
        db.commit()
        assert untouched(db) == expected_hash
        report["production_updated"] = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    report = json.loads((OUT / "report.json").read_text())
    assert report["policy"]["version"] == POLICY["version"], "Stale research protocol; do not install"
    for model in report["models"].values():
        assert max(model["effective_formal_color_pct"].values()) <= POLICY["max_color_day_pct"]
        assert model["paired_selection"]["sell_first_ranked"]
    frame, _ = snapshot()
    expected_hash = verify(report, frame)
    if args.install:
        frontend = json.loads((OUT / "frontend_verification.json").read_text())
        assert all(frontend[r]["all_daily_signals_match"] for r in NAMES)
        install(report, expected_hash)
    save_json(OUT / "report.json", report)
    path = OUT / "report.md"
    lines = ["", "## 实际应用一致性与510500交易回测", "",
             "研究、后端筛选、K线高亮和卖出优先后的极端覆盖已逐日核对。ETF回测与原引擎一致，不修改引擎或费用。",
             "原引擎没有手续费/滑点模型，以下并非已扣实际交易成本；高位方向评价不代表做空收益。", "",
             "| 策略 | ID | 累计收益 | 最大回撤 |", "|---|---|---:|---:|"]
    for regime, model in report["models"].items():
        bt = model["backtest"]
        lines.append(f"|{NAMES[regime]}|{model.get('strategy_id', '未保存')}|{bt['return_pct']:.2f}%|{bt['mdd_pct']:.2f}%|")
    path.write_text(path.read_text().split("\n## 实际应用一致性")[0] + "\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
