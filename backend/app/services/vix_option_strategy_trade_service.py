from __future__ import annotations

import math
from bisect import bisect_right
from datetime import date
from numbers import Integral
from typing import Iterable

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session


EXPIRY_BUCKET_LABELS = {
    "current": "当月",
    "next": "下月",
    "quarter_1": "季月1",
    "quarter_2": "季月2",
}
MONEYNESS_LABELS = {
    "itm_1": "实一档",
    "itm_2": "实二档",
    "itm_3": "实三档",
    "atm": "平值",
    "otm_1": "虚一档",
    "otm_2": "虚二档",
    "otm_3": "虚三档",
}


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _contract_month_key(value: object) -> int | None:
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if len(digits) >= 6:
        year = int(digits[:4])
        month = int(digits[4:6])
    elif len(digits) == 4:
        year = 2000 + int(digits[:2])
        month = int(digits[2:4])
    else:
        return None
    if month < 1 or month > 12:
        return None
    return year * 12 + month


def _contract_month_label(entry_date: pd.Timestamp, value: object) -> str:
    key = _contract_month_key(value)
    if key is None:
        return str(value or "-")
    entry_key = entry_date.year * 12 + entry_date.month
    year, month_zero_based = divmod(key, 12)
    if month_zero_based == 0:
        year -= 1
        month = 12
    else:
        month = month_zero_based
    difference = key - entry_key
    if difference == 0:
        prefix = "当月"
    elif difference == 1:
        prefix = "下月"
    elif month in {3, 6, 9, 12}:
        prefix = "季月" if difference <= 6 else "远季月"
    else:
        prefix = f"{difference}个月后" if difference > 1 else "近月"
    return f"{prefix}({year % 100:02d}{month:02d})"


def _expiry_bucket_map(values: Iterable[object]) -> dict[int, str]:
    months = sorted({key for key in (_contract_month_key(value) for value in values) if key is not None})
    result: dict[int, str] = {}
    if months:
        result[months[0]] = "current"
    if len(months) >= 2:
        result[months[1]] = "next"
    quarter_months = [
        key
        for key in months
        if key not in result and ((key - 1) % 12 + 1) in {3, 6, 9, 12}
    ]
    for index, key in enumerate(quarter_months[:2], start=1):
        result[key] = f"quarter_{index}"
    return result


def _calendar_expiry_bucket_map(entry_date: pd.Timestamp, values: Iterable[object]) -> dict[int, str]:
    entry_key = entry_date.year * 12 + entry_date.month
    months = sorted(
        {
            key
            for key in (_contract_month_key(value) for value in values)
            if key is not None and key >= entry_key
        }
    )
    result: dict[int, str] = {}
    for key in months:
        difference = key - entry_key
        if difference == 0:
            result[key] = "current"
        elif difference == 1:
            result[key] = "next"
    quarter_months = [
        key
        for key in months
        if key not in result and ((key - 1) % 12 + 1) in {3, 6, 9, 12}
    ]
    for index, key in enumerate(quarter_months[:2], start=1):
        result[key] = f"quarter_{index}"
    return result


class VixOptionStrategyTradeService:
    def __init__(self, db: Session | None):
        self.db = db

    def _read(self, sql: str, params: dict) -> pd.DataFrame:
        if self.db is None:
            raise RuntimeError("database session is required")
        return pd.read_sql(text(sql), self.db.connection(), params=params)

    @staticmethod
    def _cffex_expiry(value: object) -> pd.Timestamp:
        digits = "".join(character for character in str(value or "") if character.isdigit())
        if len(digits) != 4:
            return pd.NaT
        year = 2000 + int(digits[:2])
        month = int(digits[2:])
        first = pd.Timestamp(year=year, month=month, day=1)
        friday_offset = (4 - first.weekday()) % 7
        return first + pd.Timedelta(days=friday_offset + 14)

    def _load_frames(
        self,
        target_code: str,
        template: dict,
        start_date: date,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        target_index = self._read(
            """
            SELECT trade_date, close_price
            FROM index_daily_data
            WHERE index_code = :code AND close_price > 0
            ORDER BY trade_date
            """,
            {"code": target_code},
        )
        exchange = str(template["exchange"])
        product_code = str(template["product_code"])
        if exchange == "CFFEX":
            underlying = self._read(
                """
                SELECT trade_date, open_price, close_price
                FROM index_daily_data
                WHERE index_code = :code AND close_price > 0
                ORDER BY trade_date
                """,
                {"code": target_code},
            )
            options = self._read(
                """
                SELECT contract_code, trade_date, contract_month, option_type, strike_price,
                       open_price, high_price, low_price, close_price, volume, open_interest
                FROM option_cffex_rtj_daily_data
                WHERE product_prefix = :product_code
                  AND option_type IN ('CALL', 'PUT')
                  AND trade_date >= :start_date
                ORDER BY trade_date, contract_code
                """,
                {"product_code": product_code, "start_date": start_date},
            )
            options["last_trade_date"] = options["contract_month"].map(self._cffex_expiry)
            options["contract_unit"] = 100.0
        else:
            underlying = self._read(
                """
                SELECT trade_date, open_price, close_price
                FROM etf_daily_data_sina
                WHERE etf_code = :code AND close_price > 0
                ORDER BY trade_date
                """,
                {"code": product_code},
            )
            options = self._read(
                """
                SELECT d.contract_code, d.trade_date, d.contract_month, d.option_type,
                       d.strike_price, d.open_price, d.high_price, d.low_price, d.close_price,
                       d.volume, d.open_interest, i.last_trade_date, i.contract_unit
                FROM option_exchange_contract_daily_data d
                JOIN option_exchange_contract_info i
                  ON i.exchange = d.exchange AND i.contract_code = d.contract_code
                WHERE d.exchange = :exchange
                  AND d.underlying_code = :product_code
                  AND d.trade_date >= :start_date
                  AND i.contract_trade_code REGEXP 'M[0-9]+$'
                ORDER BY d.trade_date, d.contract_code
                """,
                {"exchange": exchange, "product_code": product_code, "start_date": start_date},
            )
        return target_index, underlying, options

    @staticmethod
    def _normalize_frames(
        target_index: pd.DataFrame,
        underlying: pd.DataFrame,
        options: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        for frame in (target_index, underlying):
            frame["trade_date"] = pd.to_datetime(frame["trade_date"])
            frame.drop_duplicates("trade_date", keep="last", inplace=True)
            frame.set_index("trade_date", inplace=True)
            frame.sort_index(inplace=True)
        if options.empty:
            return target_index, underlying, options
        for column in ("trade_date", "last_trade_date"):
            options[column] = pd.to_datetime(options[column])
        options["option_type"] = (
            options["option_type"]
            .astype(str)
            .str.upper()
            .replace({"认购": "CALL", "购": "CALL", "C": "CALL", "认沽": "PUT", "沽": "PUT", "P": "PUT"})
        )
        for column in (
            "strike_price",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume",
            "open_interest",
            "contract_unit",
        ):
            options[column] = pd.to_numeric(options[column], errors="coerce")
        options["dte"] = (options["last_trade_date"] - options["trade_date"]).dt.days
        options.drop_duplicates(["trade_date", "contract_code"], keep="last", inplace=True)
        return target_index, underlying, options

    @staticmethod
    def _direction(target_index: pd.DataFrame, signal_date: pd.Timestamp) -> tuple[str, str, float | None, float | None]:
        if signal_date not in target_index.index:
            return "", "信号日缺少指数收盘价", None, None
        position = target_index.index.get_loc(signal_date)
        if not isinstance(position, Integral):
            return "", "信号日行情位置无法确定", None, None
        close = float(target_index.iloc[position]["close_price"])
        prior_20 = (
            close / float(target_index.iloc[position - 20]["close_price"]) - 1
            if position >= 20 and float(target_index.iloc[position - 20]["close_price"]) > 0
            else None
        )
        prior_40 = (
            close / float(target_index.iloc[position - 40]["close_price"]) - 1
            if position >= 40 and float(target_index.iloc[position - 40]["close_price"]) > 0
            else None
        )
        if prior_20 is not None and prior_20 >= 0.03:
            return "PUT", "前20个交易日涨幅达到3%，按高位波动买认沽", prior_20, prior_40
        if prior_40 is not None and prior_40 >= 0.06:
            return "PUT", "前40个交易日涨幅达到6%，按高位波动买认沽", prior_20, prior_40
        return "CALL", "前期未明显涨多，按恐慌后的修复买认购", prior_20, prior_40

    @staticmethod
    def _valid_entry_rows(rows: pd.DataFrame, option_type: str, minimum_expiry: pd.Timestamp) -> pd.DataFrame:
        if rows.empty:
            return rows
        valid = rows.copy()
        valid = valid[
            (valid["option_type"] == option_type)
            & (valid["last_trade_date"] >= minimum_expiry)
            & (valid["open_price"] > 0)
            & (valid["close_price"] > 0)
            & (valid["volume"] > 0)
            & (valid["high_price"] >= valid[["open_price", "close_price"]].max(axis=1))
            & (valid["low_price"] >= 0)
            & (valid["low_price"] <= valid[["open_price", "close_price"]].min(axis=1))
        ]
        return valid

    @classmethod
    def _select_contract(
        cls,
        entry_rows: pd.DataFrame,
        entry_date: pd.Timestamp,
        underlying_price: float,
        template: dict,
        minimum_expiry: pd.Timestamp,
    ) -> pd.Series | None:
        option_type = str(template["option_type"])
        eligible = cls._valid_entry_rows(entry_rows, option_type, minimum_expiry)
        if eligible.empty:
            return None
        if template["expiry_bucket"] in {"current", "next"}:
            bucket_map = _expiry_bucket_map(eligible["contract_month"].dropna().unique())
        else:
            bucket_map = _calendar_expiry_bucket_map(
                entry_date,
                entry_rows["contract_month"].dropna().unique(),
            )
        eligible = eligible.copy()
        eligible["contract_month_key"] = eligible["contract_month"].map(_contract_month_key)
        eligible["expiry_bucket"] = eligible["contract_month_key"].map(bucket_map)
        eligible = eligible[eligible["expiry_bucket"] == template["expiry_bucket"]].copy()
        if eligible.empty:
            return None
        strikes = sorted(float(value) for value in eligible["strike_price"].dropna().unique() if float(value) > 0)
        if not strikes:
            return None
        at_the_money = min(strikes, key=lambda value: (abs(value - underlying_price), value))
        moneyness = str(template["moneyness"])
        if moneyness == "atm":
            target_strike = at_the_money
        else:
            prefix, _, rank_text = moneyness.partition("_")
            if prefix not in {"itm", "otm"} or not rank_text.isdigit():
                return None
            rank = int(rank_text)
            if option_type == "CALL":
                candidates = (
                    sorted((value for value in strikes if value < at_the_money), reverse=True)
                    if prefix == "itm"
                    else sorted(value for value in strikes if value > at_the_money)
                )
            else:
                candidates = (
                    sorted(value for value in strikes if value > at_the_money)
                    if prefix == "itm"
                    else sorted((value for value in strikes if value < at_the_money), reverse=True)
                )
            if rank <= 0 or len(candidates) < rank:
                return None
            target_strike = candidates[rank - 1]
        eligible = eligible[eligible["strike_price"] == target_strike].copy()
        eligible["strike_distance"] = (eligible["strike_price"] - underlying_price).abs() / underlying_price
        eligible.sort_values(
            ["strike_distance", "dte", "volume", "open_interest"],
            ascending=[True, True, False, False],
            inplace=True,
        )
        return eligible.iloc[0] if not eligible.empty else None

    @staticmethod
    def _position_bucket(position_pct: float) -> str:
        if position_pct <= 0:
            return "flat"
        if position_pct <= 0.25:
            return "light"
        if position_pct <= 0.5:
            return "medium"
        if position_pct <= 0.75:
            return "heavy"
        return "full"

    @classmethod
    def _build_portfolio_result(
        cls,
        signal_dates: list[pd.Timestamp],
        template: dict,
        underlying: pd.DataFrame,
        histories: dict[str, pd.DataFrame],
        trades: list[dict],
    ) -> dict:
        initial_capital = float(template.get("initial_capital") or 1_000_000)
        quantity = int(template.get("contracts_per_trade") or 1)
        if not signal_dates or underlying.empty:
            return {
                "initial_capital": initial_capital,
                "cumulative_return_pct": 0.0,
                "annualized_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "points": [],
            }

        calendar = pd.DatetimeIndex(underlying.index)
        portfolio_dates = calendar[calendar >= min(signal_dates)]
        signal_date_set = set(signal_dates)
        buys_by_date: dict[pd.Timestamp, list[dict]] = {}
        sells_by_date: dict[pd.Timestamp, list[dict]] = {}
        for trade in trades:
            if trade.get("status") != "completed":
                continue
            buy_date = pd.Timestamp(trade["buy_date"])
            sell_date = pd.Timestamp(trade["sell_date"])
            buys_by_date.setdefault(buy_date, []).append(trade)
            sells_by_date.setdefault(sell_date, []).append(trade)

        cash = initial_capital
        active_positions: list[dict] = []
        points: list[dict] = []
        for trade_date in portfolio_dates:
            for trade in buys_by_date.get(trade_date, []):
                buy_amount = float(trade["buy_price"]) * float(trade["contract_unit"]) * quantity
                if buy_amount > cash + 1e-8:
                    trade["status"] = "unavailable"
                    trade["status_reason"] = "组合资金不足，未执行买入"
                    trade["contract_quantity"] = None
                    trade["buy_amount"] = None
                    trade["sell_amount"] = None
                    trade["profit_per_contract"] = None
                    trade["return_pct"] = None
                    continue
                trade["contract_quantity"] = quantity
                trade["buy_amount"] = buy_amount
                trade["sell_amount"] = float(trade["sell_price"]) * float(trade["contract_unit"]) * quantity
                cash -= buy_amount
                active_positions.append(trade)

            for trade in sells_by_date.get(trade_date, []):
                if trade not in active_positions:
                    continue
                cash += float(trade["sell_amount"])
                active_positions.remove(trade)

            position_value = 0.0
            for trade in active_positions:
                history = histories.get(str(trade["contract_code"]))
                if history is None or trade_date not in history.index:
                    continue
                close_price = _number(history.loc[trade_date, "close_price"])
                if close_price is None or close_price <= 0:
                    continue
                position_value += close_price * float(trade["contract_unit"]) * int(trade["contract_quantity"])

            total_capital = cash + position_value
            position_pct = position_value / total_capital if total_capital > 0 else 0.0
            points.append(
                {
                    "trade_date": trade_date.date(),
                    "nav": total_capital / initial_capital,
                    "benchmark_nav": None,
                    "signal": "blue" if trade_date in signal_date_set else None,
                    "close_price": None,
                    "position_value": position_value,
                    "position_pct": position_pct,
                    "position_bucket": cls._position_bucket(position_pct),
                }
            )

        if not points:
            return {
                "initial_capital": initial_capital,
                "cumulative_return_pct": 0.0,
                "annualized_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "points": [],
            }
        nav_values = [float(point["nav"]) for point in points]
        peak = nav_values[0]
        max_drawdown = 0.0
        for nav in nav_values:
            peak = max(peak, nav)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - nav) / peak)
        final_nav = nav_values[-1]
        elapsed_days = max((points[-1]["trade_date"] - points[0]["trade_date"]).days, 0)
        elapsed_years = elapsed_days / 365.25
        annualized_return = (
            (final_nav ** (1 / elapsed_years) - 1) * 100
            if elapsed_years > 0 and final_nav > 0
            else 0.0
        )
        return {
            "initial_capital": initial_capital,
            "cumulative_return_pct": (final_nav - 1) * 100,
            "annualized_return_pct": annualized_return,
            "max_drawdown_pct": max_drawdown * 100,
            "points": points,
        }

    def calculate_from_frames(
        self,
        signal_dates: Iterable[str | date],
        template: dict,
        target_index: pd.DataFrame,
        underlying: pd.DataFrame,
        options: pd.DataFrame,
    ) -> dict:
        target_index, underlying, options = self._normalize_frames(target_index, underlying, options)
        calendar = pd.DatetimeIndex(underlying.index)
        option_dates = {trade_date: rows.copy() for trade_date, rows in options.groupby("trade_date")}
        first_option_date = options["trade_date"].min() if not options.empty else None
        histories = {
            str(contract_code): rows.set_index("trade_date").sort_index()
            for contract_code, rows in options.groupby("contract_code")
        }
        holding_days = int(template["holding_days"])
        slippage = float(template.get("slippage", 0.005))
        rows: list[dict] = []
        normalized_signal_dates = sorted({pd.Timestamp(value) for value in signal_dates})

        for raw_signal_date in normalized_signal_dates:
            required_type, direction_reason, prior_20, prior_40 = self._direction(target_index, raw_signal_date)
            base = {
                "signal_date": raw_signal_date.date(),
                "product_code": template["product_code"],
                "product_name": template["product_name"],
                "exchange": template["exchange"],
                "option_type": required_type or template["option_type"],
                "expiry_bucket": template["expiry_bucket"],
                "expiry_bucket_label": template["expiry_bucket_label"],
                "moneyness": template["moneyness"],
                "moneyness_label": template["moneyness_label"],
                "holding_days": holding_days,
                "direction_reason": direction_reason,
                "prior_20d_return_pct": None if prior_20 is None else prior_20 * 100,
                "prior_40d_return_pct": None if prior_40 is None else prior_40 * 100,
                "contract_code": None,
                "contract_month": None,
                "contract_month_label": None,
                "strike_price": None,
                "contract_unit": None,
                "contract_quantity": None,
                "buy_date": None,
                "buy_price": None,
                "buy_amount": None,
                "sell_date": None,
                "sell_price": None,
                "sell_amount": None,
                "profit_per_contract": None,
                "return_pct": None,
            }
            if not required_type:
                rows.append({**base, "status": "unavailable", "status_reason": direction_reason})
                continue
            entry_position = bisect_right(calendar, raw_signal_date)
            if entry_position >= len(calendar):
                rows.append({**base, "status": "pending", "status_reason": "尚无下一交易日买入行情"})
                continue
            exit_position = entry_position + holding_days
            if exit_position >= len(calendar):
                rows.append({**base, "status": "pending", "status_reason": "持有期尚未结束"})
                continue
            entry_date = calendar[entry_position]
            exit_date = calendar[exit_position]
            entry_rows = option_dates.get(entry_date)
            underlying_price = _number(underlying.loc[entry_date, "open_price"]) if entry_date in underlying.index else None
            if entry_rows is None or underlying_price is None or underlying_price <= 0:
                if first_option_date is not None and entry_date < first_option_date:
                    rows.append(
                        {
                            **base,
                            "buy_date": entry_date.date(),
                            "status": "not_listed",
                            "status_reason": f"该期权品种尚未上市（数据库首日{first_option_date.date()}）",
                        }
                    )
                else:
                    rows.append({**base, "status": "unavailable", "status_reason": "买入日缺少期权或标的开盘行情"})
                continue
            event_template = {**template, "option_type": required_type}
            selected = self._select_contract(
                entry_rows,
                entry_date,
                underlying_price,
                event_template,
                exit_date + pd.Timedelta(days=3),
            )
            if selected is None:
                rows.append({**base, "buy_date": entry_date.date(), "status": "unavailable", "status_reason": "没有符合月份和档位的有效合约"})
                continue
            contract_code = str(selected["contract_code"])
            history = histories.get(contract_code)
            expected_dates = calendar[(calendar >= entry_date) & (calendar <= exit_date)]
            if history is None or entry_date not in history.index or exit_date not in history.index:
                rows.append({**base, "buy_date": entry_date.date(), "contract_code": contract_code, "status": "unavailable", "status_reason": "合约持有期行情不完整"})
                continue
            path = history.reindex(expected_dates)
            if path["close_price"].isna().any():
                rows.append({**base, "buy_date": entry_date.date(), "contract_code": contract_code, "status": "unavailable", "status_reason": "合约持有期存在缺失交易日"})
                continue
            raw_buy_price = _number(selected["open_price"])
            raw_sell_price = _number(path.loc[exit_date, "close_price"])
            if raw_buy_price is None or raw_buy_price <= 0 or raw_sell_price is None or raw_sell_price <= 0:
                rows.append({**base, "buy_date": entry_date.date(), "contract_code": contract_code, "status": "unavailable", "status_reason": "买卖价格无效"})
                continue
            buy_price = raw_buy_price * (1 + slippage)
            sell_price = raw_sell_price * (1 - slippage)
            contract_unit = _number(selected.get("contract_unit")) or (100.0 if template["exchange"] == "CFFEX" else 10_000.0)
            profit = (sell_price - buy_price) * contract_unit
            rows.append(
                {
                    **base,
                    "status": "completed",
                    "status_reason": "已按信号方向完成买卖",
                    "contract_code": contract_code,
                    "contract_month": str(selected["contract_month"]),
                    "contract_month_label": f"{template['expiry_bucket_label']}({str(selected['contract_month'])})",
                    "strike_price": float(selected["strike_price"]),
                    "contract_unit": contract_unit,
                    "buy_date": entry_date.date(),
                    "buy_price": buy_price,
                    "sell_date": exit_date.date(),
                    "sell_price": sell_price,
                    "profit_per_contract": profit,
                    "return_pct": (sell_price / buy_price - 1) * 100,
                }
            )

        portfolio = self._build_portfolio_result(
            normalized_signal_dates,
            template,
            underlying,
            histories,
            rows,
        )
        return {
            "template": template,
            "trades": rows,
            "summary": {
                "signal_count": len(rows),
                "completed_count": sum(item["status"] == "completed" for item in rows),
                "pending_count": sum(item["status"] == "pending" for item in rows),
                "direction_mismatch_count": sum(item["status"] == "direction_mismatch" for item in rows),
                "not_listed_count": sum(item["status"] == "not_listed" for item in rows),
                "unavailable_count": sum(item["status"] == "unavailable" for item in rows),
            },
            **portfolio,
        }

    def calculate(self, signal_dates: Iterable[str | date], target_code: str, template: dict) -> dict:
        dates = sorted({date.fromisoformat(str(value)) if not isinstance(value, date) else value for value in signal_dates})
        if not dates:
            initial_capital = float(template.get("initial_capital") or 1_000_000)
            return {
                "template": template,
                "trades": [],
                "summary": {
                    "signal_count": 0,
                    "completed_count": 0,
                    "pending_count": 0,
                    "direction_mismatch_count": 0,
                    "not_listed_count": 0,
                    "unavailable_count": 0,
                },
                "initial_capital": initial_capital,
                "cumulative_return_pct": 0.0,
                "annualized_return_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "points": [],
            }
        target_index, underlying, options = self._load_frames(target_code, template, dates[0])
        return self.calculate_from_frames(dates, template, target_index, underlying, options)
