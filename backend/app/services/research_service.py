import json
import math
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[3]
VIX_OPTION_REPORT_PATH = REPO_ROOT / "runtime" / "reports" / "vix_option_analysis" / "report.json"
CSI1000_FUTURES_REPORT_PATH = (
    REPO_ROOT / "runtime" / "reports" / "csi1000_futures_analysis" / "report.json"
)
ASHARE_OUTLOOK_REPORT_PATH = REPO_ROOT / "docs" / "research" / "ashare_outlook_2026-10-04.json"


class ResearchService:
    def __init__(self, db: Session | None = None):
        self.db = db

    def get_ashare_outlook(self) -> dict:
        if not ASHARE_OUTLOOK_REPORT_PATH.exists():
            raise FileNotFoundError("A股市场展望研究尚未生成")
        try:
            payload = json.loads(ASHARE_OUTLOOK_REPORT_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("A股市场展望研究读取失败") from exc
        try:
            if (not isinstance(payload, dict) or payload.get("research_only") is not True
                    or payload.get("live") is not False):
                raise ValueError("Invalid report purpose")
            cutoff = datetime.fromisoformat(payload["as_of_at"])
            if cutoff.tzinfo is None or not payload["indexes"] or not payload["sections"]:
                raise ValueError("Missing dated evidence")
            if payload["market_date"] > cutoff.date().isoformat():
                raise ValueError("Future market date")
            financing = payload.get("financing")
            if financing and financing.get("availability_policy") == "previous_cn_trade_date":
                if financing["reference_trade_date"] != payload["market_date"]:
                    raise ValueError("Financing reference date mismatch")
                if financing["source_date"] and financing["source_date"] >= financing["reference_trade_date"]:
                    raise ValueError("Financing must use T-1 or earlier")
                if financing["available_at"] and datetime.fromisoformat(financing["available_at"]) > cutoff.replace(tzinfo=None):
                    raise ValueError("Unreleased financing evidence")
            source_ids = {source["id"] for source in payload["sources"]}
            for section in payload["sections"]:
                for paragraph in section["paragraphs"]:
                    if not set(paragraph["sources"]).issubset(source_ids):
                        raise ValueError("Unknown source reference")
                for table in section.get("tables", []):
                    if not table["columns"] or not all(isinstance(c, str) for c in table["columns"]):
                        raise ValueError("Invalid evidence columns")
                    if any(len(row) != len(table["columns"]) or not all(isinstance(cell, str) for cell in row)
                           for row in table["rows"]):
                        raise ValueError("Invalid evidence cells")
            for index in payload["indexes"]:
                if index["source_date"] > payload["market_date"]:
                    raise ValueError("Future index date")
                if any(c["date"] > index["source_date"] for c in index["candles"]):
                    raise ValueError("Future chart data")
            history = payload.get("history_comparison")
            if history:
                if history["as_of_at"] != payload["as_of_at"].removesuffix("+08:00"):
                    raise ValueError("Historical evidence cutoff mismatch")
                if any(p["date"] > payload["market_date"] for path in history["spring_2021"]["paths"] for p in path["points"]):
                    raise ValueError("Future historical chart data")
                if any(c["end"] > payload["market_date"] for c in history["cases"]):
                    raise ValueError("Future case endpoint")
            extensions = payload.get("extensions")
            if extensions:
                if extensions["as_of_at"] != payload["as_of_at"].removesuffix("+08:00"):
                    raise ValueError("Extension evidence cutoff mismatch")
                if extensions["market_date"] != payload["market_date"]:
                    raise ValueError("Extension market date mismatch")
                if any(r["date"] > payload["market_date"] for r in extensions["proxy_metrics"]):
                    raise ValueError("Future proxy evidence")
                if any(r["available_at"] > extensions["as_of_at"] for r in extensions["monthly"]):
                    raise ValueError("Unreleased monthly evidence")
            supplement = payload.get("supplement")
            if supplement:
                if (supplement["as_of_at"] != payload["as_of_at"].removesuffix("+08:00")
                        or supplement["market_date"] != payload["market_date"]
                        or supplement["research_only"] is not True):
                    raise ValueError("Supplement cutoff mismatch")
                if any(r["date"] > payload["market_date"] for r in supplement["etf"]):
                    raise ValueError("Future ETF evidence")
                if (supplement["ah"]["market_day"]["date"] > payload["market_date"]
                        or supplement["ah"]["latest"]["date"] > cutoff.date().isoformat()):
                    raise ValueError("Future AH evidence")
                if supplement["worldbank"]["published_date"] >= cutoff.date().isoformat():
                    raise ValueError("Unreleased date-only commodity evidence")
                if any(r["published_at"] > supplement["as_of_at"] for r in supplement["policy_monthly"]):
                    raise ValueError("Unreleased policy evidence")
                if any(r["retrieved_at"] > supplement["as_of_at"]
                       or r["available_at"] > supplement["as_of_at"]
                       or r["source_date"] > cutoff.date().isoformat()
                       for r in supplement.get("global_refresh", [])):
                    raise ValueError("Future global refresh evidence")
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("A股市场展望研究格式无效") from exc
        return payload

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
