from collections import deque
from datetime import date
from math import sqrt

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


class MacroService:
    CHINEXT_INDEX_CODE = "sz399006"
    STAR50_INDEX_CODE = "sh000688"
    CSI_DIVIDEND_INDEX_CODE = "sh000922"
    BOLL_WINDOW = 20
    BOLL_STD_MULTIPLIER = 2
    STYLE_BUFFER_RATIO = 0.01
    MACRO_BOLL_FIELDS = (
        "hs300_equity_bond_spread_pp",
        "csi1000_equity_bond_spread_pp",
        "buffett_indicator_pct",
        "household_deposit_market_cap_ratio_pct",
    )
    STYLE_RATIO_FIELDS = (
        "chinext_csi_dividend_ratio",
        "star50_csi_dividend_ratio",
    )

    def __init__(self, db: Session):
        self.db = db

    def get_dashboard(self, start_date: date | None = None, end_date: date | None = None) -> dict:
        params = {
            "start_date": start_date or date(2005, 4, 8),
            "end_date": end_date or date.today(),
            "chinext_index_code": self.CHINEXT_INDEX_CODE,
            "star50_index_code": self.STAR50_INDEX_CODE,
            "csi_dividend_index_code": self.CSI_DIVIDEND_INDEX_CODE,
        }
        try:
            rows = self.db.execute(
                text(
                    """
                    SELECT
                        macro.trade_date,
                        macro.hs300_pe_ttm,
                        macro.csi1000_pe_ttm,
                        macro.cn_gov_bond_10y_yield_pct,
                        macro.a_share_total_market_cap_cny,
                        macro.trailing_4q_nominal_gdp_cny,
                        macro.household_deposit_cny,
                        macro.hs300_equity_bond_spread_pp,
                        macro.csi1000_equity_bond_spread_pp,
                        macro.buffett_indicator_pct,
                        macro.household_deposit_market_cap_ratio_pct,
                        macro.gdp_period_end,
                        macro.deposit_period_end,
                        macro.market_cap_source,
                        macro.market_cap_adjustment_factor,
                        macro.gdp_source,
                        CASE
                            WHEN csi_dividend.close_price > 0
                                THEN chinext.close_price / csi_dividend.close_price
                            ELSE NULL
                        END AS chinext_csi_dividend_ratio,
                        CASE
                            WHEN csi_dividend.close_price > 0
                                THEN star50.close_price / csi_dividend.close_price
                            ELSE NULL
                        END AS star50_csi_dividend_ratio
                    FROM cn_macro_indicator_daily AS macro
                    LEFT JOIN index_daily_data AS chinext
                      ON chinext.trade_date = macro.trade_date
                     AND chinext.index_code = :chinext_index_code
                    LEFT JOIN index_daily_data AS star50
                      ON star50.trade_date = macro.trade_date
                     AND star50.index_code = :star50_index_code
                    LEFT JOIN index_daily_data AS csi_dividend
                      ON csi_dividend.trade_date = macro.trade_date
                     AND csi_dividend.index_code = :csi_dividend_index_code
                    WHERE macro.trade_date BETWEEN :start_date AND :end_date
                    ORDER BY macro.trade_date ASC
                    """
                ),
                params,
            ).mappings().all()
        except SQLAlchemyError as exc:
            raise RuntimeError("A股宏观指标数据表尚未准备完成") from exc

        points = [self._serialize_row(row) for row in rows]
        self._append_macro_bollinger_bands(points)
        self._append_style_indicators(points)
        latest = points[-1] if points else None
        return {
            "start_date": params["start_date"].isoformat(),
            "end_date": params["end_date"].isoformat(),
            "latest": latest,
            "points": points,
            "methodology": {
                "equity_bond_spread": "指数盈利收益率（1/滚动市盈率）减中国10年期国债到期收益率；附加BOLL(20,2)",
                "buffett_indicator": "官网可用期使用沪深北三所全部A股总市值；早期总市值按重叠期中位比例桥接官网口径，再除以同期参考名义GDP；附加BOLL(20,2)",
                "deposit_market_cap_ratio": "人民币住户存款余额 / A股总市值；官网可用期优先，早期使用已校准的长期总市值序列；附加BOLL(20,2)",
                "growth_dividend_ratio": "成长指数收盘价 / 中证红利收盘价；同时计算MA20、上下1%缓冲轨与BOLL(20,2)，所有序列按共同交易日对齐",
            },
        }

    @classmethod
    def _append_macro_bollinger_bands(cls, points: list[dict]) -> None:
        for value_field in cls.MACRO_BOLL_FIELDS:
            middle_field = f"{value_field}_boll_mid"
            upper_field = f"{value_field}_boll_upper"
            lower_field = f"{value_field}_boll_lower"
            window: deque[float] = deque(maxlen=cls.BOLL_WINDOW)

            for point in points:
                point[middle_field] = None
                point[upper_field] = None
                point[lower_field] = None
                raw_value = point.get(value_field)
                if raw_value is None:
                    continue

                window.append(float(raw_value))
                if len(window) < cls.BOLL_WINDOW:
                    continue

                moving_average = sum(window) / cls.BOLL_WINDOW
                variance = sum((value - moving_average) ** 2 for value in window) / cls.BOLL_WINDOW
                standard_deviation = sqrt(variance)
                point[middle_field] = moving_average
                point[upper_field] = moving_average + cls.BOLL_STD_MULTIPLIER * standard_deviation
                point[lower_field] = moving_average - cls.BOLL_STD_MULTIPLIER * standard_deviation

    @classmethod
    def _append_style_indicators(cls, points: list[dict]) -> None:
        for ratio_field in cls.STYLE_RATIO_FIELDS:
            ma_field = f"{ratio_field}_ma20"
            upper_field = f"{ratio_field}_upper_1pct"
            lower_field = f"{ratio_field}_lower_1pct"
            boll_upper_field = f"{ratio_field}_boll_upper"
            boll_lower_field = f"{ratio_field}_boll_lower"
            window: deque[float] = deque(maxlen=cls.BOLL_WINDOW)

            for point in points:
                point[ma_field] = None
                point[upper_field] = None
                point[lower_field] = None
                point[boll_upper_field] = None
                point[boll_lower_field] = None
                ratio_value = point.get(ratio_field)
                if ratio_value is None:
                    continue

                window.append(float(ratio_value))
                if len(window) < cls.BOLL_WINDOW:
                    continue

                moving_average = sum(window) / cls.BOLL_WINDOW
                variance = sum((value - moving_average) ** 2 for value in window) / cls.BOLL_WINDOW
                standard_deviation = sqrt(variance)
                point[ma_field] = moving_average
                point[upper_field] = moving_average * (1 + cls.STYLE_BUFFER_RATIO)
                point[lower_field] = moving_average * (1 - cls.STYLE_BUFFER_RATIO)
                point[boll_upper_field] = moving_average + cls.BOLL_STD_MULTIPLIER * standard_deviation
                point[boll_lower_field] = moving_average - cls.BOLL_STD_MULTIPLIER * standard_deviation

    @staticmethod
    def _serialize_row(row) -> dict:
        payload = dict(row)
        for key in ("trade_date", "gdp_period_end", "deposit_period_end"):
            value = payload.get(key)
            payload[key] = value.isoformat() if value else None
        text_keys = {"market_cap_source", "gdp_source"}
        for key, value in list(payload.items()):
            if key not in {"trade_date", "gdp_period_end", "deposit_period_end", *text_keys}:
                payload[key] = float(value) if value is not None else None
        return payload
