"""Pair existing trials with sell precedence; produce the final evaluation."""
from copy import deepcopy
import json

import numpy as np
import pandas as pd

from csi500_swing import OUT, POLICY, Search, episodes, matches, rule_id, save_json, snapshot, turning_points
from app.services.csi500_swing_features import cycle_labels


def array_items(path):
    decoder = json.JSONDecoder()
    with path.open(encoding="utf-8") as stream:
        buffer = ""
        started = False
        eof = False
        while True:
            buffer = buffer.lstrip()
            if not started and buffer.startswith("["):
                buffer, started = buffer[1:], True
                continue
            if started and buffer.startswith(","):
                buffer = buffer[1:]
                continue
            if started and buffer.startswith("]"):
                return
            if started and buffer:
                try:
                    item, end = decoder.raw_decode(buffer)
                except json.JSONDecodeError:
                    if eof:
                        raise
                else:
                    yield item
                    buffer = buffer[end:]
                    continue
            if eof:
                raise ValueError("Truncated candidate array")
            chunk = stream.read(1 << 20)
            eof = not chunk
            buffer += chunk


def audit():
    report = json.loads((OUT / "report.json").read_text())
    assert report["policy"]["version"] == POLICY["version"]
    f, catalog = snapshot()
    labels, cycles = cycle_labels(f.index)
    pivots = turning_points(f)
    for regime, model in report["models"].items():
        blue, bk = matches(f, model["high"]["rules"])
        search = Search(f, catalog, regime, "low", [])
        targets = [r["index"] for r in model["extreme_coverage"] if r["side"] == "low"]
        qualified = [t for t in array_items(OUT / f"{regime}_low_attempts.json") if not t["rejected"]]
        early = [t for t in qualified if all((catalog[c["field"]]["first_available_date"] or "9999") <= "2022-01-01"
                 for g in t["rules"] for c in g["conditions"] if catalog[c["field"]]["transform"] != "availability")]
        base = sorted(early, key=lambda t: (-t["metrics"]["score"], sum(len(g["conditions"]) for g in t["rules"]), t["id"]))[0]
        base_mask, base_known = matches(f, base["rules"])
        pairs = []
        for trial in qualified:
            red, rk = matches(f, trial["rules"])
            effective = red & ~blue
            if not all(effective[i] for i in targets):
                continue
            trial = deepcopy(trial)
            trial["paired_metrics"] = search.metrics(effective, search.inside & rk & bk)
            fields = {c["field"] for g in trial["rules"] for c in g["conditions"]}
            late = {k for k in fields if catalog[k]["transform"] != "availability"
                    and (catalog[k]["first_available_date"] or "9999") > "2022-01-01"}
            if late:
                common = search.inside & rk & bk & base_known
                for key in late:
                    common &= f[key].notna().to_numpy()
                old, new = search.metrics(base_mask & ~blue, common), search.metrics(effective, common)
                trial["paired_common_window"] = {"days": int(common.sum()), "baseline": old, "candidate": new,
                                                 "delta_score": new["score"] - old["score"]}
                if new["score"] <= old["score"]:
                    continue
            pairs.append(trial)
        chosen = sorted(pairs, key=lambda t: (-t["paired_metrics"]["score"], sum(len(g["conditions"]) for g in t["rules"]), t["id"]))[0]
        model["low"] = chosen
        red, rk = matches(f, chosen["rules"])
        masks = {"low": red & ~blue, "high": blue}
        formal = (labels == regime) & (f.index >= "2022-01-01")
        model["effective_formal_color_pct"] = {"red": float(masks["low"][formal].mean()) * 100,
                                                "blue": float(blue[formal].mean()) * 100}
        assert max(model["effective_formal_color_pct"].values()) <= 35
        assert all(masks[r["side"]][r["index"]] for r in model["extreme_coverage"])
        model["effective_metrics"] = {side: Search(f, catalog, regime, side, []).metrics(mask, (labels == regime) & rk & bk)
                                       for side, mask in masks.items()}
        model["paired_selection"] = {"qualified_red_candidates": len(qualified), "compatible_pairs": len(pairs),
                                      "sell_first_ranked": True}
        model["annual"], model["cycle_evaluation"] = {}, []
        for year in sorted({d[:4] for d in f.index}):
            inside = (labels == regime) & (f.index.str.startswith(year)) & rk & bk
            model["annual"][year] = {side: Search(f, catalog, regime, side, []).metrics(mask, inside) for side, mask in masks.items()}
        for i, (start, kind) in enumerate(cycles):
            if kind != regime:
                continue
            end = cycles[i + 1][0] if i + 1 < len(cycles) else "9999"
            inside = (f.index >= start) & (f.index < end) & rk & bk
            model["cycle_evaluation"].append({"start": start, "end_exclusive": end,
                **{side: Search(f, catalog, regime, side, []).metrics(mask, inside) for side, mask in masks.items()}})
        distances = []
        for side, mask in masks.items():
            ev = episodes(f, pd.Series(mask, index=f.index), side)
            for event in ev:
                for name in event:
                    if name.startswith(("mae_", "mfe_")) and event[name] is not None:
                        event[name] = max(0.0, event[name])
                event["cycle"] = labels[event["index"]]
                event["applicable_environment"] = event["cycle"] == regime
            pd.DataFrame(ev).to_csv(OUT / f"{regime}_{side}_events.csv", index=False)
            model.setdefault("ordinary_pivot_coverage", {})[side] = {
                "count": int(sum(p["side"] == side and labels[p["index"]] == regime and f.index[p["index"]] >= "2022-01-01" for p in pivots)),
                "exact_hits": int(sum(p["side"] == side and labels[p["index"]] == regime and f.index[p["index"]] >= "2022-01-01" and mask[p["index"]] for p in pivots))}
            for extreme in model["extreme_coverage"]:
                if extreme["side"] != side:
                    continue
                index = extreme["index"]
                first = index
                while first and mask[first - 1]:
                    first -= 1
                distances.append({**extreme, "first_signal_date": f.index[first], "lead_sessions": index - first,
                                  "signal_close": float(f.close.iloc[first]),
                                  "price_distance_pct": abs(float(f.close.iloc[first]) / extreme["price"] - 1) * 100})
        model["extreme_distance"] = distances
        model["config_fingerprint"] = rule_id({s: model[s]["rules"] for s in masks})
        daily = f[["open", "high", "low", "close"]].copy()
        daily["cycle"], daily["red"], daily["blue"], daily["known"] = labels, red, blue, rk & bk
        daily["as_of_at"] = daily.index + "T22:30:00+08:00"
        daily.to_csv(OUT / f"{regime}_daily.csv", index_label="date")
    report["selected_fields"] = sorted({c["field"] for m in report["models"].values() for side in ("low", "high")
                                         for g in m[side]["rules"] for c in g["conditions"]})
    report["production_updated"] = False
    save_json(OUT / "report.json", report)
    for key, meta in catalog.items():
        if key in report["selected_fields"]:
            meta.update(research_status="selected", selection_reason="Sell-first paired ranking")
        elif meta.get("research_status") == "selected":
            meta.update(research_status="scanned", selection_reason="Not selected after sell-first pairing")
    save_json(OUT / "catalog.json", catalog)
    lines = ["\n## 卖出优先后的最终规则与局限", "", "以下最终规则及实际颜色统计优先于前面的单方向初筛结果。", "",
             "| 环境 | 红色占比(2022起) | 蓝色占比(2022起) | 低位区域 | 高位区域 |", "|---|---:|---:|---:|---:|"]
    for regime, m in report["models"].items():
        pct = m["effective_formal_color_pct"]
        lines.append(f"|{regime}|{pct['red']:.2f}%|{pct['blue']:.2f}%|{m['effective_metrics']['low']['events']}|{m['effective_metrics']['high']['events']}|")
        lines.extend(["", regime + "红色：`" + json.dumps(m["low"]["rules"], ensure_ascii=False) + "`",
                      regime + "蓝色：`" + json.dumps(m["high"]["rules"], ensure_ascii=False) + "`",
                      "普通5%波段覆盖：" + json.dumps(m["ordinary_pivot_coverage"], ensure_ascii=False)])
    lines += ["", "熊市高位合格规则只有少量历史区域，当前严格极端标签没有熊市高位样本，不能称为‘熊市高点100%覆盖’。",
              "牛市低位也只有少量区域。大量候选上的历史优化有显著选择偏差，分数高不代表实盘稳定，暂不建议自动执行。",
              "各周期和年度结果、提前交易日及价格距离见report.json；失败事件及完整5/10/20/60日结果见各events.csv。"]
    path = OUT / "report.md"
    path.write_text(path.read_text().split("\n## 卖出优先后的最终")[0] + "\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: {"red": m["low"]["rules"], "blue": m["high"]["rules"], "colors": m["effective_formal_color_pct"]}
                      for k, m in report["models"].items()}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    audit()
