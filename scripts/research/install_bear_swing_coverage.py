"""Verify and atomically update only existing bear-strategy red rules/notes."""
import argparse
import copy
import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
from sqlalchemy import select

from bear_swing_coverage import OUT, markdown, matches, title
from bear_swing_v2_features import save_json
from finalize_bear_swing import replay
from app.db.session import SessionLocal
from app.models.quant_strategy_config import QuantStrategyConfig
from app.models.user import User
from app.services.quant_service import QuantService


def item_dict(item):
    return {c.name: copy.deepcopy(getattr(item, c.name)) for c in item.__table__.columns}


def digest(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()


def desired_notes(model):
    return (f"历史极端低点覆盖优先研究版（2026-09-29）。红色：{title(model['rule'])}。"
            f"固定历史标签覆盖{model['coverage']}/{model['targets']}，允许提前，未来覆盖不保证。"
            "极端标签仅作事后评估，不用于实时信号。蓝色条件不变；红买50%、蓝卖100%、次日开盘、冲突卖出优先。"
            "提前信号仍可能遭遇显著回撤；本轮按已知历史覆盖选型，不是独立样本外结果。"
            "详见runtime/reports/csi1000_bear_swing_coverage/report.md。")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = json.loads((OUT/"report.json").read_text())
    f = pd.read_json(OUT/"features.json", orient="table")
    f.index = f.index.astype(str)
    with SessionLocal() as db:
        service = QuantService(db)
        before = {s.id: item_dict(s) for s in db.scalars(select(QuantStrategyConfig)).all()}
        root = db.scalar(select(User).where(User.username == "root"))
        assert root is not None
        verification = {}
        for name, model in report["models"].items():
            old = before[model["strategy_id"]]
            assert old["owner_user_id"] == root.id and old["target_code"] == "sh000852"
            assert old["name"] == "中证1000熊市波段-" + ("基础版" if name == "basic" else "增强版")
            assert old["red_filter_groups"] in (model["old_rule"], model["rule"]), "Strategy changed since snapshot"
            assert old["blue_filter_groups"] == model["blue_rule"]
            assert float(old["buy_position_pct"]) == .5 and float(old["sell_position_pct"]) == 1
            assert old["execution_price_mode"] == "next_open" and old["purple_conflict_mode"] == "sell_first"
            data = {**old, "red_filter_groups": model["rule"], "notes": desired_notes(model)}
            service._validate_strategy_payload(data)
            strategy = SimpleNamespace(**data)
            # The chart loader selects feature families based on used rules.
            # Load the union so the old bank/IV inputs do not disappear when a
            # new price-only candidate is compared against the original rule.
            loader = SimpleNamespace(**{**data, "red_filter_groups": model["rule"] + model["old_rule"]})
            _, snapshots = service._load_fixed_strategy_target_chart(loader)
            snapshots = [s for s in snapshots if s["trade_date"] <= report["as_of"]]
            actual = service._build_signal_map(strategy, snapshots)
            red, _ = matches(f, model["rule"])
            blue, _ = matches(f, model["blue_rule"])
            expected = {d: "purple" if r and b else "red" if r else "blue"
                        for d, r, b in zip(f.index, red, blue) if r or b}
            assert actual == expected, (name, "backend parity", list(set(actual.items()) ^ set(expected.items()))[:10])
            bands = service._build_strategy_highlight_bands(strategy, snapshots)
            assert {b["tradeDate"]: b["color"] for b in bands} == {d: c for d, c in expected.items() if d >= model["start_date"]}
            assert all(actual.get(row["date"]) == "red" for row in model["bottoms"])
            backtests = {}
            for version, rules in (("old", model["old_rule"]), ("new", model["rule"])):
                s = SimpleNamespace(**{**old, "red_filter_groups": rules})
                low, _ = matches(f, rules)
                expected_version = {d: "purple" if r and b else "red" if r else "blue"
                                    for d, r, b in zip(f.index, low, blue) if r or b}
                assert service._build_signal_map(s, snapshots) == expected_version, (name, version, "comparison input parity")
                for period, start in (("full", model["start_date"]), ("2026", "2026-01-01")):
                    result = replay(service, s, snapshots, start, report["as_of"])
                    backtests[f"{version}_{period}"] = {k: v for k, v in result.items() if k not in ("points", "trades")}
                    pd.DataFrame(result["trades"]).to_csv(OUT/f"{name}_{version}_{period}_trades.csv", index=False)
            model["backtests"] = backtests
            verification[name] = {"signal_dates": len(actual), "extreme_red_dates": len(model["bottoms"]),
                                  "backend_filter_parity": True, "highlight_parity": True, "engine_parity": True}
            print(name, backtests, flush=True)

        # End the long read-only transaction before short, row-locked updates.
        db.rollback()
        if args.apply:
            targets = db.scalars(select(QuantStrategyConfig).where(QuantStrategyConfig.id.in_([44, 45])).with_for_update().execution_options(populate_existing=True)).all()
            assert len(targets) == 2
            for item in targets:
                assert digest(item_dict(item)) == digest(before[item.id]), "Concurrent change: abort without overwriting"
            backup = OUT/"before_update.json"
            if not backup.exists():
                save_json(backup, {str(i): before[i] for i in (44, 45)})
            byid = {r.id: r for r in targets}
            for model in report["models"].values():
                item = byid[model["strategy_id"]]
                item.red_filter_groups = model["rule"]
                item.notes = desired_notes(model)
            db.flush()
            for item in targets:
                unchanged = set(before[item.id]) - {"red_filter_groups", "notes", "updated_at"}
                assert all(getattr(item, k) == before[item.id][k] for k in unchanged)
            db.commit()
            after = {s.id: item_dict(s) for s in db.scalars(select(QuantStrategyConfig).execution_options(populate_existing=True)).all()}
            assert set(before) == set(after), "Strategy count changed"
            assert all(before[i] == after[i] for i in before if i not in (44, 45)), "An unrelated strategy changed"
            for model in report["models"].values():
                assert after[model["strategy_id"]]["red_filter_groups"] == model["rule"]
            save_json(OUT/"after_update.json", {str(i): after[i] for i in (44,45)})
            report["production_updated"] = True
            verification["unrelated_strategies_unchanged"] = True
            verification["no_new_strategy"] = True
        report["verification"] = verification
    save_json(OUT/"report.json", report)
    markdown(report)
    lines = ["\n## ETF交易回测与生效核验", "",
             "512100，沿用现有引擎50%买入/100%卖出、次日开盘、同日卖出优先；未计手续费与滑点。独立重放与现有引擎收益和回撤一致。",
             "下列回撤是完整账户曲线回撤；前文首次信号到极端低点的跌幅不是同一指标。", "",
             "| 策略 | 版本/区间 | 累计收益 | 最大回撤 |", "|---|---|---:|---:|"]
    for name, model in report["models"].items():
        for period, result in model["backtests"].items():
            lines.append(f"|{name}|{period}|{result['return_pct']:.2f}%|{result['mdd_pct']:.2f}%|")
    lines += ["", f"已更新现有策略：{report['production_updated']}；后端逐日筛选、红蓝高亮及回测一致性验证通过。",
              "更新后updated_at参与现有策略图表缓存键，无需全局清缓存或重启服务。", ""]
    with (OUT/"report.md").open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


if __name__ == "__main__":
    main()
