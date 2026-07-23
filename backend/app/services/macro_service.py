from datetime import date

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


class MacroService:
    def __init__(self, db: Session):
        self.db = db

    def get_dashboard(self, start_date: date | None = None, end_date: date | None = None) -> dict:
        params = {
            "start_date": start_date or date(2005, 4, 8),
            "end_date": end_date or date.today(),
        }
        try:
            rows = self.db.execute(
                text(
                    """
                    SELECT
                        trade_date,
                        hs300_pe_ttm,
                        csi1000_pe_ttm,
                        cn_gov_bond_10y_yield_pct,
                        a_share_total_market_cap_cny,
                        trailing_4q_nominal_gdp_cny,
                        household_deposit_cny,
                        hs300_equity_bond_spread_pp,
                        csi1000_equity_bond_spread_pp,
                        buffett_indicator_pct,
                        household_deposit_market_cap_ratio_pct,
                        gdp_period_end,
                        deposit_period_end,
                        market_cap_source,
                        market_cap_adjustment_factor,
                        gdp_source
                    FROM cn_macro_indicator_daily
                    WHERE trade_date BETWEEN :start_date AND :end_date
                    ORDER BY trade_date ASC
                    """
                ),
                params,
            ).mappings().all()
        except SQLAlchemyError as exc:
            raise RuntimeError("A股宏观指标数据表尚未准备完成") from exc

        points = [self._serialize_row(row) for row in rows]
        latest = points[-1] if points else None
        return {
            "start_date": params["start_date"].isoformat(),
            "end_date": params["end_date"].isoformat(),
            "latest": latest,
            "points": points,
            "methodology": {
                "equity_bond_spread": "指数盈利收益率（1/滚动市盈率）减中国10年期国债到期收益率",
                "buffett_indicator": "官网可用期使用沪深北三所全部A股总市值；早期总市值按重叠期中位比例桥接官网口径，再除以同期参考名义GDP",
                "deposit_market_cap_ratio": "人民币住户存款余额 / A股总市值；官网可用期优先，早期使用已校准的长期总市值序列",
            },
        }

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
