"""Verify and idempotently install two coverage-specific CSI500 strategies."""
import argparse
from datetime import date
from hashlib import sha256
import json
from types import SimpleNamespace

import pandas as pd
from sqlalchemy import text

from csi500_coverage_restudy import OUT
from csi500_swing import matches, save_json, snapshot
from finalize_csi500_swing import payload as legacy_payload
from report_csi500_coverage import replay
from app.db.session import SessionLocal
from app.models.quant_strategy_config import QuantStrategyConfig
from app.models.user import User
from app.services.csi500_swing_features import PUBLIC_FIELDS, VERSION, config_fingerprint, feature_points
from app.services.quant_service import QuantService

NAMES = {"bull": "中证500牛市波段-期权版", "bear": "中证500熊市波段-期权版"}


def payload(regime, pair):
    fingerprint = config_fingerprint({"red": pair["low"]["rules"], "blue": pair["high"]["rules"]})
    stub = {**pair, "config_fingerprint": fingerprint, "backtest": pair["backtest"]["candidate"]}
    data = legacy_payload(regime, stub)
    data.update(name=NAMES[regime], start_date=date.fromisoformat(pair["start_date"]), notes=(
        f"覆盖期独立策略，自{pair['start_date']}起回溯，不拼接早期版本。"
        "全历史开发与优化，没有样本外验证；历史极端命中不保证未来。"
        "牛熊标签仅用于评价，不自动开关。22:30已知数据，次日开盘；"
        "红色买入50%、蓝色卖出100%、冲突卖出优先。交易代理510500，现有引擎不扣实际交易成本。"
        "510500与159922期权分源，分位用此前最多1260个有效观测、至少252个，排除当日；"
        "D变化按有效来源观测计算，缺失日不补值。"
        + ("牛市样本目前仅单轮，低位8段、高位13段，不建议据此认为稳定优于其他模型。" if regime == "bull"
           else "熊市期权样本主要来自2024年，低位10段、高位8段，不能保证新一轮熊市有效。")
        + f"规则指纹{fingerprint[:16]}；报告runtime/reports/csi500_coverage_restudy/report.md。"))
    return data, fingerprint


def unrelated_hash(db, root_id):
    rows = [dict(r) for r in db.execute(text("SELECT * FROM quant_strategy_configs ORDER BY id")).mappings()
            if not (r["owner_user_id"] == root_id and r["name"] in NAMES.values()
                    and r["target_code"] == "sh000905")]
    return sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def verify(report, frame):
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        root_id = db.query(User.id).filter(User.username == "root").one()[0]
        untouched = unrelated_hash(db, root_id)
        service = QuantService(db)
        points = feature_points(db)
        bydate = {p["trade_date"]: p["values"] for p in points}
        for day, row in frame.iterrows():
            for key in PUBLIC_FIELDS:
                actual, expected = bydate.get(day, {}).get(key), row[key]
                assert (actual is None and pd.isna(expected)) or actual is not None and abs(actual - expected) < 1e-7, (day, key, actual, expected)
        for regime in NAMES:
            pair = report["models"]["options_" + regime]["pair"]
            assert pair and pair["backtest"]["original_engine_parity"]
            data, fingerprint = payload(regime, pair)
            service._validate_strategy_payload(data)
            strategy = SimpleNamespace(**data)
            candles, snapshots = service._load_fixed_strategy_target_chart(strategy)
            snapshot_end = frame.index[-1]
            actual = service._build_signal_map(strategy, snapshots)
            red = matches(frame, pair["low"]["rules"])[0]
            blue = matches(frame, pair["high"]["rules"])[0]
            expected = {d: "purple" if r and b else "red" if r else "blue"
                        for d, r, b in zip(frame.index, red, blue) if r or b}
            assert {d: c for d, c in actual.items() if d <= snapshot_end} == expected, regime
            highlights = service._build_strategy_highlight_bands(strategy, snapshots)
            visible = {h["tradeDate"]: h["color"] for h in highlights if h["tradeDate"] <= snapshot_end}
            assert visible == {d: c for d, c in expected.items() if d >= pair["start_date"]}, regime
            prices, colors, pending, initial = service._build_equity_curve_context(strategy)
            curve = service._simulate_equity_curve(filtered_prices=prices, signal_map=colors,
                pending_actions=pending, initial_close=initial, buy_ratio=.5, sell_ratio=1,
                execution_price_mode="next_open", include_signals=True)
            resolved = {d: "blue" if service._resolve_action(c, strategy) == "sell" else "red"
                        for d, c in colors.items() if d >= pair["start_date"] and service._resolve_action(c, strategy)}
            result, detail = replay(service, prices, resolved)
            assert abs(result["return_pct"] - curve["cumulative_return_pct"]) < 1e-7
            assert abs(result["mdd_pct"] - curve["max_drawdown_pct"]) < 1e-7
            pair["application"] = {"fingerprint": fingerprint, "start": str(prices[0]["trade_date"]),
                "end": str(prices[-1]["trade_date"]), "backtest": result,
                "features_filters_highlights_parity": True, "original_engine_parity": True}
            pd.DataFrame(detail["trades"]).to_csv(OUT / f"options_{regime}_installed_trades.csv", index=False)
            save_json(OUT / f"options_{regime}_chart_fixture.json", {
                "candles": [c for c in candles if str(c["trade_date"]) <= snapshot_end],
                "points": [p for p in points if p["trade_date"] <= snapshot_end],
                "params": data["indicator_params"], "rules": {"red": data["red_filter_groups"], "blue": data["blue_filter_groups"]},
                "expected_colors": expected, "start_date": pair["start_date"]})
            print("verified", regime, pair["application"], flush=True)
        assert unrelated_hash(db, root_id) == untouched
        db.rollback()
    return root_id, untouched


def install(report, root_id, untouched):
    frontend = json.loads((OUT / "frontend_verification.json").read_text())
    assert frontend["feature_version"] == VERSION
    assert all(frontend[regime]["all_daily_signals_match"] for regime in NAMES)
    for regime in NAMES:
        fixture = OUT / f"options_{regime}_chart_fixture.json"
        assert frontend[regime]["fixture_sha256"] == sha256(fixture.read_bytes()).hexdigest(), "Frontend proof is stale"
    with SessionLocal() as db:
        db.query(User).filter(User.id == root_id).with_for_update().one()
        assert unrelated_hash(db, root_id) == untouched, "Unrelated strategy changed; stop"
        for regime in NAMES:
            pair = report["models"]["options_" + regime]["pair"]
            data, _ = payload(regime, pair)
            row = db.query(QuantStrategyConfig).filter(QuantStrategyConfig.owner_user_id == root_id,
                QuantStrategyConfig.name == data["name"], QuantStrategyConfig.target_code == "sh000905").with_for_update().one_or_none()
            if row is None:
                row = QuantStrategyConfig(owner_user_id=root_id, **data)
                db.add(row)
            else:
                for key, value in data.items():
                    setattr(row, key, value)
            db.flush()
            pair["strategy_id"] = row.id
            print("saved", row.id, row.name, flush=True)
        assert unrelated_hash(db, root_id) == untouched
        db.commit()
        assert unrelated_hash(db, root_id) == untouched
    report["production_updated"] = True
    report["verification"].update(production_updated=True, frontend_and_filter_parity=True,
        untouched_strategy_sha256=untouched, feature_version=VERSION)


def installation_report(report):
    lines = ["# 中证500覆盖期独立策略上线", "",
        "用户已取消必须从2022起的限制。本次新建两条期权版，旧策略46/47保持原样。",
        "全部可用历史用于优化，不是样本外验证，不保证未来极端命中。", "",
        "| 策略 | ID | 起点 | 回放截止 | 510500收益 | 最大回撤 |", "|---|---:|---|---|---:|---:|"]
    for regime, name in NAMES.items():
        pair = report["models"]["options_" + regime]["pair"]
        app, bt = pair["application"], pair["application"]["backtest"]
        lines.append(f"|{name}|{pair['strategy_id']}|{app['start']}|{app['end']}|{bt['return_pct']:.2f}%|{bt['mdd_pct']:.2f}%|")
    lines += ["", "红买50%、蓝卖100%、卖出优先、次日开盘；不按历史牛熊标签自动开关。",
        "沿用原回测引擎，没有额外加入交易成本、滑点或做空。",
        "两来源ETF期权单独读取；D变化按来源有效观测计算，缺失当天仍为空，不跨来源替代。",
        "价格位置、期权偏斜/期限结构分位、成交额P/C变化、成交量P/C分位已进入量化筛选和牛熊波段因子副图。", "",
        "## 一致性", "",
        "研究冻结快照、生产因子、后端筛选、K线高亮和前端筛选已核对5281个交易日；原交易引擎与独立回放一致。",
        "新记录使用自己的共同可用起点，起点之前不绘制策略信号；其他策略配置哈希保持不变。",
        "正式浏览器检查、测试结果及服务加载状态另记于deployment.json。"]
    (OUT / "installation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    report = json.loads((OUT / "review.json").read_text())
    frame, _ = snapshot()
    root_id, untouched = verify(report, frame)
    if args.install:
        install(report, root_id, untouched)
        installation_report(report)
    save_json(OUT / "review.json", report)


if __name__ == "__main__":
    main()
