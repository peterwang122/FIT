import hashlib
import hmac
import json
import re
import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Iterable

import requests
from pypinyin import Style, lazy_pinyin
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.quant_strategy_config import QuantStrategyConfig
from app.models.scheduled_task import ScheduledTask
from app.models.scheduled_task_run import ScheduledTaskRun
from app.models.user import User
from app.services.quant_service import QuantService
from app.services.stock_service import CITIC_CUSTOMER_MEMBER_NAME, StockService


DISPLAY_KEY_BY_INDEX_NAME = {
    "上证50": "50",
    "沪深300": "300",
    "中证500": "500",
    "中证1000": "1000",
}
SERIES_KEY_BY_INDEX_NAME = {
    name: f"series_{display_key}" for name, display_key in DISPLAY_KEY_BY_INDEX_NAME.items()
}
RISK_CODE_TO_SCORE_KEY = {
    "sh000300": "score_300",
    "sh000852": "score_1000",
}
EFFECTIVE_SIGNAL_TEXTS = {"蓝", "红", "紫"}
SAFE_INDEX_ALIAS_BY_CODE = {
    "sh000016": "50",
    "sh000300": "300",
    "sh000905": "500",
    "sh000852": "1000",
    "sh000688": "K50",
}
TABLE_PRODUCT_ORDER = (("IH", "上证50"), ("IF", "沪深300"), ("IC", "中证500"), ("IM", "中证1000"))
SOURCE_VERSION = "1"


def _quoted_identifier(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized or not normalized.replace("_", "").isalnum():
        raise ValueError(f"unsafe SQL identifier: {value}")
    return f"`{normalized}`"


def _date_text(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")[:10]


def _number(value: object) -> float | None:
    return None if value is None else float(value)


def _content_hash(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_letters(value: object, length: int = 3) -> str:
    digest = hashlib.sha256(str(value or "unknown").encode("utf-8")).digest()
    return "".join(chr(ord("A") + byte % 26) for byte in digest[:length])


def _stock_initials(name: object, fallback: object) -> str:
    letters = "".join(
        lazy_pinyin(str(name or ""), style=Style.FIRST_LETTER, errors="ignore")
    ).upper()
    letters = re.sub(r"[^A-Z]", "", letters)
    return letters[:12] if len(letters) >= 2 else _stable_letters(fallback, 4)


def _safe_target_alias(config: QuantStrategyConfig | None, summary: dict) -> str:
    target_code = str(getattr(config, "target_code", "") or "").strip().lower()
    target_name = str(getattr(config, "target_name", "") or summary.get("target_name") or "")
    strategy_type = str(getattr(config, "strategy_type", "") or "").strip().lower()
    if strategy_type == "index":
        if target_name in DISPLAY_KEY_BY_INDEX_NAME:
            return DISPLAY_KEY_BY_INDEX_NAME[target_name]
        if target_code in SAFE_INDEX_ALIAS_BY_CODE:
            return SAFE_INDEX_ALIAS_BY_CODE[target_code]
        return f"指数{_stable_letters(target_code or target_name)}"
    return _stock_initials(target_name, target_code or summary.get("strategy_id"))


def _safe_strategy_name(
    config: QuantStrategyConfig | None,
    summary: dict,
    target_aliases: dict[str, str],
) -> str:
    name = str(getattr(config, "name", "") or summary.get("strategy_name") or "").strip()
    for source_name, alias in sorted(target_aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if source_name:
            name = name.replace(source_name, alias)
    for source_name, alias in {
        **DISPLAY_KEY_BY_INDEX_NAME,
        "科创50": "K50",
        "全高点覆盖": "全区间覆盖",
        "期现": "联动",
        "买入": "阶段",
        "卖出": "调整",
        "多空": "方向",
        "期货": "样本",
        "股票": "对象",
        "风险": "条件",
        "策略": "方案",
    }.items():
        name = name.replace(source_name, alias)
    name = re.sub(r"\b(?:IH|IF|IC|IM)\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\d{6}", "", name)
    name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "", name)
    return name[:24] or f"{_safe_target_alias(config, summary)}方案"


def _safe_notification_result(summary: dict) -> tuple[str, str]:
    signal_text = str(summary.get("signal_text") or "").strip()
    if summary.get("is_risk"):
        if summary.get("risk_state") is True:
            return "条件命中", "当日条件满足"
        if summary.get("risk_state") is False:
            return "条件未命中", "当日条件未满足"
        return "数据不完整", "数据尚不完整"
    if signal_text in EFFECTIVE_SIGNAL_TEXTS:
        return signal_text, "当日出现有效结果"
    if signal_text == "数据不完整":
        return "数据不完整", "数据尚不完整"
    return "无结果", "当日无有效结果"


def _chunked(items: list[dict], size: int) -> Iterable[list[dict]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


class WechatMiniappSyncService:
    def __init__(self, db: Session, http_session=requests):
        self.db = db
        self.http = http_session

    @property
    def enabled(self) -> bool:
        return bool(
            settings.wechat_miniapp_sync_enabled
            and settings.wechat_miniapp_ingest_url.strip()
            and settings.wechat_miniapp_ingest_secret.strip()
        )

    def _start_date(self, full: bool) -> date | None:
        if full:
            return None
        days = max(int(settings.wechat_miniapp_sync_lookback_days), 1)
        return date.today() - timedelta(days=days)

    def build_series_records(self, start_date: date | None = None) -> list[dict]:
        table_name = _quoted_identifier(settings.excel_index_emotion_table_name)
        date_column = _quoted_identifier(settings.excel_index_emotion_date_column)
        name_column = _quoted_identifier(settings.excel_index_emotion_name_column)
        value_column = _quoted_identifier(settings.excel_index_emotion_value_column)
        where_date = f"AND {date_column} >= :start_date" if start_date else ""
        rows = self.db.execute(
            text(
                f"SELECT {date_column} AS item_date, {name_column} AS item_name, "
                f"{value_column} AS item_value FROM {table_name} "
                f"WHERE {name_column} IN ('上证50','沪深300','中证500','中证1000') "
                f"{where_date} ORDER BY {date_column} ASC"
            ),
            {"start_date": start_date} if start_date else {},
        ).mappings().all()
        grouped: dict[str, dict[str, float | None]] = defaultdict(dict)
        for row in rows:
            key = SERIES_KEY_BY_INDEX_NAME.get(str(row["item_name"]).strip())
            item_date = _date_text(row["item_date"])
            if key and item_date:
                grouped[item_date][key] = _number(row["item_value"])
        records = []
        for item_date, values in grouped.items():
            payload = {"date": item_date, "values": values}
            records.append(
                {
                    "_id": f"series_{item_date.replace('-', '')}",
                    **payload,
                    "content_hash": _content_hash(payload),
                }
            )
        return records

    def _table_position_rows(self, start_date: date | None) -> list[dict]:
        table_name = _quoted_identifier(settings.cffex_member_rankings_table_name)
        date_column = _quoted_identifier(settings.cffex_trade_date_column)
        product_column = _quoted_identifier(settings.cffex_product_code_column)
        short_member_column = _quoted_identifier(settings.cffex_short_member_column)
        long_member_column = _quoted_identifier(settings.cffex_long_member_column)
        short_change_column = _quoted_identifier(settings.cffex_short_change_value_column)
        long_change_column = _quoted_identifier(settings.cffex_long_change_value_column)
        rank_column = _quoted_identifier(settings.cffex_rank_no_column)
        volume_member_column = _quoted_identifier(settings.cffex_volume_member_column)
        stock_service = StockService(self.db)
        short_member_match = stock_service._member_match_sql(
            settings.cffex_short_member_column,
            date_column,
            CITIC_CUSTOMER_MEMBER_NAME,
        )
        long_member_match = stock_service._member_match_sql(
            settings.cffex_long_member_column,
            date_column,
            CITIC_CUSTOMER_MEMBER_NAME,
        )
        where_date = f"AND {date_column} >= :start_date" if start_date else ""
        rows = self.db.execute(
            text(
                f"SELECT {date_column} AS item_date, {product_column} AS product_code, "
                f"SUM(CASE WHEN {short_member_match} THEN COALESCE({short_change_column}, 0) ELSE 0 END) AS zx_short, "
                f"SUM(CASE WHEN {long_member_match} THEN COALESCE({long_change_column}, 0) ELSE 0 END) AS zx_long, "
                f"SUM(CASE WHEN {rank_column} <= 20 AND {volume_member_column} IS NOT NULL "
                f"THEN COALESCE({short_change_column}, 0) ELSE 0 END) AS aggregate_short, "
                f"SUM(CASE WHEN {rank_column} <= 20 AND {volume_member_column} IS NOT NULL "
                f"THEN COALESCE({long_change_column}, 0) ELSE 0 END) AS aggregate_long "
                f"FROM {table_name} "
                f"WHERE {product_column} IN ('IH','IF','IC','IM') {where_date} "
                f"GROUP BY {date_column}, {product_column} "
                f"ORDER BY {date_column} ASC, FIELD({product_column}, 'IH','IF','IC','IM')"
            ),
            {
                **stock_service._member_match_params(CITIC_CUSTOMER_MEMBER_NAME),
                **({"start_date": start_date} if start_date else {}),
            },
        ).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    def _position_text(value: int) -> str:
        if value > 0:
            return f"空{abs(value):,}手"
        if value < 0:
            return f"多{abs(value):,}手"
        return "持平"

    @staticmethod
    def _position_action(value: int) -> str:
        if value > 0:
            return "加仓"
        if value < 0:
            return "减仓"
        return "持平"

    @staticmethod
    def _table_sample(source: dict, label: str) -> dict:
        rows = []
        for row in source.get("rows", []):
            display_key = DISPLAY_KEY_BY_INDEX_NAME.get(str(row.get("index_name") or ""))
            if not display_key:
                continue
            rows.append(
                {
                    "group": display_key,
                    "short_value": int(row.get("short_position") or 0),
                    "long_value": int(row.get("long_position") or 0),
                    "net_value": int(row.get("net_position") or 0),
                    "net_text": str(row.get("net_position_text") or "持平"),
                    "action": str(row.get("action") or "持平"),
                }
            )
        return {
            "label": label,
            "total_value": int(source.get("total_net_position") or 0),
            "total_text": str(source.get("total_net_position_text") or "持平"),
            "rows": rows,
        }

    def build_table_records(self, start_date: date | None = None) -> list[dict]:
        grouped: dict[str, dict[str, dict]] = defaultdict(dict)
        for row in self._table_position_rows(start_date):
            grouped[_date_text(row["item_date"])][str(row["product_code"])] = row
        records = []
        for date_value, rows_by_product in grouped.items():
            if any(product_code not in rows_by_product for product_code, _ in TABLE_PRODUCT_ORDER):
                continue

            def build_source(short_key: str, long_key: str) -> dict:
                rows = []
                total = 0
                for product_code, index_name in TABLE_PRODUCT_ORDER:
                    row = rows_by_product[product_code]
                    short_value = int(round(float(row.get(short_key) or 0)))
                    long_value = int(round(float(row.get(long_key) or 0)))
                    net_value = short_value - long_value
                    total += net_value
                    rows.append(
                        {
                            "index_name": index_name,
                            "short_position": short_value,
                            "long_position": long_value,
                            "net_position": net_value,
                            "net_position_text": self._position_text(net_value),
                            "action": self._position_action(net_value),
                        }
                    )
                return {
                    "total_net_position": total,
                    "total_net_position_text": self._position_text(total),
                    "rows": rows,
                }

            payload = {
                "date": date_value,
                "samples": {
                    "sample_zx": self._table_sample(build_source("zx_short", "zx_long"), "ZX样本"),
                    "sample_aggregate": self._table_sample(
                        build_source("aggregate_short", "aggregate_long"),
                        "综合样本",
                    ),
                },
            }
            records.append(
                {
                    "_id": f"table_{date_value.replace('-', '')}",
                    **payload,
                    "content_hash": _content_hash(payload),
                }
            )
        return records

    def build_score_records(self, start_date: date | None = None) -> list[dict]:
        table_name = _quoted_identifier(settings.quant_index_dashboard_table_name)
        date_column = _quoted_identifier(settings.quant_index_dashboard_date_column)
        code_column = _quoted_identifier(settings.quant_index_dashboard_code_column)
        where_date = f"AND {date_column} >= :start_date" if start_date else ""
        rows = self.db.execute(
            text(
                f"SELECT {date_column} AS item_date, {code_column} AS item_code, "
                f"risk_overall_score, risk_global_shock_score FROM {table_name} "
                f"WHERE {code_column} IN ('sh000300','sh000852') {where_date} "
                f"AND (risk_overall_score IS NOT NULL OR risk_global_shock_score IS NOT NULL) "
                f"ORDER BY {date_column} ASC"
            ),
            {"start_date": start_date} if start_date else {},
        ).mappings().all()
        grouped: dict[str, dict[str, dict]] = defaultdict(dict)
        for row in rows:
            grouped[_date_text(row["item_date"])][str(row["item_code"])] = dict(row)
        records = []
        for item_date, by_code in grouped.items():
            item_300 = by_code.get("sh000300", {})
            item_1000 = by_code.get("sh000852", {})
            global_300 = _number(item_300.get("risk_global_shock_score"))
            global_1000 = _number(item_1000.get("risk_global_shock_score"))
            values = {
                "score_300": _number(item_300.get("risk_overall_score")),
                "score_1000": _number(item_1000.get("risk_overall_score")),
                "score_global": global_1000,
            }
            consistent = global_300 is None or global_1000 is None or abs(global_300 - global_1000) < 0.000001
            payload = {"date": item_date, "values": values, "quality": {"global_consistent": consistent}}
            records.append(
                {
                    "_id": f"score_{item_date.replace('-', '')}",
                    **payload,
                    "content_hash": _content_hash(payload),
                }
            )
        return records

    def build_notification_event(self) -> dict | None:
        root = self.db.query(User).filter(User.role == "root").order_by(User.id.asc()).first()
        if root is None:
            return None
        task = (
            self.db.query(ScheduledTask)
            .filter(
                ScheduledTask.owner_user_id == root.id,
                ScheduledTask.task_type == "notification",
                ScheduledTask.name == settings.wechat_miniapp_notification_task_name,
            )
            .order_by(ScheduledTask.id.asc())
            .first()
        )
        if task is None or not task.enabled:
            return None
        run = (
            self.db.query(ScheduledTaskRun)
            .filter(
                ScheduledTaskRun.scheduled_task_id == task.id,
                ScheduledTaskRun.trigger_type.in_(("schedule", "manual")),
                ScheduledTaskRun.status == "success",
            )
            .order_by(ScheduledTaskRun.scheduled_for.desc(), ScheduledTaskRun.id.desc())
            .first()
        )
        if run is None or run.scheduled_for.date() < date.today() - timedelta(days=7):
            return None
        basis_match = re.search(r"based on trade date (\d{4}-\d{2}-\d{2})", run.summary or "")
        basis_trade_date = (
            date.fromisoformat(basis_match.group(1))
            if basis_match
            else run.scheduled_for.date()
        )
        strategy_ids = [
            int(value)
            for value in (task.config_json or {}).get("strategy_ids", [])
            if isinstance(value, int) or str(value).isdigit()
        ]
        summaries = QuantService(self.db).list_strategy_notification_summaries(
            strategy_ids,
            root.id,
            basis_trade_date=basis_trade_date,
        )
        strategy_rows = (
            self.db.query(QuantStrategyConfig)
            .filter(
                QuantStrategyConfig.owner_user_id == root.id,
                QuantStrategyConfig.id.in_(strategy_ids),
            )
            .all()
        )
        strategy_map = {item.id: item for item in strategy_rows}
        target_aliases = {
            str(item.target_name or "").strip(): _safe_target_alias(item, {})
            for item in strategy_rows
            if str(item.target_name or "").strip()
        }
        safe_items = []
        for item in summaries:
            result, description = _safe_notification_result(item)
            config = strategy_map.get(int(item.get("strategy_id") or 0))
            safe_items.append(
                {
                    "name": _safe_strategy_name(config, item, target_aliases),
                    "target": _safe_target_alias(config, item),
                    "latest_date": _date_text(item.get("latest_trade_date")) or "-",
                    "result": result,
                    "description": description,
                }
            )
        effective_aliases = [
            safe_items[index]["name"]
            for index, item in enumerate(summaries)
            if str(item.get("signal_text") or "") in EFFECTIVE_SIGNAL_TEXTS
        ]
        if effective_aliases:
            prefix = f"今日有效项目{len(effective_aliases)}项"
            detail = "、".join(effective_aliases[:2]) + ("等" if len(effective_aliases) > 2 else "")
            summary = f"{prefix}：{detail}"[:20]
        else:
            summary = "今日无有效项目"
        event_id = f"event_{task.id}_{run.id}"
        payload = {
            "date": run.scheduled_for.date().isoformat(),
            "event_id": event_id,
            "basis_date": basis_trade_date.isoformat(),
            "completed_at": (run.finished_at or run.scheduled_for).isoformat(),
            "summary": summary,
            "total_count": len(summaries),
            "effective_count": len(effective_aliases),
            "mail": {
                "title": "每日数据结果",
                "sent_date": run.scheduled_for.date().isoformat(),
                "basis_date": basis_trade_date.isoformat(),
                "items": safe_items,
                "summary": (
                    f"本次汇总共 {len(summaries)} 个项目，其中 "
                    f"{len(effective_aliases)} 个出现有效结果。"
                ),
            },
        }
        return {"_id": event_id, **payload, "content_hash": _content_hash(payload)}

    def _signed_headers(self, body: str) -> dict[str, str]:
        timestamp = str(int(datetime.now().timestamp()))
        nonce = secrets.token_hex(16)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        canonical = f"{timestamp}\n{nonce}\n{digest}"
        signature = hmac.new(
            settings.wechat_miniapp_ingest_secret.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-FIT-Timestamp": timestamp,
            "X-FIT-Nonce": nonce,
            "X-FIT-Signature": signature,
        }

    def push(self, dataset: str, items: list[dict]) -> dict:
        if not items:
            return {"dataset": dataset, "written": 0, "batches": 0}
        total = 0
        batches = 0
        delivery = None
        batch_size = min(max(int(settings.wechat_miniapp_sync_batch_size), 1), 100)
        for chunk in _chunked(items, batch_size):
            body = json.dumps(
                {"dataset": dataset, "items": chunk, "source_version": SOURCE_VERSION},
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
            response = self.http.post(
                settings.wechat_miniapp_ingest_url,
                data=body.encode("utf-8"),
                headers=self._signed_headers(body),
                timeout=settings.wechat_miniapp_request_timeout_seconds,
            )
            response.raise_for_status()
            response_payload = response.json()
            if isinstance(response_payload, dict) and isinstance(response_payload.get("body"), str):
                response_payload = json.loads(response_payload["body"])
            if response_payload.get("ok") is not True:
                raise RuntimeError(str(response_payload.get("error") or "cloud ingestion failed"))
            response_data = response_payload.get("data") or {}
            total += int(response_data.get("written") or len(chunk))
            if response_data.get("delivery") is not None:
                delivery = response_data["delivery"]
            batches += 1
        report = {"dataset": dataset, "written": total, "batches": batches}
        if delivery is not None:
            report["delivery"] = delivery
        return report

    def sync(self, *, full: bool = False, include_notification: bool = True) -> dict:
        if not self.enabled:
            return {"status": "disabled"}
        start_date = self._start_date(full)
        reports = [
            self.push("table", self.build_table_records(start_date)),
            self.push("series", self.build_series_records(start_date)),
            self.push("score", self.build_score_records(start_date)),
        ]
        if include_notification:
            event = self.build_notification_event()
            if event:
                reports.append(self.push("notification_event", [event]))
        return {"status": "success", "full": full, "reports": reports}

    def sync_notification(self) -> dict:
        if not self.enabled:
            return {"status": "disabled"}
        event = self.build_notification_event()
        if event is None:
            return {"status": "no_event"}
        return {
            "status": "success",
            "report": self.push("notification_event", [event]),
        }
