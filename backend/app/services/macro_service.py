import json
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

    def get_bank_liquidity(self, start_date: date | None = None, end_date: date | None = None) -> dict:
        query_start = start_date or date(2017, 5, 31)
        query_end = end_date or date.today()
        params = {"start_date": query_start, "end_date": query_end}
        try:
            rows = self.db.execute(
                text(
                    """
                    SELECT
                        trade_date,
                        fr001_pct, fr007_pct, fdr001_pct, fdr007_pct,
                        dr001_weighted_pct, dr007_weighted_pct,
                        r001_weighted_pct, r007_weighted_pct,
                        reverse_repo_7d_policy_rate_pct,
                        reverse_repo_7d_policy_source_date,
                        reverse_repo_7d_policy_available_at,
                        source_url_reverse_repo_7d_policy,
                        bank_bond_aaa_1y_yield_pct, cgb_1y_yield_pct,
                        factor_fdr007_policy_spread_bp,
                        factor_overnight_pressure_bp,
                        factor_nonbank_layering_bp,
                        factor_bank_funding_spread_bp,
                        pct_fdr007_policy_spread,
                        pct_overnight_pressure,
                        pct_nonbank_layering,
                        pct_bank_funding_spread,
                        liquidity_tightness_score, liquidity_state,
                        liquidity_trend, score_change_5d,
                        reverse_repo_injection_cny,
                        reverse_repo_maturity_cny,
                        reverse_repo_net_cny,
                        reverse_repo_net_5d_cny,
                        reverse_repo_net_20d_cny,
                        frr_source_date, frr_available_at,
                        closing_repo_source_date, closing_repo_available_at,
                        chinabond_source_date, chinabond_available_at,
                        pbc_source_date, pbc_available_at,
                        source_url_frr, source_url_closing_repo,
                        source_url_chinabond, source_url_pbc,
                        components_json, sources_json
                    FROM cn_bank_liquidity_daily
                    WHERE trade_date BETWEEN :start_date AND :end_date
                    ORDER BY trade_date ASC
                    """
                ),
                params,
            ).mappings().all()
            monthly_rows = self.db.execute(
                text(
                    """
                    SELECT
                        period_end, category, tool_type, tool_name,
                        injection_cny, withdrawal_cny, net_injection_cny,
                        coverage_status, published_at, source_url
                    FROM cn_pbc_liquidity_tool_monthly
                    WHERE period_end BETWEEN :start_date AND :end_date
                    ORDER BY period_end ASC, category ASC, tool_name ASC
                    """
                ),
                params,
            ).mappings().all()
        except SQLAlchemyError as exc:
            raise RuntimeError("银行流动性数据表尚未准备完成") from exc

        daily_points = [self._serialize_bank_liquidity_row(row) for row in rows]
        monthly_points = [self._serialize_bank_liquidity_row(row) for row in monthly_rows]
        latest = daily_points[-1] if daily_points else None
        score_start = next(
            (point["trade_date"] for point in daily_points if point.get("liquidity_tightness_score") is not None),
            None,
        )
        closing_repo_start = next(
            (
                point["trade_date"]
                for point in daily_points
                if all(
                    point.get(field) is not None
                    for field in (
                        "dr001_weighted_pct",
                        "dr007_weighted_pct",
                        "r001_weighted_pct",
                        "r007_weighted_pct",
                    )
                )
            ),
            None,
        )
        latest_complete = next(
            (
                point["trade_date"]
                for point in reversed(daily_points)
                if point.get("liquidity_tightness_score") is not None
                and all(
                    point.get(field) is not None
                    for field in (
                        "dr001_weighted_pct",
                        "dr007_weighted_pct",
                        "r001_weighted_pct",
                        "r007_weighted_pct",
                    )
                )
            ),
            None,
        )
        return {
            "start_date": query_start.isoformat(),
            "end_date": query_end.isoformat(),
            "latest": latest,
            "daily_points": daily_points,
            "monthly_tool_points": monthly_points,
            "coverage": {
                "official_history_start": daily_points[0]["trade_date"] if daily_points else None,
                "score_start": score_start,
                "closing_repo_start": closing_repo_start,
                "latest_date": latest.get("trade_date") if latest else None,
                "latest_complete_date": latest_complete,
                "monthly_tools_start": monthly_points[0]["period_end"] if monthly_points else None,
                "closing_repo_note": "全日DR/R仅展示中国货币网当前公开窗口及此后每日积累的官方原值。",
                "monthly_tools_note": "央行月度工具仅从官方完整披露期展示；更早不拼接、不估算总量。",
            },
            "methodology": {
                "score": "四项历史中间秩百分位按40%/20%/20%/20%加权；每项只使用当日前最多1260个有效观测，至少252个样本。",
                "states": "0–<30宽松，30–<60平衡，60–<80偏紧，80–100紧张。",
                "trend": "紧张度5日变化不少于10分为收紧，不高于-10分为转松，其余为平稳。",
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

    @staticmethod
    def _serialize_bank_liquidity_row(row) -> dict:
        payload = dict(row)
        date_keys = {
            "trade_date",
            "period_end",
            "frr_source_date",
            "closing_repo_source_date",
            "chinabond_source_date",
            "pbc_source_date",
            "reverse_repo_7d_policy_source_date",
        }
        datetime_keys = {
            "frr_available_at",
            "closing_repo_available_at",
            "chinabond_available_at",
            "pbc_available_at",
            "reverse_repo_7d_policy_available_at",
            "published_at",
        }
        text_keys = {
            "liquidity_state",
            "liquidity_trend",
            "category",
            "tool_type",
            "tool_name",
            "coverage_status",
            "source_url",
            "source_url_frr",
            "source_url_closing_repo",
            "source_url_chinabond",
            "source_url_pbc",
            "source_url_reverse_repo_7d_policy",
        }
        json_keys = {"components_json", "sources_json"}
        for key, value in list(payload.items()):
            if key in date_keys:
                payload[key] = value.isoformat() if value else None
            elif key in datetime_keys:
                payload[key] = value.isoformat(sep=" ", timespec="seconds") if value else None
            elif key in json_keys:
                if isinstance(value, str):
                    try:
                        payload[key] = json.loads(value)
                    except json.JSONDecodeError:
                        payload[key] = None
            elif key not in text_keys:
                payload[key] = float(value) if value is not None else None
        return payload
