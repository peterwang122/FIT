import json
import math
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[3]
VIX_OPTION_REPORT_PATH = REPO_ROOT / "runtime" / "reports" / "vix_option_analysis" / "report.json"
CSI1000_FUTURES_REPORT_PATH = (
    REPO_ROOT / "runtime" / "reports" / "csi1000_futures_analysis" / "report.json"
)


class ResearchService:
    def __init__(self, db: Session | None = None):
        self.db = db

    def get_vix_option_analysis(self) -> dict:
        if not VIX_OPTION_REPORT_PATH.exists():
            raise FileNotFoundError("VIX期权研究报告尚未生成")
        try:
            payload = json.loads(VIX_OPTION_REPORT_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("VIX期权研究报告读取失败") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("index_summaries"), list):
            raise RuntimeError("VIX期权研究报告格式无效")
        return payload

    def get_csi1000_futures_analysis(self) -> dict:
        if not CSI1000_FUTURES_REPORT_PATH.exists():
            raise FileNotFoundError("中证1000股指期货研究报告尚未生成")
        try:
            payload = json.loads(CSI1000_FUTURES_REPORT_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("中证1000股指期货研究报告读取失败") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("waves"), list):
            raise RuntimeError("中证1000股指期货研究报告格式无效")
        return payload

    def get_option_contract_candles(self, exchange: str, contract_code: str) -> dict:
        exchange = exchange.strip().upper()
        contract_code = contract_code.strip()
        if exchange not in {"CFFEX", "SSE", "SZSE"}:
            raise ValueError("不支持的期权交易所")
        if not contract_code:
            raise ValueError("期权合约代码不能为空")
        if self.db is None:
            raise RuntimeError("数据库会话不可用")

        if exchange == "CFFEX":
            statement = text(
                """
                SELECT trade_date, open_price, high_price, low_price, close_price,
                       volume, turnover, open_interest
                FROM option_cffex_rtj_daily_data
                WHERE contract_code = :contract_code
                ORDER BY trade_date
                """
            )
            params = {"contract_code": contract_code}
        else:
            statement = text(
                """
                SELECT trade_date, open_price, high_price, low_price, close_price,
                       volume, turnover, open_interest, underlying_code
                FROM option_exchange_contract_daily_data
                WHERE exchange = :exchange AND contract_code = :contract_code
                ORDER BY trade_date
                """
            )
            params = {"exchange": exchange, "contract_code": contract_code}

        rows = self.db.execute(statement, params).mappings().all()
        candles: list[dict] = []
        underlying_code = None
        for row in rows:
            values = {
                key: self._finite_float(row.get(key))
                for key in ("open_price", "high_price", "low_price", "close_price")
            }
            if any(value is None or value <= 0 for value in values.values()):
                continue
            if values["high_price"] < max(values["open_price"], values["close_price"]):
                continue
            if values["low_price"] > min(values["open_price"], values["close_price"]):
                continue
            if underlying_code is None:
                underlying_code = row.get("underlying_code")
            candles.append(
                {
                    "trade_date": row["trade_date"].isoformat(),
                    "open": values["open_price"],
                    "high": values["high_price"],
                    "low": values["low_price"],
                    "close": values["close_price"],
                    "volume": self._finite_float(row.get("volume")),
                    "turnover": self._finite_float(row.get("turnover")),
                    "open_interest": self._finite_float(row.get("open_interest")),
                }
            )

        if not candles:
            raise FileNotFoundError(f"未找到期权合约 {contract_code} 的有效K线")
        return {
            "exchange": exchange,
            "contract_code": contract_code,
            "underlying_code": underlying_code,
            "candles": candles,
        }

    @staticmethod
    def _finite_float(value) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None
