"""Post-selection diagnostics only; never selects rules or writes production data."""
import hashlib
import json
import math
from datetime import date

import numpy as np
import pandas as pd

from bear_swing_v2_features import ROOT, save_json
from csi1000_bear_swing import rule_mask, turning_points
from csi1000_bear_swing_v2 import OUT, all_outcomes, describe, signals, stats


def old_signals(f, saved, side):
    groups = json.loads(saved["red_filter_groups" if side == "low" else "blue_filter_groups"])
    assert len(groups) == 1, "Audit supports the current single AND group only"
    conditions = groups[0]["conditions"]
    known = f[[c["field"] for c in conditions]].notna().all(axis=1).to_numpy()
    return rule_mask(f, conditions).to_numpy(), known


def neighborhood(f, mask, known, day, radius=5):
    i = f.index.get_loc(day)
    left, right = max(0, i - radius), min(len(f), i + radius + 1)
    onset = mask & ~np.r_[False, mask[:-1]]
    active_start = None
    if known[i] and mask[i]:
        active_start = i
        while active_start > 0 and mask[active_start - 1]:
            active_start -= 1
    entry_index = active_start + 1 if active_start is not None else None
    entry = f.open.iloc[entry_index] if entry_index is not None and entry_index <= i else None
    return {"date": day, "signal": bool(mask[i]) if known[i] else None,
            "active_episode_start": str(f.index[active_start]) if active_start is not None else None,
            "active_entry_date": str(f.index[entry_index]) if entry is not None else None,
            "entry_to_diagnostic_low_pct": float((f.low.iloc[i] / entry - 1) * 100) if entry is not None else None,
            "hits": list(f.index[left:right][mask[left:right]]),
            "onsets": list(f.index[left:right][onset[left:right]]),
            "missing": list(f.index[left:right][~known[left:right]])}


def mo_strike_coverage(raw):
    """Diagnose K0 coverage with stored contract/interest inputs, not new prices."""
    result = []
    for day in sorted({r["trade_date"] for r in raw["mo_gap"]}):
        dashboard = next(r for r in raw["dashboard"] if r["trade_date"] == day)
        payload = json.loads(dashboard["option_vix_json"])["cffex:MO"]
        for term in ("near_", "next_"):
            month = payload[term + "contract_month"]
            rows = [r for r in raw["mo_gap"] if r["trade_date"] == day and r["contract_month"] == month]
            strikes = {}
            for r in rows:
                prices = [r.get(k) for k in ("close_price", "settle_price", "pre_settle_price")]
                value = next((float(x) for x in prices if x is not None and float(x) > 0), None)
                if value is not None:
                    strikes.setdefault(float(r["strike_price"]), {})[r["option_type"]] = value
            paired = [(k, p["CALL"], p["PUT"]) for k, p in strikes.items() if "CALL" in p and "PUT" in p]
            strike, call, put = min(paired, key=lambda x: abs(x[1] - x[2]))
            expiry = payload[term + "expiry_date"]
            years = (date.fromisoformat(expiry) - date.fromisoformat(day)).days / 365
            forward = strike + math.exp(payload[term + "risk_free_rate"] * years) * (call - put)
            k0 = max((k for k in strikes if k <= forward), default=None)
            result.append({"date": day, "month": month, "raw_rows": len(rows), "forward": forward,
                           "minimum_strike": min(strikes), "k0": k0, "stored_expiry": expiry,
                           "stored_close_vix": payload["vix_close"]})
    return result


def main():
    report = json.loads((OUT / "report.json").read_text())
    raw = json.loads((OUT / "inputs.json").read_text())
    f = pd.read_json(OUT / "features.json", orient="table")
    f.index = f.index.astype(str)
    pivots = turning_points(f)
    outcomes = {side: all_outcomes(f, side) for side in ("low", "high")}
    saved = {r["id"]: r for r in raw["strategies"]}
    comparisons, bottoms, family_rows, ablations = [], [], [], []
    periods = {"2022": ("2022-01-01", "2022-12-31"),
               "2023_to_2024_09": ("2023-01-01", "2024-09-18"),
               "post_2024_09": ("2024-09-19", f.index[-1]),
               "2026": ("2026-01-01", f.index[-1])}
    for model, sid in (("basic", 44), ("enhanced", 45)):
        for side in ("low", "high"):
            candidate = report["models"][model][side]["candidate"]
            if not candidate:
                continue
            new_mask, new_known = signals(f, candidate["spec"])
            old_mask, old_known = old_signals(f, saved[sid], side)
            common_start = max(saved[sid]["start_date"], candidate["first_complete"])
            start_mask = f.index.to_numpy() >= common_start
            for label, mask, known in (("old", old_mask, old_known), ("candidate", new_mask, new_known)):
                for period, (start, end) in periods.items():
                    if end < common_start:
                        continue
                    m = stats(f, mask & start_mask, known, outcomes[side], pivots, side,
                              max(start, common_start), end)
                    comparisons.append({"model": model, "side": side, "rule": label, "period": period, **m})
                if side == "low":
                    for day in ("2022-04-26", "2024-02-05", "2024-09-18"):
                        if day >= common_start:
                            bottoms.append({"model": model, "rule": label,
                                            **neighborhood(f, mask, known, day)})
            extra = candidate["spec"]["extra"]
            if extra:
                without = {**candidate["spec"], "extra": None}
                base_mask, base_known = signals(f, without)
                for phase, (start, end) in {
                    "development": (candidate["train"]["start"], candidate["train"]["end"]),
                    "validation": (candidate["validation"]["start"], candidate["validation"]["end"]),
                    "2026": periods["2026"],
                }.items():
                    for label, mask, known in (("with_filter", new_mask, new_known), ("without_filter", base_mask, base_known)):
                        ablations.append({"model": model, "side": side, "phase": phase,
                                          "rule": label, **stats(f, mask, known, outcomes[side], pivots, side, start, end)})
            for family, r in report["models"][model][side]["family_candidates"].items():
                if r:
                    family_rows.append({"model": model, "side": side, "family": family,
                                        "description": describe(r["spec"]), "accepted": r["accepted"],
                                        "train": r["train"], "validation": r["validation"]})

    audit = {"comparisons": comparisons, "bottoms": bottoms, "ablations": ablations,
             "mo_strike_coverage": mo_strike_coverage(raw),
             "family_comparison": family_rows,
             "total_attempts": sum(x["attempts"] for sides in report["models"].values() for x in sides.values()),
             "accepted": sum(x["accepted_count"] for sides in report["models"].values() for x in sides.values()),
             "code_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in (
                 "scripts/research/csi1000_bear_swing_v2.py", "scripts/research/bear_swing_v2_features.py",
                 "scripts/research/csi1000_bear_swing.py", "backend/app/services/bear_swing_features.py",
                 "scripts/research/audit_bear_swing_v2.py")},
             "notes": ["This is post-selection diagnostics, never a new selection step.",
                 "Same snapshot, prices, dates and next-open execution; input availability remains disclosed per rule.",
                 "Signal windows overlap; event counts are not independent trials or statistical confidence.",
                 "No trading return is inferred from the +5%/-3% first-touch metric; that is an evaluation label, not a stop rule.",
                 "No replacement accepted, so no new strategy/ETF return claim or UI deployment is made."]}
    save_json(OUT / "audit.json", audit)
    pd.DataFrame(comparisons).to_csv(OUT / "old_vs_candidate.csv", index=False)
    pd.DataFrame(ablations).to_csv(OUT / "filter_ablation.csv", index=False)
    pd.DataFrame(bottoms).to_csv(OUT / "bottom_diagnostics.csv", index=False)

    def pc(v):
        return "--" if v is None else f"{v:.1f}%"

    lines = ["# 熊市波段重研结论与旧版对照", "",
        f"数据快照截至 {report['as_of']}。7164组固定候选，0组同时通过开发、验证与邻近参数门槛。",
        "原策略44/45未修改；下面的候选均未达标，不是推荐参数。", "",
        "## 结论", "",
        "1. 旧基础版不是简洁本身有问题，而是把极端超卖当成低点、又用银行流动性硬过滤。它没有证明能可靠区分下跌途中与波段底部。",
        "2. 重建后的核心情绪/融资信息能改善部分区间，但不能稳定解决早买；一日反弹也常发生在下跌途中。",
        "3. 增强版的衍生因子并不自动带来增强；开发期好看的低点候选，在2026年依然明显失败。",
        "4. 不能为补中2024年2月或9月的已知低点而放松阈值，也不能把没有达标的第一名再次发布成正式策略。", "",
        "## 同口径对照", "",
        "所有数值来自同一批指数日线，首次连续信号的下一交易日开盘入场，观察20个交易日；高点只评价向下机会，不是实际做空收益。",
        "各模型两侧使用旧版/候选共同可用起点，区间结束后的收益不纳入。不同规则有效样本数不同，不把这些事件当成独立统计试验。", "",
        "| 模型/方向 | 区间 | 版本 | 有效段数 | 先有利5% | 先不利3% | 20日中位最大逆向 | 极值覆盖 |",
        "|---|---|---|---:|---:|---:|---:|---:|"]
    for r in comparisons:
        title = ("基础" if r["model"] == "basic" else "增强") + ("低点" if r["side"] == "low" else "高点")
        lines.append(f"|{title}|{r['period']}|{'旧版' if r['rule']=='old' else '未达标候选'}|{r['evaluated']}|{pc(r['favorable_first_pct'])}|{pc(r['adverse_first_pct'])}|{pc(r['median_mae20'])}|{pc(r['pivot_coverage_pct'])}|")
    lines += ["", "## 已知底部诊断", "",
        "诊断窗口是前后5个交易日，不用于重选参数。最低点当天收盘确认、再于次日开盘执行，本来就不等同买到盘中最低价。",
        "2024-02-05旧基础版WR=91.48，未达到95；银行紧张度=59.71并未拦截。旧增强版WR达标，但MO收盘隐波缺失。",
        "2024-09-18旧基础版WR=83.68、银行紧张度=74.21，两项均未满足。9月13日WR已到95.72，但银行紧张度78.42仍将信号过滤掉。", "",
        "| 模型 | 规则 | 诊断日期 | 当日命中 | 当前信号区起点 | 起点次日开盘至该日最低价 | 窗口内首次信号 | 窗口内缺失日 |",
        "|---|---|---|---|---|---|---|---|"]
    for r in bottoms:
        lines.append(f"|{r['model']}|{r['rule']}|{r['date']}|{r['signal']}|{r['active_episode_start'] or '--'}|{pc(r['entry_to_diagnostic_low_pct'])}|{', '.join(r['onsets']) or '--'}|{', '.join(r['missing']) or '--'}|")
    lines += ["", "## MO缺失不是没有原始行情", "",
        "只读复算确认：2024-02-05 MO2402/MO2403分别有76/82行原始期权行情；近月收盘期限隐波可算为46.6008。",
        "但次月由看涨看跌平价计算的远期水平约4054.09，低于原始链中最低执行价4100，无法找到K0，次月方差返回空。30日期限插值因此不可得。",
        "2024-01-22也存在同类问题：次月远期4748.19低于最低执行价4750。不能用前日值、开盘隐波或自行补合约冒充收盘隐波。",
        "这两个日期的分析使用现有计算器和保存的利率参数，是定位缺值原因，不代表已经对期权到期日/执行价历史做完整审计；原始数据和看板未改动。", "",
        "## 研究边界与下一步", "",
        "- 本轮含阶段位置、重建核心情绪、滞后一交易日的沪深融资30D、资金变化、银行流动性与海外波动率；增强候选加入IM、MO和中信净空。每侧最多三项规则。",
        "- 估值/汇率缺逐日可核验发布时间，完整风险分未完成底层时点审计；宏观月度严格可重放时间最早2026-09-20。它们没有被假装成已验证的历史信号。",
        "- 这轮没有证据支持把新参数替换进正式策略。两条现有策略仅能作为未达标研究模板，不应因名称而被认作可用熊市系统。",
        "- 历史库并非每个时点真实留存的完整原始版本；当前结果是按可核验发布时间作因果重放，不能宣传为历史实盘或完全无修订偏差。",
        "- 后续值得研究的是将低位观察区与可执行反转触发分开，并事先规定失效和退出，尤其区分恐慌急跌与缓慢阴跌；本轮只测试了固定5日位置记忆加确认，尚未证明完整两阶段系统有效。",
        "- 如果继续扩大模型族，应另立协议、完整保留本轮失败结果，以之后的新数据做前瞻观察，不再把2022/2024当未看过的测试集。", "",
        "## 可复核文件", "",
        "- protocol.json：试验前冻结的范围、门槛与截止时点。",
        "- report.md / report.json：分训练、验证和年度评价。",
        "- attempts.json：全部7164组试验，包括未达标原因。",
        "- old_vs_candidate.csv / filter_ablation.csv：旧新对照与去掉额外过滤的对照。",
        "- basic/enhanced_low/high_events.csv：逐次信号与5/10/20/60日结果。",
        "- basic/enhanced_low/high_daily.csv：逐日原值、信号和决策日。",
        "- inputs.json / features.json / coverage.json / audit.json：原始快照、特征、覆盖、数据和代码指纹。", ""]
    (OUT / "conclusions.md").write_text("\n".join(lines), encoding="utf-8")
    print(OUT / "conclusions.md")


if __name__ == "__main__":
    main()
