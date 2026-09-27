from datetime import date, datetime
import json
import math
from pathlib import Path

from app.schemas.market_regime import MarketRegimeResponse, RegimeIndex
from app.services.market_regime_research import read_snapshot
from app.services.market_regime_model import cycle_points, MODEL_VERSION, RULES

REPORT_PATH = Path(__file__).resolve().parents[3] / "runtime/reports/market_regime/report.json"


def _proxy_points(snapshot: dict | None, index_code: RegimeIndex,
                  after: date = date.min, seed=None) -> list[dict]:
    """Run one chronological index-only model, including the historical warmup."""
    if not snapshot:
        return []
    state = seed.state if seed else "unavailable"
    streaks = {
        key: (getattr(seed, f"{key}_streak", 0) or 0)
        for key in ("pause", "invalid", "recover", "full")
    }
    result = []
    for source in snapshot.get("daily_points") or []:
        day = date.fromisoformat(str(source["date"]))
        if day <= after:
            continue
        trend = source if index_code == "sh000985" else (source.get("adaptation") or {}).get(index_code)
        if not trend or not isinstance(trend.get("close"), (int, float)):
            continue
        medium_breadth = source.get("index_participation_ma60_pct")
        long_breadth = source.get("index_participation_ma120_pct")
        required = [
            (trend or {}).get("close"), (trend or {}).get("ma60"),
            (trend or {}).get("ma120"), (trend or {}).get("ma120_change_20d_pct"),
            medium_breadth, long_breadth,
        ]
        available = not source.get("missing_reasons") and all(
            isinstance(value, (int, float)) and math.isfinite(value) for value in required
        )
        if not available:
            streaks = {key: 0 for key in streaks}
            result.append({
                "date": day, "open": (trend or {}).get("open"), "high": (trend or {}).get("high"),
                "low": (trend or {}).get("low"), "close": (trend or {}).get("close"),
                "medium_ma": (trend or {}).get("ma60"), "long_ma": (trend or {}).get("ma120"),
                "long_slope": None, "breadth_medium": medium_breadth, "breadth_long": long_breadth,
                "observed": None, "traded": None, "eligible": None, "coverage_pct": None,
                "state": "unavailable", "buy_multiplier": 0.0, "reason": "index_proxy_incomplete",
                "missing_reasons": ["index_history_incomplete"], "evidence_mode": "index_proxy",
                **{f"{key}_streak": 0 for key in streaks},
                **{f"{key}_met": None for key in streaks},
            })
            continue
        close, medium_ma, long_ma, slope_pct, medium_breadth, long_breadth = map(float, required)
        slope = slope_pct / 100
        pause = close < medium_ma and medium_breadth < 40
        invalid = close < long_ma and slope < 0 and long_breadth < 30
        recover = close > medium_ma and medium_breadth >= 50
        full = recover and close > long_ma and slope >= 0 and long_breadth >= 50
        conditions = {"pause": pause, "invalid": invalid, "recover": recover, "full": full}
        for key, met in conditions.items():
            streaks[key] = streaks[key] + 1 if met else 0
        if state == "unavailable":
            state = "repair"
        if streaks["invalid"] >= 10:
            state = "invalid"
        elif state != "invalid" and streaks["pause"] >= 3:
            state = "paused"
        elif streaks["full"] >= 5:
            state = "valid"
        elif state in ("paused", "invalid") and streaks["recover"] >= 5:
            state = "repair"
        result.append({
            "date": day, "open": trend.get("open"), "high": trend.get("high"),
            "low": trend.get("low"), "close": close, "medium_ma": medium_ma,
            "long_ma": long_ma, "long_slope": slope, "breadth_medium": medium_breadth,
            "breadth_long": long_breadth, "observed": 3, "traded": 3, "eligible": 3,
            "coverage_pct": 100, "state": state,
            "buy_multiplier": {"valid": 1.0, "repair": .5, "paused": 0.0, "invalid": 0.0}[state],
            "reason": f"index_proxy_{state}", "missing_reasons": [], "evidence_mode": "index_proxy",
            **{f"{key}_streak": streaks[key] for key in streaks},
            **{f"{key}_met": conditions[key] for key in streaks},
        })
    return result


def _events(points: list[dict]) -> list[dict]:
    merged, active = [], None
    for point in points:
        risk = point["state"] in {"paused", "invalid", "warning"}
        if active and risk:
            active["end"] = point["date"]
            active["days"] += 1
            if point["state"] not in active["states"]:
                active["states"].append(point["state"])
        elif active:
            active["closed"] = point["state"] != "unavailable"
            active["end_reason"] = point["state"]
            active["resumed_date"] = point["date"] if active["closed"] else None
            active = None
        elif not active and risk:
            active = {"start": point["date"], "end": point["date"], "days": 1,
                      "closed": False, "end_reason": None, "resumed_date": None,
                      "states": [point["state"]]}
            merged.append(active)
    positions = {p["date"]: i for i, p in enumerate(points)}
    for event in merged:
        i = positions[event["start"]]
        for window in (5, 10, 20, 60):
            future = points[i + 1:i + 1 + window]
            complete = len(future) == window and all(
                isinstance(p.get(key), (int, float)) and math.isfinite(p[key]) and p[key] > 0
                for p in future for key in ("high", "low"))
            event[f"drawdown_{window}d_pct"] = (
                (min(p["low"] for p in future) / points[i]["close"] - 1) * 100 if complete else None)
            event[f"upside_{window}d_pct"] = (
                (max(p["high"] for p in future) / points[i]["close"] - 1) * 100 if complete else None)
    return merged


def _gaps(points):
    gaps, active = [], None
    for point in points:
        if point["state"] != "unavailable":
            active = None
            continue
        if active is None:
            active = {"start": point["date"], "end": point["date"], "days": 0,
                      "reasons": ["index_history_incomplete"]}
            gaps.append(active)
        active["end"] = point["date"]
        active["days"] += 1
    return gaps


def get_market_regime(
    index_code: RegimeIndex = "sh000852", start_date: date | None = None, end_date: date | None = None,
) -> MarketRegimeResponse:
    if index_code not in ("sh000852", "sh000985", "sh000300"):
        raise ValueError("不支持的观察指数")
    if start_date and end_date and start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    snapshot = read_snapshot()
    if not snapshot or not snapshot.get("daily_points"):
        raise RuntimeError("市场环境指数日更快照尚未生成，请执行市场环境轻量更新；不回退到旧逐股广度")
    if "macro_regime_timeline" not in snapshot:
        raise RuntimeError("新环境模型快照尚未生成，请执行市场环境轻量更新")
    merged_points = cycle_points(snapshot, index_code)
    for point in merged_points:
        point["date"] = date.fromisoformat(point["date"])
    days = [p["date"] for p in merged_points]
    if not days or days != sorted(set(days)):
        raise RuntimeError("指数日更快照缺少所选指数或日期顺序异常，请重新生成")
    points = [point for point in merged_points
              if (start_date is None or point["date"] >= start_date)
              and (end_date is None or point["date"] <= end_date)]
    all_events = _events(merged_points)
    events = [event for event in all_events
              if points and event["end"] >= points[0]["date"] and event["start"] <= points[-1]["date"]]
    daily_as_of = merged_points[-1]["date"] if merged_points else None
    generated_at = datetime.fromisoformat(str(snapshot["generated_at"]))
    sources = [{"table": "index_daily_data", "start": merged_points[0]["date"],
                "end": merged_points[-1]["date"], "note": "全历史与日更均使用4条宽基指数，不读取逐股广度。"}] if merged_points else []
    notes = ["全历史统一使用现有日更指数：中证全指、沪深300、中证500、中证1000。",
             "参与度是三条宽基指数位于均线上方的比例，仅有0%、33.3%、66.7%、100%四档，不代表个股广度。",
             "新版区分牛市、牛市内调整、转弱观察、熊市和修复；短期跌破MA60不再直接暂停低吸。",
             "货币信用、景气、盈利三组按已公布月份确认结构转弱或修复；不任意拼接总分。",
             "宏观严格版本留存前仅提供指数基线，明确标记宏观未核验；不能宣称全历史宏观模型验证通过。",
             "宏观数据按实际可用时间展示，不将月度数据插值，也不将归档修订数据冒充当时已知值。"]
    research = {key: value for key, value in snapshot.items() if key not in ("daily_points", "latest")}
    comparison_path = REPORT_PATH.with_name("strategy_comparison.json")
    comparison = None
    if comparison_path.exists():
        try:
            comparison = json.loads(comparison_path.read_text())
        except (OSError, ValueError):
            pass
    return MarketRegimeResponse(
        schema_version="market-regime-cycle-v1", generated_at=generated_at,
        rule_name=MODEL_VERSION, model_rules=RULES, index_code=index_code,
        index_name={"sh000985": "中证全指", "sh000300": "沪深300", "sh000852": "中证1000"}[index_code],
        breadth_as_of=daily_as_of, daily_as_of=daily_as_of,
        daily_update_mode="index_proxy", notes=notes,
        strategy_evaluation_end=comparison.get("end_date") if comparison else None, breadth_sources=sources,
        history_start=merged_points[0]["date"] if merged_points else None,
        history_end=merged_points[-1]["date"] if merged_points else None,
        latest=points[-1] if points else None, points=points, events=events,
        coverage_gaps=[gap for gap in _gaps(merged_points)
                       if points and gap["end"] >= points[0]["date"] and gap["start"] <= points[-1]["date"]],
        lightweight_research=research if end_date is None or end_date >= daily_as_of else None,
        strategy_comparison=comparison,
    )
