"""Offline, buy-only regime gate research. No application or database writes."""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Rule:
    name: str
    medium: int = 60
    long: int = 120
    pause_breadth: float = 40
    invalid_breadth: float = 30
    recover_breadth: float = 50
    pause_days: int = 3
    invalid_days: int = 10
    recover_days: int = 5
    slow_only: bool = False


# Frozen before inspecting results; adjacent variants are sensitivity checks, not a search.
RULES = [Rule("slow", slow_only=True), Rule("balanced"),
         Rule("faster", medium=40), Rule("slower", medium=80)]


def stock_breadth_parts(frame, calendar):
    """Aggregate observed stocks without filling gaps; provenance belongs to the export manifest."""
    totals = pd.DataFrame(0, index=calendar, columns=["observed", "traded"] +
                          [f"{kind}{w}" for w in (40, 60, 80, 120)
                           for kind in ("valid", "above")])
    for _, group in frame.groupby("prefixed_code", sort=False):
        group = group.set_index("trade_date").reindex(calendar)
        close = pd.to_numeric(group.close_price, errors="coerce")
        volume = pd.to_numeric(group.volume, errors="coerce")
        close = close.where(close > 0)
        totals["observed"] += close.notna().astype(int)
        traded = close.notna() & volume.gt(0)
        totals["traded"] += traded.astype(int)
        for w in (40, 60, 80, 120):
            ma = close.rolling(w, min_periods=w).mean()
            valid = ma.notna() & traded
            totals[f"valid{w}"] += valid.astype(int)
            totals[f"above{w}"] += (valid & close.gt(ma)).astype(int)
    return totals


def regime_points(prices, breadth, rule):
    rows = prices.set_index("date").join(breadth).copy()
    rows["medium_ma"] = rows.close.rolling(rule.medium).mean()
    rows["long_ma"] = rows.close.rolling(rule.long).mean()
    rows["long_slope"] = rows.long_ma / rows.long_ma.shift(20) - 1
    rows["medium_breadth"] = rows[f"breadth{rule.medium}"]
    rows["long_breadth"] = rows[f"breadth{rule.long}"]
    state = "unavailable"
    pause_streak = invalid_streak = recover_streak = full_streak = 0
    out = []
    for day, row in rows.iterrows():
        required = [row.close, row.medium_ma, row.long_ma, row.long_slope,
                    row.medium_breadth, row.long_breadth]
        # Coverage denominator is today's observed traded stocks, not today's survivor list.
        sufficient = (row.get("traded", 0) >= 500 and
                      row.get(f"valid{rule.long}", 0) >= row.get("traded", 0) * .60)
        available = all(pd.notna(v) and np.isfinite(v) for v in required) and sufficient
        record = {"date": str(day), "close": row.close, "medium_ma": row.medium_ma,
                  "long_ma": row.long_ma, "long_slope": row.long_slope,
                  "breadth_medium": row.medium_breadth, "breadth_long": row.long_breadth,
                  "observed": row.get("observed"), "traded": row.get("traded"),
                  "eligible": row.get(f"valid{rule.long}")}
        if not available:
            pause_streak = invalid_streak = recover_streak = full_streak = 0
            out.append({**record, "state": "unavailable", "buy_multiplier": 0.0,
                        "reason": "warmup_or_coverage_gap"})
            continue
        pause = row.close < row.medium_ma and row.medium_breadth < rule.pause_breadth
        invalid = (row.close < row.long_ma and row.long_slope < 0 and
                   row.long_breadth < rule.invalid_breadth)
        recover = row.close > row.medium_ma and row.medium_breadth >= rule.recover_breadth
        full = (recover and row.close > row.long_ma and row.long_slope >= 0 and
                row.long_breadth >= rule.recover_breadth)
        pause_streak = pause_streak + 1 if pause else 0
        invalid_streak = invalid_streak + 1 if invalid else 0
        recover_streak = recover_streak + 1 if recover else 0
        full_streak = full_streak + 1 if full else 0
        if state == "unavailable":
            state = "repair"
        if invalid_streak >= rule.invalid_days:
            state = "invalid"
        elif not rule.slow_only and state != "invalid" and pause_streak >= rule.pause_days:
            state = "paused"
        elif full_streak >= rule.recover_days:
            state = "valid"
        elif state in ("paused", "invalid") and recover_streak >= rule.recover_days:
            state = "repair"
        multiplier = {"valid": 1.0, "repair": .5, "paused": 0.0, "invalid": 0.0}[state]
        out.append({**record, "state": state, "buy_multiplier": multiplier,
                    "reason": state, "pause_streak": pause_streak,
                    "invalid_streak": invalid_streak, "recover_streak": recover_streak})
    return out


def evaluate_signals(prices, signals, gate=None, buy=.5, sell=.5, cost=0.0):
    """Gate signal day's NEW orders; execute next observed trading day open, never force exit."""
    cash, shares, peak = 1.0, 0.0, 1.0
    pending = None
    trades, points, blocked = [], [], []
    for row in prices:
        d, op, cl = row["date"], float(row["open"]), float(row["close"])
        if pending and op > 0:
            side, signal_day, fraction = pending
            nav = cash + shares * op
            quantity = 0.0
            if side == "buy":
                budget = min(cash / (1 + cost), nav * buy * fraction)
                quantity = budget / op
                cash -= budget * (1 + cost)
                shares += quantity
            elif side == "sell":
                quantity = min(shares, nav * sell / op)
                shares -= quantity
                cash += quantity * op * (1 - cost)
            if quantity > 1e-9:
                trades.append({"date": d, "signal_date": signal_day, "side": side,
                               "price": op, "quantity": quantity, "multiplier": fraction})
        pending = None
        nav = cash + shares * cl
        peak = max(peak, nav)
        points.append({"date": d, "nav": nav, "drawdown_pct": (nav / peak - 1) * 100,
                       "position_pct": shares * cl / nav * 100})
        color = signals.get(d)
        if color in ("blue", "purple"):
            pending = ("sell", d, 1)
        elif color == "red":
            multiplier = gate.get(d, 0.0) if gate is not None else 1.0
            if multiplier > 0:
                pending = ("buy", d, multiplier)
            if multiplier < 1:
                blocked.append({"signal_date": d, "multiplier": multiplier,
                                "has_cash": cash > 1e-9})
    return {"return_pct": (nav - 1) * 100,
            "mdd_pct": -min(p["drawdown_pct"] for p in points),
            "mean_position_pct": float(np.mean([p["position_pct"] for p in points])),
            "final_position_pct": points[-1]["position_pct"],
            "trades": trades, "points": points, "restricted_signals": blocked}


def episodes(points, prices):
    price_map = {r["date"]: i for i, r in enumerate(prices)}
    events, current = [], None
    for p in points:
        blocked = p["state"] in ("paused", "invalid")
        if blocked and current is None:
            current = {"start": p["date"], "end": p["date"], "days": 0,
                       "states": [], "closed": False, "end_reason": None}
        if current and blocked:
            current["end"] = p["date"]
            current["days"] += 1
            if p["state"] not in current["states"]:
                current["states"].append(p["state"])
        elif current:
            current["closed"] = p["state"] != "unavailable"
            current["end_reason"] = p["state"]
            events.append(current)
            current = None
    if current:
        events.append(current)
    for e in events:
        i = price_map[e["start"]]
        close = prices[i]["close"]
        for w in (5, 10, 20, 60):
            future = prices[i + 1:i + w + 1]
            e[f"drawdown_{w}d_pct"] = ((min(r["low"] for r in future) / close - 1) * 100
                                          if len(future) == w else None)
            e[f"upside_{w}d_pct"] = ((max(r["high"] for r in future) / close - 1) * 100
                                        if len(future) == w else None)
    return events


def rule_manifest():
    return [asdict(r) for r in RULES]
