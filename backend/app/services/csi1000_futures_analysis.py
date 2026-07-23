from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session


INDEX_CODE = "sh000852"
INDEX_NAME = "中证1000"
ZIGZAG_THRESHOLD = 0.20
CONTRACT_MULTIPLIER = 200.0
FEE_RATE = 0.000023
IM_SYMBOL_RE = re.compile(r"^IM(?P<year>\d{2})(?P<month>\d{2})$")


def finite_number(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def date_text(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")[:10]


def parse_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(date_text(value))


def contract_month(symbol: str) -> tuple[int, int] | None:
    match = IM_SYMBOL_RE.fullmatch(str(symbol or "").upper())
    if not match:
        return None
    month = int(match.group("month"))
    if not 1 <= month <= 12:
        return None
    return 2000 + int(match.group("year")), month


def third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    first_friday = first + timedelta(days=(4 - first.weekday()) % 7)
    return first_friday + timedelta(days=14)


def contract_expiry(symbol: str) -> date | None:
    parsed = contract_month(symbol)
    return third_friday(*parsed) if parsed else None


def tenor_label(index: int) -> str:
    if index == 0:
        return "第1到期（近月）"
    if index == 1:
        return "第2到期"
    return f"第{index + 1}到期"


@dataclass(frozen=True)
class IndexBar:
    trade_date: date
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class FuturesBar:
    trade_date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    settle: float | None
    volume: float
    open_interest: float
    expiry: date

    @property
    def mark(self) -> float:
        return self.settle if self.settle is not None and self.settle > 0 else self.close


@dataclass(frozen=True)
class ZigZagPivot:
    kind: str
    trade_date: date
    value: float
    confirmed: bool
    confirmation_date: date | None


@dataclass(frozen=True)
class ZigZagWave:
    wave_id: int
    direction: str
    start: ZigZagPivot
    end: ZigZagPivot
    complete: bool


def _pivot(kind: str, point: tuple[date, float], confirmed: bool, confirmation_date: date | None) -> ZigZagPivot:
    return ZigZagPivot(
        kind=kind,
        trade_date=point[0],
        value=float(point[1]),
        confirmed=confirmed,
        confirmation_date=confirmation_date,
    )


def detect_zigzag_waves(
    bars: Iterable[IndexBar],
    threshold: float = ZIGZAG_THRESHOLD,
) -> list[ZigZagWave]:
    """Detect alternating high/low pivots after a 20% reversal from a running extreme."""
    ordered = sorted(bars, key=lambda item: item.trade_date)
    if len(ordered) < 2 or not 0 < threshold < 1:
        return []

    candidate_low = (ordered[0].trade_date, ordered[0].low)
    candidate_high = (ordered[0].trade_date, ordered[0].high)
    trend: str | None = None
    extreme: tuple[date, float] | None = None
    pivots: list[ZigZagPivot] = []

    for bar in ordered[1:]:
        if trend is None:
            if bar.low < candidate_low[1]:
                candidate_low = (bar.trade_date, bar.low)
            if bar.high > candidate_high[1]:
                candidate_high = (bar.trade_date, bar.high)
            up_confirmed = (
                candidate_low[0] < bar.trade_date
                and bar.high >= candidate_low[1] * (1.0 + threshold)
            )
            down_confirmed = (
                candidate_high[0] < bar.trade_date
                and bar.low <= candidate_high[1] * (1.0 - threshold)
            )
            if not up_confirmed and not down_confirmed:
                continue
            if up_confirmed and (
                not down_confirmed
                or bar.high / candidate_low[1] - 1.0
                >= 1.0 - bar.low / candidate_high[1]
            ):
                pivots.append(_pivot("low", candidate_low, True, bar.trade_date))
                trend = "up"
                extreme = (bar.trade_date, bar.high)
            else:
                pivots.append(_pivot("high", candidate_high, True, bar.trade_date))
                trend = "down"
                extreme = (bar.trade_date, bar.low)
            continue

        if extreme is None:
            continue
        if trend == "up":
            if bar.high > extreme[1]:
                extreme = (bar.trade_date, bar.high)
            if extreme[0] < bar.trade_date and bar.low <= extreme[1] * (1.0 - threshold):
                pivots.append(_pivot("high", extreme, True, bar.trade_date))
                trend = "down"
                extreme = (bar.trade_date, bar.low)
        else:
            if bar.low < extreme[1]:
                extreme = (bar.trade_date, bar.low)
            if extreme[0] < bar.trade_date and bar.high >= extreme[1] * (1.0 + threshold):
                pivots.append(_pivot("low", extreme, True, bar.trade_date))
                trend = "up"
                extreme = (bar.trade_date, bar.high)

    if trend is not None and extreme is not None:
        pivots.append(_pivot("high" if trend == "up" else "low", extreme, False, None))

    waves: list[ZigZagWave] = []
    for start, end in zip(pivots, pivots[1:]):
        if start.kind == end.kind or start.trade_date >= end.trade_date:
            continue
        direction = "up" if start.kind == "low" else "down"
        waves.append(
            ZigZagWave(
                wave_id=len(waves) + 1,
                direction=direction,
                start=start,
                end=end,
                complete=end.confirmed,
            )
        )
    return waves


class FuturesUniverse:
    def __init__(self, bars: Iterable[FuturesBar]):
        self.by_date: dict[date, dict[str, FuturesBar]] = {}
        self.by_symbol: dict[str, dict[date, FuturesBar]] = {}
        for bar in bars:
            self.by_date.setdefault(bar.trade_date, {})[bar.symbol] = bar
            self.by_symbol.setdefault(bar.symbol, {})[bar.trade_date] = bar
        self.trading_dates = sorted(self.by_date)

    def active(self, trade_date: date) -> list[FuturesBar]:
        return sorted(
            (
                bar
                for bar in self.by_date.get(trade_date, {}).values()
                if bar.expiry >= trade_date and bar.volume > 0
            ),
            key=lambda item: (item.expiry, item.symbol),
        )

    def next_date(self, trade_date: date) -> date | None:
        return next((item for item in self.trading_dates if item > trade_date), None)

    def dates_between(self, start_date: date, end_date: date) -> list[date]:
        return [item for item in self.trading_dates if start_date <= item <= end_date]

    def expiry_bar(self, symbol: str, expiry: date) -> FuturesBar | None:
        eligible = [
            bar
            for trade_date, bar in self.by_symbol.get(symbol, {}).items()
            if trade_date <= expiry
        ]
        return max(eligible, key=lambda item: item.trade_date) if eligible else None


def transaction_fee(price: float) -> float:
    return price * CONTRACT_MULTIPLIER * FEE_RATE


def directional_points(direction: str, entry_price: float, exit_price: float) -> float:
    return exit_price - entry_price if direction == "up" else entry_price - exit_price


def simulate_wave_contract(
    universe: FuturesUniverse,
    wave: ZigZagWave,
    entry_bar: FuturesBar,
    tenor_index: int,
) -> dict:
    direction = wave.direction
    entry_price = entry_bar.low if direction == "up" else entry_bar.high
    current_symbol = entry_bar.symbol
    current_entry_date = wave.start.trade_date
    current_entry_price = entry_price
    realized_points = 0.0
    fees = transaction_fee(entry_price)
    path: list[dict] = []
    rolls: list[dict] = []

    while True:
        current_bars = universe.by_symbol.get(current_symbol, {})
        current_reference = current_bars.get(current_entry_date) or entry_bar
        expiry = current_reference.expiry
        if wave.end.trade_date <= expiry:
            exit_bar = current_bars.get(wave.end.trade_date)
            if exit_bar is None:
                return {
                    "valid": False,
                    "reason": f"波段终点{wave.end.trade_date}缺少{current_symbol}行情",
                }
            exit_price = exit_bar.high if direction == "up" else exit_bar.low
            realized_points += directional_points(direction, current_entry_price, exit_price)
            fees += transaction_fee(exit_price)
            path.append(
                {
                    "contract": current_symbol,
                    "start_date": current_entry_date.isoformat(),
                    "end_date": wave.end.trade_date.isoformat(),
                    "entry_price": round(current_entry_price, 4),
                    "exit_price": round(exit_price, 4),
                    "end_action": "wave_end" if wave.complete else "provisional_end",
                }
            )
            break

        expiry_bar = universe.expiry_bar(current_symbol, expiry)
        if expiry_bar is None:
            return {"valid": False, "reason": f"{current_symbol}缺少到期日行情"}
        expiry_price = expiry_bar.mark
        realized_points += directional_points(direction, current_entry_price, expiry_price)
        fees += transaction_fee(expiry_price)
        path.append(
            {
                "contract": current_symbol,
                "start_date": current_entry_date.isoformat(),
                "end_date": expiry_bar.trade_date.isoformat(),
                "entry_price": round(current_entry_price, 4),
                "exit_price": round(expiry_price, 4),
                "end_action": "expiry",
            }
        )

        next_date = universe.next_date(expiry_bar.trade_date)
        if next_date is None or next_date > wave.end.trade_date:
            return {"valid": False, "reason": f"{current_symbol}到期后没有可衔接交易日"}
        next_contracts = universe.active(next_date)
        if not next_contracts:
            return {"valid": False, "reason": f"{next_date}没有可用IM合约"}
        next_bar = next_contracts[0]
        fees += transaction_fee(next_bar.open)
        rolls.append(
            {
                "expired_contract": current_symbol,
                "expiry_date": expiry_bar.trade_date.isoformat(),
                "next_contract": next_bar.symbol,
                "next_entry_date": next_date.isoformat(),
                "expiry_price": round(expiry_price, 4),
                "next_entry_price": round(next_bar.open, 4),
            }
        )
        current_symbol = next_bar.symbol
        current_entry_date = next_date
        current_entry_price = next_bar.open
        entry_bar = next_bar

    gross_pnl = realized_points * CONTRACT_MULTIPLIER
    net_pnl = gross_pnl - fees
    trading_days = len(universe.dates_between(wave.start.trade_date, wave.end.trade_date))
    return {
        "valid": True,
        "tenor_index": tenor_index,
        "tenor_label": tenor_label(tenor_index),
        "entry_contract": entry_bar.symbol if not path else path[0]["contract"],
        "entry_date": wave.start.trade_date.isoformat(),
        "entry_price": round(entry_price, 4),
        "exit_date": wave.end.trade_date.isoformat(),
        "exit_contract": path[-1]["contract"],
        "exit_price": path[-1]["exit_price"],
        "direction": direction,
        "holding_days": max(trading_days - 1, 0),
        "roll_count": len(rolls),
        "rolls": rolls,
        "contract_path": path,
        "gross_points": round(realized_points, 4),
        "gross_pnl": round(gross_pnl, 2),
        "fee": round(fees, 2),
        "net_pnl": round(net_pnl, 2),
        "notional_return_pct": round(net_pnl / (entry_price * CONTRACT_MULTIPLIER) * 100.0, 4),
    }


def load_index_bars(db: Session) -> list[IndexBar]:
    rows = db.execute(
        text(
            """
            SELECT trade_date, open_price, high_price, low_price, close_price
            FROM index_daily_data
            WHERE index_code = :index_code
              AND open_price > 0 AND high_price > 0 AND low_price > 0 AND close_price > 0
            ORDER BY trade_date
            """
        ),
        {"index_code": INDEX_CODE},
    ).mappings().all()
    return [
        IndexBar(
            trade_date=parse_date(row["trade_date"]),
            open=float(row["open_price"]),
            high=float(row["high_price"]),
            low=float(row["low_price"]),
            close=float(row["close_price"]),
        )
        for row in rows
    ]


def load_futures_bars(db: Session) -> list[FuturesBar]:
    rows = db.execute(
        text(
            """
            SELECT trade_date, symbol, open_price, high_price, low_price, close_price,
                   settle_price, volume, open_interest
            FROM futures_daily_data
            WHERE variety = 'IM' AND symbol REGEXP '^IM[0-9]{4}$'
            ORDER BY trade_date, symbol
            """
        )
    ).mappings().all()
    latest_trade_date = max((parse_date(row["trade_date"]) for row in rows), default=date.min)
    observed_last_date: dict[str, date] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        observed_last_date[symbol] = max(
            observed_last_date.get(symbol, date.min),
            parse_date(row["trade_date"]),
        )

    result: list[FuturesBar] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        expiry = contract_expiry(symbol)
        observed_expiry = observed_last_date.get(symbol)
        if (
            expiry is not None
            and observed_expiry is not None
            and expiry <= latest_trade_date
            and abs((observed_expiry - expiry).days) <= 7
        ):
            expiry = observed_expiry
        values = {
            key: finite_number(row.get(key))
            for key in ("open_price", "high_price", "low_price", "close_price")
        }
        if expiry is None or any(value is None or value <= 0 for value in values.values()):
            continue
        result.append(
            FuturesBar(
                trade_date=parse_date(row["trade_date"]),
                symbol=symbol,
                open=float(values["open_price"]),
                high=float(values["high_price"]),
                low=float(values["low_price"]),
                close=float(values["close_price"]),
                settle=finite_number(row.get("settle_price")),
                volume=float(finite_number(row.get("volume")) or 0.0),
                open_interest=float(finite_number(row.get("open_interest")) or 0.0),
                expiry=expiry,
            )
        )
    return result


def summarize_direction(waves: list[dict], direction: str) -> dict:
    completed = [item for item in waves if item["direction"] == direction and item["complete"]]
    tenor_indices = sorted(
        {
            int(result["tenor_index"])
            for wave in completed
            for result in wave["contract_results"]
            if result.get("valid") and result.get("tenor_index") is not None
        }
    )
    tenor_rows: list[dict] = []
    for tenor_index in tenor_indices:
        results = [
            result
            for wave in completed
            for result in wave["contract_results"]
            if result.get("valid") and result.get("tenor_index") == tenor_index
        ]
        values = [float(item["net_pnl"]) for item in results]
        tenor_rows.append(
            {
                "tenor_index": tenor_index,
                "tenor_label": tenor_label(tenor_index),
                "wave_count": len(results),
                "total_net_pnl": round(sum(values), 2),
                "average_net_pnl": round(sum(values) / len(values), 2) if values else None,
                "median_net_pnl": round(median(values), 2) if values else None,
                "win_rate": round(sum(1 for value in values if value > 0) / len(values), 6) if values else None,
                "best_wave_count": sum(
                    1 for wave in completed if wave.get("best_tenor_index") == tenor_index
                ),
            }
        )
    valid_rows = [item for item in tenor_rows if item["wave_count"]]
    best = max(valid_rows, key=lambda item: item["total_net_pnl"]) if valid_rows else None
    return {
        "direction": direction,
        "wave_count": len(completed),
        "best_tenor_index": best["tenor_index"] if best else None,
        "tenors": tenor_rows,
    }


def build_report(db: Session) -> dict:
    index_bars = load_index_bars(db)
    futures_bars = load_futures_bars(db)
    universe = FuturesUniverse(futures_bars)
    if not index_bars:
        raise RuntimeError("没有可用的中证1000指数日线")
    if not universe.trading_dates:
        raise RuntimeError("没有可用的IM数字合约日线")

    detected = detect_zigzag_waves(index_bars, ZIGZAG_THRESHOLD)
    first_futures_date = universe.trading_dates[0]
    latest_futures_date = universe.trading_dates[-1]
    eligible = [
        wave
        for wave in detected
        if wave.start.trade_date >= first_futures_date
        and wave.end.trade_date <= latest_futures_date
        and wave.start.trade_date in universe.by_date
        and wave.end.trade_date in universe.by_date
    ]

    waves: list[dict] = []
    for wave_index, wave in enumerate(eligible, start=1):
        active_contracts = universe.active(wave.start.trade_date)
        results: list[dict] = []
        for tenor_index, entry_bar in enumerate(active_contracts):
            result = simulate_wave_contract(universe, wave, entry_bar, tenor_index)
            result.update(
                {
                    "result_id": f"W{wave_index}-{entry_bar.symbol}",
                    "start_contract": entry_bar.symbol,
                    "start_expiry": entry_bar.expiry.isoformat(),
                }
            )
            results.append(result)
        valid_results = [item for item in results if item.get("valid")]
        ordered = sorted(valid_results, key=lambda item: float(item["net_pnl"]), reverse=True)
        ranks = {item["result_id"]: rank for rank, item in enumerate(ordered, start=1)}
        for result in results:
            result["rank"] = ranks.get(result["result_id"])
        best = ordered[0] if ordered else None
        low_pivot = wave.start if wave.start.kind == "low" else wave.end
        high_pivot = wave.start if wave.start.kind == "high" else wave.end
        signed_change = (wave.end.value / wave.start.value - 1.0) * 100.0
        waves.append(
            {
                "wave_id": wave_index,
                "direction": wave.direction,
                "direction_label": "上涨波段" if wave.direction == "up" else "下跌波段",
                "complete": wave.complete,
                "start_date": wave.start.trade_date.isoformat(),
                "start_value": round(wave.start.value, 4),
                "start_kind": wave.start.kind,
                "end_date": wave.end.trade_date.isoformat(),
                "end_value": round(wave.end.value, 4),
                "end_kind": wave.end.kind,
                "confirmation_date": wave.end.confirmation_date.isoformat() if wave.end.confirmation_date else None,
                "low_date": low_pivot.trade_date.isoformat(),
                "low_value": round(low_pivot.value, 4),
                "high_date": high_pivot.trade_date.isoformat(),
                "high_value": round(high_pivot.value, 4),
                "index_change_pct": round(signed_change, 4),
                "amplitude_pct": round(abs(signed_change), 4),
                "best_tenor_index": best.get("tenor_index") if best else None,
                "best_start_contract": best.get("start_contract") if best else None,
                "best_result_id": best.get("result_id") if best else None,
                "contract_results": results,
            }
        )

    wave_point_by_date: dict[str, set[str]] = {}
    for wave in waves:
        wave_point_by_date.setdefault(wave["start_date"], set()).add(wave["start_kind"])
        wave_point_by_date.setdefault(wave["end_date"], set()).add(wave["end_kind"])
    candles = [
        {
            "trade_date": item.trade_date.isoformat(),
            "open": item.open,
            "high": item.high,
            "low": item.low,
            "close": item.close,
            "pivot": "/".join(sorted(wave_point_by_date.get(item.trade_date.isoformat(), set()))) or None,
        }
        for item in index_bars
        if first_futures_date <= item.trade_date <= latest_futures_date
    ]

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": "中证1000二成ZigZag波段股指期货研究",
        "underlying": {"code": INDEX_CODE, "name": INDEX_NAME},
        "data_range": {
            "start": first_futures_date.isoformat(),
            "end": latest_futures_date.isoformat(),
        },
        "methodology": {
            "zigzag_threshold": ZIGZAG_THRESHOLD,
            "entry_exit": "上涨段按低点日合约最低价做多、高点日合约最高价平仓；下跌段反向做空",
            "roll": "仅在持有合约到期后换月：到期日按结算价结束旧合约，下一交易日开盘接入当月合约",
            "multiplier": CONTRACT_MULTIPLIER,
            "fee_rate": FEE_RATE,
            "slippage": 0,
            "hindsight_only": True,
        },
        "sample": {
            "wave_count": len(waves),
            "completed_wave_count": sum(1 for item in waves if item["complete"]),
            "up_wave_count": sum(1 for item in waves if item["direction"] == "up"),
            "down_wave_count": sum(1 for item in waves if item["direction"] == "down"),
            "provisional_wave_count": sum(1 for item in waves if not item["complete"]),
        },
        "direction_summaries": {
            "up": summarize_direction(waves, "up"),
            "down": summarize_direction(waves, "down"),
        },
        "waves": waves,
        "index_candles": candles,
    }
