import re
import smtplib
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.quant_strategy_config import QuantStrategyConfig
from app.models.scheduled_task import ScheduledTask
from app.models.scheduled_task_run import ScheduledTaskRun
from app.models.user import User
from app.services.market_calendar_service import DEFAULT_MARKET_SCOPE, MarketCalendarService
from app.services.notification_service import NotificationService
from app.services.quant_service import QuantService
from app.services.stock_service import StockService
from app.tasks.collector import run_daily_collection_request, run_index_daily_collection_request, run_stock_hfq_collection_request

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
SCHEDULE_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
HK_INDEX_ALL_CODE = "ALL_HK_INDEX"
US_INDEX_ALL_CODE = "ALL_US_INDEX"
HK_INDEX_ALL_NAME = "港股指数全市场"
US_INDEX_ALL_NAME = "美股指数全市场"
DOUYIN_POLL_TERMINAL_SUMMARY_PREFIX = "已发现当天新作品"


class TaskRunSkipped(RuntimeError):
    pass


class TaskRunTerminalFailure(RuntimeError):
    pass


class TaskRunRetryableFailure(RuntimeError):
    pass


class TaskRunPollingPending(RuntimeError):
    def __init__(self, message: str, countdown_seconds: int = 60):
        super().__init__(message)
        self.countdown_seconds = max(1, int(countdown_seconds))


COLLECTION_TASK_DEFINITIONS: dict[str, dict[str, str | bool | int | None]] = {
    "stock_hfq_single": {
        "label": "A股股票单只 HFQ 采集",
        "market_scope": "cn_stock",
        "target_type": "stock",
        "requires_target": True,
        "endpoint": "/collect",
    },
    "stock_daily": {
        "label": "股票日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-stock-daily",
    },
    "stock_exchange_official_daily": {
        "label": "沪深官网股票日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-stock-exchange-official-daily",
    },
    "index_cn_daily": {
        "label": "A股指数日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-cn-daily",
    },
    "index_bj50_daily": {
        "label": "北证50日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-bj50-daily",
    },
    "cffex_daily": {
        "label": "中金所会员持仓日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-cffex-daily",
    },
    "forex_daily": {
        "label": "汇率日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-forex-daily",
    },
    "usd_index_daily": {
        "label": "美元指数日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-usd-index-daily",
    },
    "futures_daily": {
        "label": "中金所期货日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-futures-daily",
    },
    "etf_daily": {
        "label": "ETF 日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-etf-daily",
    },
    "option_daily": {
        "label": "中金所期权日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-option-daily",
    },
    "exchange_option_daily": {
        "label": "沪深交易所期权行情日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-exchange-option-daily",
    },
    "exchange_option_stats_daily": {
        "label": "沪深交易所期权官方统计补齐",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-exchange-option-stats-daily",
    },
    "option_minute_daily": {
        "label": "期权分钟行情采集",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-option-minute-daily",
    },
    "cn_risk_free_rate_daily": {
        "label": "人民币无风险利率日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-cn-risk-free-rate-daily",
    },
    "cn_macro_daily": {
        "label": "A股宏观指标日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-cn-macro-daily",
    },
    "margin_trading_daily": {
        "label": "A股融资融券日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-margin-trading-daily",
        "poll_end_time": "09:35",
        "poll_interval_minutes": 1,
        "poll_inside_run": True,
    },
    "fund_purchase_limit_daily": {
        "label": "A股公募基金限购日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-fund-purchase-limit-daily",
    },
    "quant_index_daily": {
        "label": "量化指数看板日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-quant-index-daily",
    },
    "index_hk_daily": {
        "label": "港股指数日更",
        "market_scope": "hk_index",
        "target_type": "index",
        "requires_target": False,
        "endpoint": "/collect-index-hk-daily",
    },
    "index_us_daily": {
        "label": "美股指数日更",
        "market_scope": "us_index",
        "target_type": "index",
        "requires_target": False,
        "endpoint": "/collect-index-us-daily",
        "accept_previous_trading_day": True,
    },
    "hk_index_futures_daily": {
        "label": "港股股指期货日更",
        "market_scope": "hk_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-hk-index-futures-daily",
        "poll_end_time": "23:30",
        "poll_interval_minutes": 5,
        "poll_inside_run": True,
    },
    "us_index_futures_daily": {
        "label": "美股股指期货日更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-us-index-futures-daily",
        "accept_previous_trading_day": True,
    },
    "us_index_futures_official_daily": {
        "label": "美股股指期货官方合约日更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-us-index-futures-official-daily",
        "validation_trading_day_lag": 1,
    },
    "index_qvix_daily": {
        "label": "QVIX 日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-qvix-daily",
    },
    "index_news_sentiment_daily": {
        "label": "新闻情绪日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-news-sentiment-daily",
    },
    "index_cn_market_fear_greed_daily": {
        "label": "A股大盘恐贪指数日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-cn-market-fear-greed-daily",
    },
    "index_cn_baifenwei_fear_greed_daily": {
        "label": "百分位A股恐贪指数日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-cn-baifenwei-fear-greed-daily",
    },
    "excel_emotion_import": {
        "label": "情绪指标 Excel 导入",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/import-emotion-excel",
        "manual_only": True,
    },
    "douyin_coze_emotion_daily": {
        "label": "抖音四大指数情绪日更",
        "market_scope": "cn_stock",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-douyin-coze-emotion-daily",
        "calendar_daily": True,
        "poll_end_time": "21:00",
        "poll_interval_minutes": 1,
        "poll_inside_run": True,
    },
    "index_us_vix_daily": {
        "label": "美股 VIX 日更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-us-vix-daily",
        "accept_previous_trading_day": True,
    },
    "index_us_fear_greed_daily": {
        "label": "美股恐贪指数日更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-us-fear-greed-daily",
    },
    "index_us_hedge_proxy_daily": {
        "label": "OFR 美股持仓代理月更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-us-hedge-proxy-daily",
        "latest_release_max_age_days": 45,
    },
    "index_us_put_call_ratio_daily": {
        "label": "美股 Put/Call Ratio 日更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-us-put-call-ratio-daily",
        "accept_previous_trading_day": True,
    },
    "index_us_treasury_yield_daily": {
        "label": "美债收益率日更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-us-treasury-yield-daily",
        "validation_trading_day_lag": 1,
    },
    "index_us_credit_spread_daily": {
        "label": "美股高收益债利差日更",
        "market_scope": "us_index",
        "target_type": None,
        "requires_target": False,
        "endpoint": "/collect-index-us-credit-spread-daily",
        "validation_trading_day_lag": 1,
    },
}

COLLECTION_TASK_LABEL_OVERRIDES = {
    "stock_hfq_single": "A股股票单只 HFQ 采集",
    "stock_daily": "股票日更",
    "stock_exchange_official_daily": "沪深官网股票日更",
    "index_cn_daily": "A股指数日更",
    "index_bj50_daily": "北证50日更",
    "cffex_daily": "中金所会员持仓日更",
    "forex_daily": "汇率日更",
    "usd_index_daily": "美元指数日更",
    "futures_daily": "中金所期货日更",
    "etf_daily": "ETF 日更",
    "option_daily": "中金所期权日更",
    "exchange_option_daily": "沪深交易所期权行情日更",
    "exchange_option_stats_daily": "沪深交易所期权官方统计补齐",
    "option_minute_daily": "期权分钟行情采集",
    "cn_risk_free_rate_daily": "人民币无风险利率日更",
    "cn_macro_daily": "A股宏观指标日更",
    "margin_trading_daily": "A股融资融券日更",
    "quant_index_daily": "量化指数看板日更",
    "index_hk_daily": "港股指数日更",
    "index_us_daily": "美股指数日更",
    "hk_index_futures_daily": "港股股指期货日更",
    "us_index_futures_daily": "美股股指期货日更",
    "us_index_futures_official_daily": "美股股指期货官方合约日更",
    "index_qvix_daily": "QVIX 日更",
    "index_news_sentiment_daily": "新闻情绪日更",
    "index_cn_market_fear_greed_daily": "A股大盘恐贪指数日更",
    "index_cn_baifenwei_fear_greed_daily": "百分位A股恐贪指数日更",
    "excel_emotion_import": "情绪指标 Excel 导入",
    "douyin_coze_emotion_daily": "抖音四大指数情绪日更",
    "index_us_vix_daily": "美股 VIX 日更",
    "index_us_fear_greed_daily": "美股恐贪指数日更",
    "index_us_hedge_proxy_daily": "OFR 美股持仓代理月更",
    "index_us_put_call_ratio_daily": "美股 Put/Call Ratio 日更",
    "index_us_treasury_yield_daily": "美债收益率日更",
    "index_us_credit_spread_daily": "美股高收益债利差日更",
}
for _collector_key, _label in COLLECTION_TASK_LABEL_OVERRIDES.items():
    if _collector_key in COLLECTION_TASK_DEFINITIONS:
        COLLECTION_TASK_DEFINITIONS[_collector_key]["label"] = _label


@dataclass(frozen=True)
class CollectionDataProbe:
    table_name: str
    date_column: str
    label: str
    where_sql: str = ""
    params: dict[str, object] = field(default_factory=dict)
    minimum_rows: int = 1
    distinct_count_column: str | None = None
    warning_below_rows: int | None = None


def _quoted_identifier(value: str) -> str:
    return f"`{str(value).replace('`', '``')}`"


COLLECTION_VALIDATION_MARKET_SCOPE_OVERRIDES: dict[str, str] = {
    "forex_daily": "us_index",
    "usd_index_daily": "us_index",
}

COLLECTION_DATA_PROBES: dict[str, list[CollectionDataProbe]] = {
    "stock_daily": [
        CollectionDataProbe(settings.stock_table_name, settings.stock_date_column, "股票日线"),
    ],
    "stock_exchange_official_daily": [
        CollectionDataProbe(
            settings.stock_exchange_official_daily_table_name,
            settings.stock_exchange_official_daily_date_column,
            "上交所官网股票日线",
            where_sql="AND exchange = :exchange",
            params={"exchange": "SH"},
        ),
        CollectionDataProbe(
            settings.stock_exchange_official_daily_table_name,
            settings.stock_exchange_official_daily_date_column,
            "深交所官网股票日线",
            where_sql="AND exchange = :exchange",
            params={"exchange": "SZ"},
        ),
    ],
    "index_cn_daily": [
        CollectionDataProbe(settings.index_daily_table_name, settings.index_daily_date_column, "A股指数日线"),
        CollectionDataProbe(
            settings.index_daily_table_name,
            settings.index_daily_date_column,
            "中证红利指数日线",
            where_sql=f"AND {_quoted_identifier(settings.index_daily_code_column)} = :csi_dividend_code",
            params={"csi_dividend_code": "sh000922"},
        ),
    ],
    "index_bj50_daily": [
        CollectionDataProbe(
            settings.index_daily_table_name,
            settings.index_daily_date_column,
            "北证50指数日线",
            where_sql=f"AND {_quoted_identifier(settings.index_daily_code_column)} IN (:bj50_code, :bj50_prefixed_code)",
            params={"bj50_code": "899050", "bj50_prefixed_code": "BJ899050"},
        ),
    ],
    "cffex_daily": [
        CollectionDataProbe(
            settings.cffex_member_rankings_table_name,
            settings.cffex_trade_date_column,
            "中金所会员持仓-IF",
            where_sql=f"AND {_quoted_identifier(settings.cffex_product_code_column)} = :cffex_product_if",
            params={"cffex_product_if": "IF"},
            minimum_rows=20,
        ),
        CollectionDataProbe(
            settings.cffex_member_rankings_table_name,
            settings.cffex_trade_date_column,
            "中金所会员持仓-IH",
            where_sql=f"AND {_quoted_identifier(settings.cffex_product_code_column)} = :cffex_product_ih",
            params={"cffex_product_ih": "IH"},
            minimum_rows=20,
        ),
        CollectionDataProbe(
            settings.cffex_member_rankings_table_name,
            settings.cffex_trade_date_column,
            "中金所会员持仓-IC",
            where_sql=f"AND {_quoted_identifier(settings.cffex_product_code_column)} = :cffex_product_ic",
            params={"cffex_product_ic": "IC"},
            minimum_rows=20,
        ),
        CollectionDataProbe(
            settings.cffex_member_rankings_table_name,
            settings.cffex_trade_date_column,
            "中金所会员持仓-IM",
            where_sql=f"AND {_quoted_identifier(settings.cffex_product_code_column)} = :cffex_product_im",
            params={"cffex_product_im": "IM"},
            minimum_rows=20,
        ),
        CollectionDataProbe(
            settings.cffex_member_rankings_table_name,
            settings.cffex_trade_date_column,
            "中金所会员持仓-TS",
            where_sql=f"AND {_quoted_identifier(settings.cffex_product_code_column)} = :cffex_product_ts",
            params={"cffex_product_ts": "TS"},
            minimum_rows=20,
        ),
        CollectionDataProbe(
            settings.cffex_member_rankings_table_name,
            settings.cffex_trade_date_column,
            "中金所会员持仓-TF",
            where_sql=f"AND {_quoted_identifier(settings.cffex_product_code_column)} = :cffex_product_tf",
            params={"cffex_product_tf": "TF"},
            minimum_rows=20,
        ),
        CollectionDataProbe(
            settings.cffex_member_rankings_table_name,
            settings.cffex_trade_date_column,
            "中金所会员持仓-T",
            where_sql=f"AND {_quoted_identifier(settings.cffex_product_code_column)} = :cffex_product_t",
            params={"cffex_product_t": "T"},
            minimum_rows=20,
        ),
        CollectionDataProbe(
            settings.cffex_member_rankings_table_name,
            settings.cffex_trade_date_column,
            "中金所会员持仓-TL",
            where_sql=f"AND {_quoted_identifier(settings.cffex_product_code_column)} = :cffex_product_tl",
            params={"cffex_product_tl": "TL"},
            minimum_rows=20,
        ),
    ],
    "forex_daily": [
        CollectionDataProbe(settings.forex_daily_table_name, settings.forex_daily_date_column, "汇率日线"),
    ],
    "usd_index_daily": [
        CollectionDataProbe(
            settings.forex_daily_table_name,
            settings.forex_daily_date_column,
            "美元指数日线",
            where_sql=f"AND {_quoted_identifier(settings.forex_daily_code_column)} = :usd_index_code",
            params={"usd_index_code": "UDI"},
        ),
    ],
    "futures_daily": [
        CollectionDataProbe(
            settings.futures_daily_table_name,
            settings.futures_daily_trade_date_column,
            "中金所期货原始合约",
            where_sql=(
                f"AND ({_quoted_identifier(settings.futures_daily_data_source_column)} IS NULL "
                f"OR {_quoted_identifier(settings.futures_daily_data_source_column)} <> :derived_source)"
            ),
            params={"derived_source": settings.futures_daily_primary_source_value},
        ),
        CollectionDataProbe(
            settings.futures_daily_table_name,
            settings.futures_daily_trade_date_column,
            "中金所期货衍生合约",
            where_sql=f"AND {_quoted_identifier(settings.futures_daily_data_source_column)} = :derived_source",
            params={"derived_source": settings.futures_daily_primary_source_value},
        ),
    ],
    "etf_daily": [
        CollectionDataProbe(settings.etf_daily_table_name, settings.etf_daily_date_column, "ETF日线"),
    ],
    "option_daily": [
        CollectionDataProbe("option_cffex_rtj_daily_data", "trade_date", "中金所期权日线"),
    ],
    "exchange_option_daily": [
        CollectionDataProbe(
            "option_exchange_contract_daily_data",
            "trade_date",
            "上交所期权合约官方量额",
            where_sql=(
                "AND exchange = :exchange "
                "AND close_price IS NOT NULL "
                "AND volume IS NOT NULL "
                "AND turnover IS NOT NULL"
            ),
            params={"exchange": "SSE"},
        ),
        CollectionDataProbe(
            "option_exchange_contract_daily_data",
            "trade_date",
            "深交所期权合约官方量额",
            where_sql=(
                "AND exchange = :exchange "
                "AND close_price IS NOT NULL "
                "AND volume IS NOT NULL "
                "AND turnover IS NOT NULL"
            ),
            params={"exchange": "SZSE"},
        ),
    ],
    "exchange_option_stats_daily": [
        CollectionDataProbe(
            "option_exchange_daily_stats",
            "trade_date",
            "上交所期权产品",
            where_sql="AND exchange = :exchange",
            params={"exchange": "SSE"},
            minimum_rows=5,
        ),
        CollectionDataProbe(
            "option_exchange_daily_stats",
            "trade_date",
            "深交所期权产品",
            where_sql="AND exchange = :exchange",
            params={"exchange": "SZSE"},
            minimum_rows=4,
        ),
    ],
    "option_minute_daily": [
        *[
            CollectionDataProbe(
                "option_contract_minute_data",
                "trade_date",
                f"{source_key}原始分钟",
                where_sql="AND exchange = :exchange AND underlying_code = :underlying_code",
                params={
                    "exchange": source_key.split(":", 1)[0].upper(),
                    "underlying_code": source_key.split(":", 1)[1],
                },
                minimum_rows=220,
                distinct_count_column="bar_time",
            )
            for source_key in (
                "cffex:HO",
                "cffex:IO",
                "cffex:MO",
                "sse:510050",
                "sse:510300",
                "sse:510500",
                "sse:588000",
                "sse:588080",
                "szse:159919",
                "szse:159922",
            )
        ],
        *[
            CollectionDataProbe(
                "option_vix_minute_data",
                "trade_date",
                f"{source_key}分钟VIX",
                where_sql="AND source_key = :source_key",
                params={"source_key": source_key},
                minimum_rows=100,
                warning_below_rows=220,
            )
            for source_key in (
                "cffex:HO",
                "cffex:IO",
                "cffex:MO",
                "sse:510050",
                "sse:510300",
                "sse:510500",
                "sse:588000",
                "sse:588080",
                "szse:159919",
                "szse:159922",
            )
        ],
    ],
    "cn_risk_free_rate_daily": [
        CollectionDataProbe(
            "cn_risk_free_rate_daily",
            "trade_date",
            "人民币无风险利率曲线",
            minimum_rows=8,
        ),
    ],
    "cn_macro_daily": [
        CollectionDataProbe(
            "cn_macro_indicator_daily",
            "trade_date",
            "A股宏观指标",
            where_sql=(
                "AND hs300_equity_bond_spread_pp IS NOT NULL "
                "AND csi1000_equity_bond_spread_pp IS NOT NULL "
                "AND buffett_indicator_pct IS NOT NULL "
                "AND household_deposit_market_cap_ratio_pct IS NOT NULL"
            ),
        ),
    ],
    "margin_trading_daily": [
        CollectionDataProbe(
            "margin_trading_daily_data",
            "trade_date",
            "沪深北融资融券汇总",
            minimum_rows=3,
        ),
    ],
    "fund_purchase_limit_daily": [
        CollectionDataProbe(
            "fund_purchase_limit_daily_data",
            "trade_date",
            "A股权益类公募基金申购状态",
            minimum_rows=1000,
        ),
    ],
    "quant_index_daily": [
        CollectionDataProbe(
            settings.quant_index_dashboard_table_name,
            settings.quant_index_dashboard_date_column,
            "量化指数看板",
        ),
    ],
    "douyin_coze_emotion_daily": [
        CollectionDataProbe(
            settings.excel_index_emotion_table_name,
            settings.excel_index_emotion_date_column,
            "抖音四大指数情绪",
            where_sql=(
                f"AND {_quoted_identifier(settings.excel_index_emotion_name_column)} "
                "IN (:sz50_name, :hs300_name, :zz500_name, :zz1000_name)"
            ),
            params={
                "sz50_name": "上证50",
                "hs300_name": "沪深300",
                "zz500_name": "中证500",
                "zz1000_name": "中证1000",
            },
            minimum_rows=4,
        ),
    ],
    "index_hk_daily": [
        CollectionDataProbe(settings.index_hk_daily_table_name, settings.index_hk_daily_date_column, "港股指数日线"),
    ],
    "index_us_daily": [
        CollectionDataProbe(settings.index_us_daily_table_name, settings.index_us_daily_date_column, "美股指数日线"),
    ],
    "hk_index_futures_daily": [
        CollectionDataProbe(
            "futures_hk_index_daily_data",
            "trade_date",
            "港股股指期货",
            where_sql="AND root_symbol IN (:hsi_root, :hhi_root, :hti_root)",
            params={"hsi_root": "HSI", "hhi_root": "HHI", "hti_root": "HTI"},
            minimum_rows=3,
        ),
    ],
    "us_index_futures_daily": [
        CollectionDataProbe(
            "futures_us_index_daily_data",
            "trade_date",
            "美股股指期货",
            where_sql="AND root_symbol IN (:es_root, :nq_root)",
            params={"es_root": "ES", "nq_root": "NQ"},
            minimum_rows=2,
        ),
    ],
    "us_index_futures_official_daily": [
        CollectionDataProbe(
            "futures_us_index_official_daily_data",
            "trade_date",
            "美股股指期货官方合约",
            where_sql="AND root_symbol IN (:es_root, :nq_root)",
            params={"es_root": "ES", "nq_root": "NQ"},
            minimum_rows=2,
        ),
    ],
    "index_qvix_daily": [
        CollectionDataProbe(settings.index_qvix_daily_table_name, settings.index_qvix_daily_date_column, "QVIX"),
    ],
    "index_news_sentiment_daily": [
        CollectionDataProbe("index_news_sentiment_scope_daily", "trade_date", "新闻情绪"),
    ],
    "index_cn_market_fear_greed_daily": [
        CollectionDataProbe(
            "index_cn_market_fear_greed_daily",
            "trade_date",
            "A股大盘总体恐贪指数",
        ),
    ],
    "index_cn_baifenwei_fear_greed_daily": [
        CollectionDataProbe(
            "index_cn_baifenwei_fear_greed_daily",
            "trade_date",
            "百分位A股恐贪指数",
        ),
    ],
    "index_us_vix_daily": [
        CollectionDataProbe(settings.index_us_vix_daily_table_name, settings.index_us_vix_daily_date_column, "美股VIX"),
    ],
    "index_us_fear_greed_daily": [
        CollectionDataProbe(
            settings.index_us_fear_greed_daily_table_name,
            settings.index_us_fear_greed_daily_date_column,
            "美股恐贪指数",
        ),
    ],
    "index_us_hedge_proxy_daily": [
        CollectionDataProbe(
            settings.index_us_hedge_proxy_table_name,
            settings.index_us_hedge_proxy_release_date_column,
            "美股持仓代理",
        ),
    ],
    "index_us_put_call_ratio_daily": [
        CollectionDataProbe(
            settings.index_us_put_call_table_name,
            settings.index_us_put_call_date_column,
            "美股Put/Call Ratio",
        ),
    ],
    "index_us_treasury_yield_daily": [
        CollectionDataProbe(
            settings.index_us_treasury_yield_table_name,
            settings.index_us_treasury_yield_date_column,
            "美债收益率",
        ),
    ],
    "index_us_credit_spread_daily": [
        CollectionDataProbe(
            settings.index_us_credit_spread_table_name,
            settings.index_us_credit_spread_date_column,
            "美股高收益债利差",
        ),
    ],
}


class TaskService:
    def __init__(self, db: Session):
        self.db = db
        self.quant_service = QuantService(db)
        self.stock_service = StockService(db)
        self.market_calendar = MarketCalendarService()
        self.notification_service = NotificationService(db)

    def _get_collection_definition(self, collector_key: str | None) -> dict[str, str | bool | None]:
        normalized_key = str(collector_key or "").strip().lower()
        definition = COLLECTION_TASK_DEFINITIONS.get(normalized_key)
        if definition is None:
            raise ValueError("unsupported collection collector_key")
        return definition

    def _normalize_collector_key(
        self,
        collector_key: str | None,
        market_scope: str | None,
        target_type: str | None = None,
        target_code: str | None = None,
        target_name: str | None = None,
        task_name: str | None = None,
    ) -> str:
        normalized_key = str(collector_key or "").strip().lower()
        if normalized_key in COLLECTION_TASK_DEFINITIONS:
            return normalized_key

        normalized_scope = self._normalize_market_scope(market_scope)
        normalized_type = str(target_type or "").strip().lower()
        normalized_code = str(target_code or "").strip()
        legacy_inferred = self._infer_legacy_collector_key(
            market_scope=normalized_scope,
            target_type=normalized_type,
            target_code=normalized_code,
            target_name=target_name,
            task_name=task_name,
        )
        if legacy_inferred:
            return legacy_inferred
        if normalized_scope == "cn_stock" and (normalized_type == "stock" or normalized_code):
            return "stock_hfq_single"
        raise ValueError("collector_key is required for collection tasks")

    def _infer_legacy_collector_key(
        self,
        *,
        market_scope: str,
        target_type: str,
        target_code: str,
        target_name: str | None = None,
        task_name: str | None = None,
    ) -> str | None:
        normalized_name = " ".join(
            part.strip()
            for part in [task_name or "", target_name or "", target_code or ""]
            if str(part or "").strip()
        )
        lowered_name = normalized_name.lower()
        is_futures_task = "期货" in normalized_name or "futures" in lowered_name

        if "港股" in normalized_name:
            if is_futures_task:
                return "hk_index_futures_daily"
            return "index_hk_daily"

        if "美股" in normalized_name or "us " in lowered_name or "u.s." in lowered_name:
            if is_futures_task:
                return "us_index_futures_daily"
            if "put" in lowered_name or "call" in lowered_name:
                return "index_us_put_call_ratio_daily"
            if "treasury" in lowered_name or "yield" in lowered_name or "收益率" in normalized_name or "美债" in normalized_name:
                return "index_us_treasury_yield_daily"
            if "credit" in lowered_name or "spread" in lowered_name or "高收益债" in normalized_name or "利差" in normalized_name:
                return "index_us_credit_spread_daily"
            if "hedge" in lowered_name or "对冲" in normalized_name:
                return "index_us_hedge_proxy_daily"
            if "fear" in lowered_name or "greed" in lowered_name or "恐贪" in normalized_name:
                return "index_us_fear_greed_daily"
            if "vix" in lowered_name:
                return "index_us_vix_daily"
            if "指数" in normalized_name:
                return "index_us_daily"

        if market_scope == "hk_index":
            if is_futures_task:
                return "hk_index_futures_daily"
            return "index_hk_daily"

        if market_scope == "us_index":
            if is_futures_task:
                return "us_index_futures_daily"
            if "put" in lowered_name or "call" in lowered_name:
                return "index_us_put_call_ratio_daily"
            if "treasury" in lowered_name or "yield" in lowered_name or "收益率" in normalized_name or "美债" in normalized_name:
                return "index_us_treasury_yield_daily"
            if "credit" in lowered_name or "spread" in lowered_name or "高收益债" in normalized_name or "利差" in normalized_name:
                return "index_us_credit_spread_daily"
            if "hedge" in lowered_name or "对冲" in normalized_name:
                return "index_us_hedge_proxy_daily"
            if "fear" in lowered_name or "greed" in lowered_name or "恐贪" in normalized_name:
                return "index_us_fear_greed_daily"
            if "vix" in lowered_name:
                return "index_us_vix_daily"
            return "index_us_daily"

        if market_scope == "cn_stock":
            if "\u5317\u8bc1" in normalized_name or "899050" in lowered_name:
                return "index_bj50_daily"
            if "抖音" in normalized_name and "情绪" in normalized_name:
                return "douyin_coze_emotion_daily"
            if "qvix" in lowered_name:
                return "index_qvix_daily"
            if "新闻" in normalized_name or "情绪" in normalized_name:
                return "index_news_sentiment_daily"
            if "量化" in normalized_name and "看板" in normalized_name:
                return "quant_index_daily"
            if "期权" in normalized_name and "分钟" in normalized_name:
                return "option_minute_daily"
            if "期权" in normalized_name:
                return "option_daily"
            if "会员持仓" in normalized_name:
                return "cffex_daily"
            if "期货" in normalized_name:
                return "futures_daily"
            if "美元指数" in normalized_name or ("美元" in normalized_name and "指数" in normalized_name):
                return "usd_index_daily"
            if "汇率" in normalized_name or "forex" in lowered_name:
                return "forex_daily"
            if "etf" in lowered_name:
                return "etf_daily"
            if "股票日更" in normalized_name:
                return "stock_daily"
            if "指数日更" in normalized_name or "a股指数" in lowered_name:
                return "index_cn_daily"
            if target_type == "stock" or target_code:
                return "stock_hfq_single"
        return None

    def _collection_market_scope(self, collector_key: str) -> str:
        definition = self._get_collection_definition(collector_key)
        return self._normalize_market_scope(str(definition["market_scope"]))

    def _is_manual_only_collection(self, collector_key: str | None) -> bool:
        if not collector_key:
            return False
        definition = COLLECTION_TASK_DEFINITIONS.get(str(collector_key).strip().lower())
        return bool(definition and definition.get("manual_only"))

    def _is_calendar_daily_collection(self, collector_key: str | None) -> bool:
        if not collector_key:
            return False
        definition = COLLECTION_TASK_DEFINITIONS.get(str(collector_key).strip().lower())
        return bool(definition and definition.get("calendar_daily"))

    def _is_manual_only_task(self, task: ScheduledTask) -> bool:
        if task.task_type != "collection":
            return False
        config = task.config_json or {}
        try:
            collector_key = self._normalize_collector_key(
                config.get("collector_key"),
                task.market_scope,
                config.get("target_type"),
                config.get("target_code") or config.get("stock_code"),
                config.get("target_name"),
                task.name,
            )
        except ValueError:
            return False
        return self._is_manual_only_collection(collector_key)

    def _is_calendar_daily_task(self, task: ScheduledTask) -> bool:
        if task.task_type != "collection":
            return False
        config = task.config_json or {}
        try:
            collector_key = self._normalize_collector_key(
                config.get("collector_key"),
                task.market_scope,
                config.get("target_type"),
                config.get("target_code") or config.get("stock_code"),
                config.get("target_name"),
                task.name,
            )
        except ValueError:
            return False
        return self._is_calendar_daily_collection(collector_key)

    def _polling_window_for_task(
        self,
        task: ScheduledTask,
        *,
        include_internal: bool = False,
    ) -> tuple[time, time, int] | None:
        if task.task_type != "collection":
            return None
        config = task.config_json or {}
        try:
            collector_key = self._normalize_collector_key(
                config.get("collector_key"),
                task.market_scope,
                config.get("target_type"),
                config.get("target_code") or config.get("stock_code"),
                config.get("target_name"),
                task.name,
            )
        except ValueError:
            return None
        definition = COLLECTION_TASK_DEFINITIONS.get(collector_key) or {}
        if definition.get("poll_inside_run") and not include_internal:
            return None
        end_time_text = str(definition.get("poll_end_time") or "").strip()
        if not end_time_text:
            return None
        start_hour, start_minute = self._parse_schedule_parts(task.schedule_time)
        end_hour, end_minute = self._parse_schedule_parts(end_time_text)
        start_time = time(hour=start_hour, minute=start_minute)
        end_time = time(hour=end_hour, minute=end_minute)
        if end_time <= start_time:
            raise ValueError("poll_end_time must be later than schedule_time")
        try:
            interval_minutes = max(1, int(definition.get("poll_interval_minutes") or 1))
        except (TypeError, ValueError):
            interval_minutes = 1
        return start_time, end_time, interval_minutes

    def _uses_internal_polling(self, task: ScheduledTask) -> bool:
        if task.task_type != "collection":
            return False
        config = task.config_json or {}
        try:
            collector_key = self._normalize_collector_key(
                config.get("collector_key"),
                task.market_scope,
                config.get("target_type"),
                config.get("target_code") or config.get("stock_code"),
                config.get("target_name"),
                task.name,
            )
        except ValueError:
            return False
        definition = COLLECTION_TASK_DEFINITIONS.get(collector_key) or {}
        return bool(definition.get("poll_inside_run"))

    def _polling_run_state_for_date(self, task: ScheduledTask, target_date: date) -> tuple[bool, bool]:
        day_start = datetime.combine(target_date, time.min)
        day_end = day_start + timedelta(days=1)
        runs = (
            self.db.query(ScheduledTaskRun)
            .filter(
                ScheduledTaskRun.scheduled_task_id == task.id,
                ScheduledTaskRun.trigger_type == "schedule",
                ScheduledTaskRun.scheduled_for >= day_start,
                ScheduledTaskRun.scheduled_for < day_end,
                ScheduledTaskRun.status.in_(("queued", "running", "success", "failed")),
            )
            .order_by(ScheduledTaskRun.id.desc())
            .limit(5)
            .all()
        )
        has_success = False
        has_active = False
        for run in runs:
            scheduled_for = getattr(run, "scheduled_for", None)
            if (
                getattr(run, "scheduled_task_id", None) != task.id
                or getattr(run, "trigger_type", None) != "schedule"
                or not isinstance(scheduled_for, datetime)
                or scheduled_for.date() != target_date
            ):
                continue
            status = str(getattr(run, "status", "") or "").strip().lower()
            summary = str(getattr(run, "summary", "") or "").strip()
            has_success = has_success or status == "success" or (
                status == "failed" and summary.startswith(DOUYIN_POLL_TERMINAL_SUMMARY_PREFIX)
            )
            has_active = has_active or status in {"queued", "running"}
        return has_success, has_active

    def _is_single_stock_collection(self, task: ScheduledTask | None = None, config: dict | None = None) -> bool:
        target_config = config if config is not None else (task.config_json if task is not None else {}) or {}
        market_scope = task.market_scope if task is not None else None
        collector_key = self._normalize_collector_key(
            target_config.get("collector_key"),
            market_scope,
            target_config.get("target_type"),
            target_config.get("target_code") or target_config.get("stock_code"),
            target_config.get("target_name"),
            task.name if task is not None else None,
        )
        return collector_key == "stock_hfq_single"

    def _now(self) -> datetime:
        return datetime.now(SHANGHAI_TZ).replace(tzinfo=None)

    def _format_schedule_time(self, raw_value: str) -> str:
        value = raw_value.strip()
        if not SCHEDULE_TIME_PATTERN.match(value):
            raise ValueError("schedule_time must be in HH:MM format")
        return value

    def _parse_schedule_parts(self, raw_value: str) -> tuple[int, int]:
        normalized = self._format_schedule_time(raw_value)
        hours_text, minutes_text = normalized.split(":")
        return int(hours_text), int(minutes_text)

    def _scheduled_for_today(self, schedule_time: str, now: datetime) -> datetime:
        hour, minute = self._parse_schedule_parts(schedule_time)
        return datetime.combine(now.date(), time(hour=hour, minute=minute))

    def _due_scheduled_for(self, task: ScheduledTask, now: datetime) -> datetime | None:
        if self._is_manual_only_task(task):
            return None
        if not task.enabled:
            return None

        if self._uses_internal_polling(task):
            internal_window = self._polling_window_for_task(task, include_internal=True)
            if internal_window is not None:
                start_time, end_time, _interval_minutes = internal_window
                if now.time() < start_time or now.time() > end_time:
                    return None

        polling_window = self._polling_window_for_task(task)
        if polling_window is not None:
            start_time, end_time, interval_minutes = polling_window
            start_at = datetime.combine(now.date(), start_time)
            end_at = datetime.combine(now.date(), end_time)
            if now < start_at or now > end_at:
                return None
            has_success, has_active = self._polling_run_state_for_date(task, now.date())
            if has_success or has_active:
                return None
            elapsed_minutes = max(0, int((now - start_at).total_seconds() // 60))
            slot_minutes = (elapsed_minutes // interval_minutes) * interval_minutes
            scheduled_for = start_at + timedelta(minutes=slot_minutes)
            return scheduled_for if scheduled_for <= end_at else None

        scheduled_for = self._scheduled_for_today(task.schedule_time, now)
        if scheduled_for > now:
            return None

        return scheduled_for

    def _normalize_market_scope(self, raw_value: str | None) -> str:
        return self.market_calendar.normalize_market_scope(raw_value)

    def _effective_task_market_scope(self, task: ScheduledTask, config: dict | None = None) -> str:
        if task.task_type != "collection":
            return self._normalize_market_scope(task.market_scope)

        target_config = config if config is not None else (task.config_json or {})
        try:
            collector_key = self._normalize_collector_key(
                target_config.get("collector_key"),
                task.market_scope,
                target_config.get("target_type"),
                target_config.get("target_code") or target_config.get("stock_code"),
                target_config.get("target_name"),
                task.name,
            )
            return self._collection_market_scope(collector_key)
        except ValueError:
            return self._normalize_market_scope(task.market_scope)

    def _resolve_index_name(self, target_code: str | None, market_scope: str | None) -> str | None:
        normalized = str(target_code or "").strip()
        if not normalized:
            normalized_scope = self._normalize_market_scope(market_scope)
            if normalized_scope == "hk_index":
                return HK_INDEX_ALL_NAME
            if normalized_scope == "us_index":
                return US_INDEX_ALL_NAME
            return None
        normalized_scope = self._normalize_market_scope(market_scope)
        if normalized_scope == "hk_index" and normalized == HK_INDEX_ALL_CODE:
            return HK_INDEX_ALL_NAME
        if normalized_scope == "us_index" and normalized == US_INDEX_ALL_CODE:
            return US_INDEX_ALL_NAME
        market = "hk" if normalized_scope == "hk_index" else "us"
        for item in self.stock_service.list_index_options(market=market):
            if str(item.get("code", "")).strip() == normalized:
                return str(item.get("name", "")).strip() or None
        return None

    def _resolve_collection_target_name(
        self,
        target_type: str | None,
        target_code: str | None,
        market_scope: str | None,
    ) -> str | None:
        normalized_type = str(target_type or "").strip().lower()
        if normalized_type == "stock":
            return self._resolve_stock_name(target_code)
        if normalized_type == "index":
            return self._resolve_index_name(target_code, market_scope)
        return None

    def _resolve_stock_name(self, stock_code: str | None) -> str | None:
        normalized = str(stock_code or "").strip()
        if not normalized:
            return None
        candidates = self.stock_service.search_symbols(keyword=normalized, limit=20)
        for item in candidates:
            if str(item.get("ts_code", "")).strip() == normalized:
                return str(item.get("stock_name", "")).strip() or None
        return None

    def _serialize_run(self, item: ScheduledTaskRun) -> dict:
        return {
            "id": item.id,
            "scheduled_task_id": item.scheduled_task_id,
            "trigger_type": item.trigger_type,
            "status": item.status,
            "celery_task_id": item.celery_task_id,
            "scheduled_for": item.scheduled_for,
            "started_at": item.started_at,
            "finished_at": item.finished_at,
            "summary": item.summary or "",
            "error_message": item.error_message or "",
            "created_at": item.created_at,
        }

    def _resolve_strategy_names(self, strategy_ids: list[int], owner_user_id: int) -> list[str]:
        if not strategy_ids:
            return []
        items = (
            self.db.query(QuantStrategyConfig)
            .filter(
                QuantStrategyConfig.owner_user_id == owner_user_id,
                QuantStrategyConfig.id.in_(strategy_ids),
            )
            .order_by(QuantStrategyConfig.updated_at.desc())
            .all()
        )
        name_map = {item.id: item.name for item in items}
        return [name_map[strategy_id] for strategy_id in strategy_ids if strategy_id in name_map]

    def _compute_next_run_at_for_scope(self, market_scope: str, schedule_time: str) -> datetime:
        hour, minute = self._parse_schedule_parts(schedule_time)
        now = self._now()
        today = now.date()
        today_candidate = datetime.combine(today, time(hour=hour, minute=minute))
        if self.market_calendar.is_trading_day(market_scope, today) and today_candidate > now:
            return today_candidate

        next_trade_date = self.market_calendar.next_trading_day(market_scope, today + timedelta(days=1))
        return datetime.combine(next_trade_date, time(hour=hour, minute=minute))

    def _notification_basis_trade_date(self, market_scope: str, run_at: datetime) -> date:
        market_open = self.market_calendar.market_open_time(market_scope, run_at.date())
        if run_at.time() < market_open:
            return self.market_calendar.previous_trading_day(market_scope, run_at.date())
        return run_at.date()

    def _compute_next_run_at(self, item: ScheduledTask) -> datetime | None:
        if self._is_manual_only_task(item):
            return None
        if not item.enabled:
            return None
        if self._uses_internal_polling(item):
            internal_window = self._polling_window_for_task(item, include_internal=True)
            if internal_window is not None:
                start_time, _end_time, _interval_minutes = internal_window
                now = self._now()
                start_at = datetime.combine(now.date(), start_time)
                return start_at if now < start_at else datetime.combine(
                    now.date() + timedelta(days=1),
                    start_time,
                )
        polling_window = self._polling_window_for_task(item)
        if polling_window is not None:
            start_time, end_time, interval_minutes = polling_window
            now = self._now()
            start_at = datetime.combine(now.date(), start_time)
            end_at = datetime.combine(now.date(), end_time)
            has_success, _has_active = self._polling_run_state_for_date(item, now.date())
            if has_success or now >= end_at:
                return datetime.combine(now.date() + timedelta(days=1), start_time)
            if now < start_at:
                return start_at
            next_slot = now.replace(second=0, microsecond=0) + timedelta(minutes=interval_minutes)
            return next_slot if next_slot <= end_at else datetime.combine(now.date() + timedelta(days=1), start_time)
        if self._is_calendar_daily_task(item):
            hour, minute = self._parse_schedule_parts(item.schedule_time)
            now = self._now()
            candidate = datetime.combine(now.date(), time(hour=hour, minute=minute))
            return candidate if candidate > now else candidate + timedelta(days=1)
        market_scope = self._effective_task_market_scope(item)
        return self._compute_next_run_at_for_scope(market_scope, item.schedule_time)

    def _serialize_task(self, item: ScheduledTask) -> dict:
        def optional_config_text(value: object) -> str | None:
            if value is None:
                return None
            normalized = str(value).strip()
            if not normalized or normalized.lower() in {"none", "null"}:
                return None
            return normalized

        config = item.config_json or {}
        collector_key = None
        collection_label = None
        if item.task_type == "collection":
            collector_key = self._normalize_collector_key(
                config.get("collector_key"),
                item.market_scope,
                config.get("target_type"),
                config.get("target_code") or config.get("stock_code"),
                config.get("target_name"),
                item.name,
            )
            collection_label = str(self._get_collection_definition(collector_key).get("label") or "").strip() or None
        manual_only = self._is_manual_only_collection(collector_key)
        target_type = optional_config_text(config.get("target_type"))
        target_code = optional_config_text(config.get("target_code"))
        target_name = optional_config_text(config.get("target_name"))
        stock_code = optional_config_text(config.get("stock_code"))
        if stock_code and not target_code:
            target_code = stock_code
        if stock_code and not target_type:
            target_type = "stock"
        if target_type == "stock" and target_code and not stock_code:
            stock_code = target_code
        resolved_target_name = target_name or self._resolve_collection_target_name(target_type, target_code, item.market_scope)
        strategy_ids = [
            int(raw_id)
            for raw_id in config.get("strategy_ids", [])
            if isinstance(raw_id, int) or str(raw_id).isdigit()
        ]
        owner = self.db.get(User, item.owner_user_id) if item.task_type == "notification" else None
        return {
            "id": item.id,
            "owner_user_id": item.owner_user_id,
            "task_type": item.task_type,
            "market_scope": self._effective_task_market_scope(item, config),
            "collector_key": collector_key,
            "collection_label": collection_label,
            "manual_only": manual_only,
            "name": item.name,
            "enabled": bool(item.enabled),
            "schedule_time": item.schedule_time,
            "target_type": target_type,
            "target_code": target_code,
            "target_name": resolved_target_name,
            "stock_code": stock_code,
            "stock_name": resolved_target_name if target_type == "stock" else None,
            "strategy_ids": strategy_ids,
            "strategy_names": self._resolve_strategy_names(strategy_ids, item.owner_user_id),
            "target_email": str((owner.email if owner else None) or config.get("target_email", "")).strip() or None,
            "next_run_at": self._compute_next_run_at(item),
            "last_run_at": item.last_run_at,
            "last_run_status": item.last_run_status or "",
            "last_run_summary": item.last_run_summary or "",
            "last_error_message": item.last_error_message or "",
            "created_at": item.created_at,
            "updated_at": item.updated_at,
        }

    def list_root_visible_strategies(
        self,
        *,
        keyword: str = "",
        user_id: int | None = None,
        username: str | None = None,
        strategy_type: str = "stock",
    ) -> list[dict]:
        query = (
            self.db.query(QuantStrategyConfig, User)
            .join(User, QuantStrategyConfig.owner_user_id == User.id)
            .filter(User.role == "user")
        )

        normalized_user_id = int(user_id) if user_id else None
        normalized_username = str(username or "").strip()
        normalized_keyword = str(keyword or "").strip()
        normalized_strategy_type = str(strategy_type or "").strip().lower()

        if normalized_user_id:
            query = query.filter(User.id == normalized_user_id)

        if normalized_username:
            like_value = f"%{normalized_username}%"
            query = query.filter(
                or_(
                    User.username.like(like_value),
                    User.nickname.like(like_value),
                    User.phone.like(like_value),
                )
            )

        if normalized_strategy_type and normalized_strategy_type != "all":
            query = query.filter(QuantStrategyConfig.strategy_type == normalized_strategy_type)

        if normalized_keyword:
            like_value = f"%{normalized_keyword}%"
            query = query.filter(
                or_(
                    QuantStrategyConfig.name.like(like_value),
                    QuantStrategyConfig.target_code.like(like_value),
                    QuantStrategyConfig.target_name.like(like_value),
                    User.username.like(like_value),
                    User.nickname.like(like_value),
                    User.phone.like(like_value),
                )
            )

        rows = query.order_by(QuantStrategyConfig.updated_at.desc(), QuantStrategyConfig.id.desc()).all()
        return [
            {
                "id": strategy.id,
                "name": strategy.name,
                "notes": strategy.notes or "",
                "strategy_type": strategy.strategy_type,
                "target_code": strategy.target_code,
                "target_name": strategy.target_name,
                "start_date": strategy.start_date,
                "updated_at": strategy.updated_at,
                "owner_user_id": owner.id,
                "owner_username": owner.username,
                "owner_nickname": owner.nickname or "",
                "owner_role": owner.role,
            }
            for strategy, owner in rows
        ]

    def _get_owned_task(self, task_id: int, owner_user_id: int) -> ScheduledTask:
        item = (
            self.db.query(ScheduledTask)
            .filter(ScheduledTask.id == task_id, ScheduledTask.owner_user_id == owner_user_id)
            .first()
        )
        if item is None:
            raise LookupError("task not found")
        return item

    def _assert_create_permission(self, task_type: str, current_user: User) -> None:
        if task_type == "collection":
            if current_user.role != "root":
                raise PermissionError("only root can create collection tasks")
            return
        if task_type == "notification":
            if current_user.role == "guest":
                raise PermissionError("guest users cannot create notification tasks")
            return
        raise ValueError("unsupported task type")

    def _normalize_notification_strategy_ids(self, strategy_ids: list[int], owner_user_id: int) -> list[int]:
        normalized_ids: list[int] = []
        for raw_id in strategy_ids:
            parsed = int(raw_id)
            if parsed not in normalized_ids:
                normalized_ids.append(parsed)
        if not normalized_ids:
            raise ValueError("notification tasks require at least one strategy")
        matched_ids = {
            item.id
            for item in self.db.query(QuantStrategyConfig)
            .filter(
                QuantStrategyConfig.owner_user_id == owner_user_id,
                QuantStrategyConfig.id.in_(normalized_ids),
            )
            .all()
        }
        if len(matched_ids) != len(normalized_ids):
            raise ValueError("notification tasks can only target your own strategies")
        return normalized_ids

    def _build_config(self, payload: dict, current_user: User) -> tuple[str, dict]:
        task_type = str(payload.get("task_type", "")).strip()
        self._assert_create_permission(task_type, current_user)

        if task_type == "collection":
            target_code = str(payload.get("target_code") or payload.get("stock_code") or "").strip()
            target_type = str(payload.get("target_type", "")).strip().lower()
            target_name = str(payload.get("target_name", "")).strip()
            collector_key = self._normalize_collector_key(
                payload.get("collector_key"),
                payload.get("market_scope"),
                target_type,
                target_code,
                target_name,
                payload.get("name"),
            )
            definition = self._get_collection_definition(collector_key)
            market_scope = self._collection_market_scope(collector_key)
            requires_target = bool(definition.get("requires_target"))
            normalized_target_type = str(definition.get("target_type") or "").strip().lower() or None

            if requires_target:
                if not target_code:
                    raise ValueError("target_code is required for collection tasks")
                if not normalized_target_type:
                    normalized_target_type = target_type or "stock"
                if normalized_target_type != "stock":
                    raise ValueError("cn_stock collection tasks must target stocks")
            else:
                if collector_key == "index_hk_daily":
                    target_code = HK_INDEX_ALL_CODE
                    target_name = HK_INDEX_ALL_NAME
                    normalized_target_type = "index"
                elif collector_key == "index_us_daily":
                    target_code = US_INDEX_ALL_CODE
                    target_name = US_INDEX_ALL_NAME
                    normalized_target_type = "index"
                else:
                    target_code = ""
                    target_name = ""
                    normalized_target_type = None

            resolved_name = target_name or self._resolve_collection_target_name(normalized_target_type, target_code, market_scope)
            return market_scope, {
                "collector_key": collector_key,
                "manual_only": bool(definition.get("manual_only")),
                "target_type": normalized_target_type,
                "target_code": target_code or None,
                "target_name": resolved_name,
                "stock_code": target_code if normalized_target_type == "stock" else None,
            }

        target_email = str(current_user.email or "").strip()
        if not target_email:
            raise ValueError("please set your email in account center before enabling notification tasks")
        strategy_ids = self._normalize_notification_strategy_ids(payload.get("strategy_ids") or [], current_user.id)
        return self._normalize_market_scope(payload.get("market_scope")), {
            "strategy_ids": strategy_ids,
            "target_email": target_email,
        }

    def list_tasks(self, owner_user_id: int) -> list[dict]:
        items = (
            self.db.query(ScheduledTask)
            .filter(ScheduledTask.owner_user_id == owner_user_id)
            .order_by(ScheduledTask.updated_at.desc(), ScheduledTask.id.desc())
            .all()
        )
        return [self._serialize_task(item) for item in items]

    def get_task(self, task_id: int, owner_user_id: int) -> dict:
        item = self._get_owned_task(task_id, owner_user_id)
        return self._serialize_task(item)

    def create_task(self, payload: dict, current_user: User) -> dict:
        market_scope, config_json = self._build_config(
            {**payload, "market_scope": payload.get("market_scope", DEFAULT_MARKET_SCOPE)},
            current_user,
        )
        manual_only = bool(config_json.get("manual_only"))
        item = ScheduledTask(
            owner_user_id=current_user.id,
            task_type=str(payload.get("task_type", "")).strip(),
            market_scope=market_scope,
            name=str(payload.get("name", "")).strip(),
            enabled=False if manual_only else bool(payload.get("enabled", True)),
            schedule_time=self._format_schedule_time(str(payload.get("schedule_time", "")).strip()),
            config_json=config_json,
            last_run_status="",
            last_run_summary="",
            last_error_message="",
        )
        if not item.name:
            raise ValueError("task name is required")
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        if item.task_type == "notification":
            self.notification_service.sync_notification_task_requirements(item)
        elif item.task_type == "collection":
            stock_code = str((item.config_json or {}).get("stock_code", "")).strip()
            if item.market_scope == "cn_stock" and self._is_single_stock_collection(item) and stock_code:
                self.notification_service.sync_collection_task_state(item.market_scope, stock_code)
        return self._serialize_task(item)

    def update_task(self, task_id: int, payload: dict, current_user: User) -> dict:
        item = self._get_owned_task(task_id, current_user.id)
        previous_task_type = item.task_type
        previous_market_scope = item.market_scope
        previous_stock_code = str((item.config_json or {}).get("stock_code", "")).strip()
        next_task_type = str(payload.get("task_type", item.task_type)).strip()
        self._assert_create_permission(next_task_type, current_user)
        item.task_type = next_task_type
        item.market_scope = self._normalize_market_scope(str(payload.get("market_scope", item.market_scope)).strip())
        item.name = str(payload.get("name", item.name)).strip()
        item.schedule_time = self._format_schedule_time(str(payload.get("schedule_time", item.schedule_time)).strip())
        if not item.name:
            raise ValueError("task name is required")
        market_scope, config_json = self._build_config(
            {
                "task_type": item.task_type,
                "market_scope": item.market_scope,
                "collector_key": payload.get("collector_key"),
                "target_type": payload.get("target_type"),
                "target_code": payload.get("target_code"),
                "target_name": payload.get("target_name"),
                "stock_code": payload.get("stock_code"),
                "strategy_ids": payload.get("strategy_ids"),
            },
            current_user,
        )
        item.market_scope = market_scope
        item.config_json = config_json
        item.enabled = False if bool(config_json.get("manual_only")) else bool(payload.get("enabled", item.enabled))
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        if previous_task_type == "notification" and item.task_type != "notification":
            self.notification_service.remove_notification_task_requirements(item.id)
        if item.task_type == "notification":
            self.notification_service.sync_notification_task_requirements(item)

        current_stock_code = str((item.config_json or {}).get("stock_code", "")).strip()
        if previous_task_type == "collection" and previous_stock_code and (
            item.task_type != "collection"
            or previous_stock_code != current_stock_code
            or previous_market_scope != item.market_scope
        ):
            if previous_market_scope == "cn_stock":
                self.notification_service.sync_collection_task_state(previous_market_scope, previous_stock_code)
        if item.task_type == "collection" and item.market_scope == "cn_stock" and self._is_single_stock_collection(item) and current_stock_code:
            self.notification_service.sync_collection_task_state(item.market_scope, current_stock_code)
        return self._serialize_task(item)

    def delete_task(self, task_id: int, owner_user_id: int) -> None:
        item = self._get_owned_task(task_id, owner_user_id)
        previous_task_type = item.task_type
        previous_market_scope = item.market_scope
        previous_stock_code = str((item.config_json or {}).get("stock_code", "")).strip()
        if previous_task_type == "notification":
            self.notification_service.remove_notification_task_requirements(item.id)
        self.db.query(ScheduledTaskRun).filter(ScheduledTaskRun.scheduled_task_id == item.id).delete(
            synchronize_session=False
        )
        self.db.delete(item)
        self.db.commit()
        if previous_task_type == "collection" and previous_market_scope == "cn_stock" and previous_stock_code:
            self.notification_service.sync_collection_task_state(previous_market_scope, previous_stock_code)

    def toggle_task(self, task_id: int, enabled: bool, current_user: User) -> dict:
        item = self._get_owned_task(task_id, current_user.id)
        if self._is_manual_only_task(item):
            item.enabled = False
            self.db.add(item)
            self.db.commit()
            self.db.refresh(item)
            return self._serialize_task(item)
        if item.task_type == "notification":
            target_email = str(current_user.email or (item.config_json or {}).get("target_email") or "").strip()
            if enabled and not target_email:
                raise ValueError("please set your email in account center before enabling notification tasks")
            if target_email:
                item.config_json = {**(item.config_json or {}), "target_email": target_email}
        item.enabled = enabled
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        if item.task_type == "notification":
            self.notification_service.sync_notification_task_requirements(item)
        elif item.task_type == "collection":
            stock_code = str((item.config_json or {}).get("stock_code", "")).strip()
            if item.market_scope == "cn_stock" and self._is_single_stock_collection(item) and stock_code:
                self.notification_service.sync_collection_task_state(item.market_scope, stock_code)
        return self._serialize_task(item)

    def list_runs(self, task_id: int, owner_user_id: int, limit: int = 20) -> list[dict]:
        task = self._get_owned_task(task_id, owner_user_id)
        is_douyin_polling_task = (
            task.task_type == "collection"
            and str((task.config_json or {}).get("collector_key") or "").strip().lower()
            == "douyin_coze_emotion_daily"
        )
        query_limit = max(limit * 200, 2000) if is_douyin_polling_task else max(limit, 1)
        items = (
            self.db.query(ScheduledTaskRun)
            .filter(ScheduledTaskRun.scheduled_task_id == task.id)
            .order_by(ScheduledTaskRun.created_at.desc(), ScheduledTaskRun.id.desc())
            .limit(query_limit)
            .all()
        )
        if not is_douyin_polling_task:
            return [self._serialize_run(item) for item in items]

        visible_items: list[ScheduledTaskRun] = []
        scheduled_dates: set[date] = set()
        for item in items:
            if item.trigger_type == "schedule":
                scheduled_date = item.scheduled_for.date()
                if scheduled_date in scheduled_dates:
                    continue
                scheduled_dates.add(scheduled_date)
            visible_items.append(item)
            if len(visible_items) >= max(limit, 1):
                break
        return [self._serialize_run(item) for item in visible_items]

    def _create_run(self, task: ScheduledTask, trigger_type: str, scheduled_for: datetime) -> ScheduledTaskRun:
        item = ScheduledTaskRun(
            scheduled_task_id=task.id,
            trigger_type=trigger_type,
            status="queued",
            scheduled_for=scheduled_for,
            summary="",
            error_message="",
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_manual_run(self, task_id: int, owner_user_id: int) -> dict:
        task = self._get_owned_task(task_id, owner_user_id)
        run = self._create_run(task, trigger_type="manual", scheduled_for=self._now())
        return self._serialize_run(run)

    def _scheduled_run_exists(self, task_id: int, scheduled_for: datetime) -> bool:
        return (
            self.db.query(ScheduledTaskRun)
            .filter(
                ScheduledTaskRun.scheduled_task_id == task_id,
                ScheduledTaskRun.trigger_type == "schedule",
                ScheduledTaskRun.scheduled_for == scheduled_for,
            )
            .first()
            is not None
        )

    def enqueue_due_task_runs(self) -> list[int]:
        now = self._now()
        candidate_tasks = (
            self.db.query(ScheduledTask)
            .filter(
                ScheduledTask.enabled.is_(True),
            )
            .all()
        )
        created_run_ids: list[int] = []
        for task in candidate_tasks:
            scheduled_for = self._due_scheduled_for(task, now)
            if scheduled_for is None:
                continue
            if self._scheduled_run_exists(task.id, scheduled_for):
                continue

            if self._is_calendar_daily_task(task):
                run = self._create_run(task, trigger_type="schedule", scheduled_for=scheduled_for)
                task.last_scheduled_date = now.date()
                self.db.add(task)
                self.db.commit()
                created_run_ids.append(run.id)
                continue

            market_scope = self._effective_task_market_scope(task)
            market_reference_date = self.market_calendar.current_market_date(market_scope, now)
            if not self.market_calendar.is_trading_day(market_scope, market_reference_date):
                run = self._create_run(task, trigger_type="schedule", scheduled_for=scheduled_for)
                self._mark_run_state(
                    run,
                    task,
                    status="skipped",
                    summary="当前市场休市，已跳过自动调度。",
                    error_message="",
                    finished_at=now,
                )
                run.summary = "当前市场休市，已跳过自动调度。"
                task.last_run_summary = run.summary
                task.last_scheduled_date = market_reference_date
                self.db.add(task)
                self.db.add(run)
                self.db.commit()
                continue

            run = self._create_run(task, trigger_type="schedule", scheduled_for=scheduled_for)
            task.last_scheduled_date = market_reference_date
            self.db.add(task)
            self.db.commit()
            created_run_ids.append(run.id)
        return created_run_ids

    def bind_run_celery_task_id(self, run_id: int, celery_task_id: str) -> dict:
        item = self.db.get(ScheduledTaskRun, run_id)
        if item is None:
            raise LookupError("task run not found")
        item.celery_task_id = celery_task_id
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self._serialize_run(item)

    def _mark_run_state(
        self,
        run: ScheduledTaskRun,
        task: ScheduledTask,
        *,
        status: str,
        summary: str = "",
        error_message: str = "",
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        run.status = status
        if started_at is not None and run.started_at is None:
            run.started_at = started_at
        if finished_at is not None:
            run.finished_at = finished_at
        run.summary = summary
        run.error_message = error_message

        task.last_run_at = finished_at or started_at or self._now()
        task.last_run_status = status
        task.last_run_summary = summary
        task.last_error_message = error_message

        self.db.add(run)
        self.db.add(task)
        self.db.commit()

    def _send_email(self, recipient: str, subject: str, body: str) -> None:
        if not settings.smtp_host or not settings.smtp_from_email:
            raise RuntimeError("SMTP is not configured")

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = (
            f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
            if settings.smtp_from_name
            else settings.smtp_from_email
        )
        message["To"] = recipient
        message.set_content(body)

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)

    def _build_notification_email(self, task: ScheduledTask, owner: User, basis_trade_date: date) -> tuple[str, str]:
        config = task.config_json or {}
        strategy_ids = [
            int(raw_id)
            for raw_id in config.get("strategy_ids", [])
            if isinstance(raw_id, int) or str(raw_id).isdigit()
        ]
        if not strategy_ids:
            raise ValueError("notification task is missing strategy_ids")

        summaries = self.quant_service.list_strategy_notification_summaries(
            strategy_ids,
            owner.id,
            basis_trade_date=basis_trade_date,
        )
        if not summaries:
            raise ValueError("notification task has no available strategies")

        display_name = (owner.nickname or "").strip() or owner.username
        today_text = self._now().strftime("%Y-%m-%d")
        basis_date_text = basis_trade_date.isoformat()
        subject = f"[FIT] 每日策略通知 {today_text} - {task.name}"
        lines = [
            f"你好，{display_name}：",
            "",
            f"以下是任务“{task.name}”在 {today_text} 发送的策略摘要。",
            f"通知基准交易日：{basis_date_text}",
            "",
        ]

        actionable_count = 0
        for item in summaries:
            signal_text = str(item.get("signal_text", "无操作")).strip() or "无操作"
            if signal_text in {"蓝", "红", "紫"}:
                actionable_count += 1
            lines.extend(
                [
                    f"- 策略：{item.get('strategy_name', '-')}",
                    f"  标的：{item.get('target_name', '-')}",
                    f"  最新交易日：{item.get('latest_trade_date', '-')}",
                    f"  当日信号：{signal_text}",
                    f"  说明：{item.get('note', '无操作')}",
                    "",
                ]
            )

        lines.append(f"本次汇总共 {len(summaries)} 条策略，其中 {actionable_count} 条存在操作信号。")
        return subject, "\n".join(lines).strip()

    def _execute_notification_task(
        self,
        task: ScheduledTask,
        reference_dt: datetime | None = None,
    ) -> str:
        owner = self.db.get(User, task.owner_user_id)
        if owner is None:
            raise ValueError("task owner not found")
        if owner.role == "guest":
            raise PermissionError("guest users cannot execute notification tasks")

        recipient = str(owner.email or (task.config_json or {}).get("target_email") or "").strip()
        if not recipient:
            raise ValueError("notification task target email is missing")

        market_scope = self._normalize_market_scope(task.market_scope)
        basis_trade_date = self._notification_basis_trade_date(
            market_scope,
            reference_dt or self._now(),
        )
        subject, body = self._build_notification_email(task, owner, basis_trade_date)
        self._send_email(recipient, subject, body)

        strategy_count = len((task.config_json or {}).get("strategy_ids") or [])
        return (
            f"Sent notification email to {recipient} for {strategy_count} strategies "
            f"based on trade date {basis_trade_date.isoformat()}."
        )

    def _collection_validation_market_scope(self, collector_key: str) -> str:
        override_scope = COLLECTION_VALIDATION_MARKET_SCOPE_OVERRIDES.get(collector_key)
        if override_scope:
            return self._normalize_market_scope(override_scope)
        return self._collection_market_scope(collector_key)

    def _collection_validation_lagged_date(
        self,
        collector_key: str,
        market_scope: str,
        target_trade_date: date,
    ) -> date:
        definition = COLLECTION_TASK_DEFINITIONS.get(collector_key) or {}
        try:
            lag_days = max(0, int(definition.get("validation_trading_day_lag") or 0))
        except (TypeError, ValueError):
            lag_days = 0
        lagged_date = target_trade_date
        for _ in range(lag_days):
            lagged_date = self.market_calendar.previous_trading_day(market_scope, lagged_date)
        return lagged_date

    def _collection_target_trade_date(self, collector_key: str, reference_dt: datetime | None = None) -> date:
        if self._is_calendar_daily_collection(collector_key):
            reference = reference_dt or self._now()
            localized = (
                reference.replace(tzinfo=SHANGHAI_TZ)
                if reference.tzinfo is None
                else reference.astimezone(SHANGHAI_TZ)
            )
            return localized.date()
        market_scope = self._collection_validation_market_scope(collector_key)
        market_date = self.market_calendar.current_market_date(market_scope, reference_dt or self._now())
        if self.market_calendar.is_trading_day(market_scope, market_date):
            target_trade_date = market_date
        else:
            target_trade_date = self.market_calendar.previous_trading_day(market_scope, market_date)
        return self._collection_validation_lagged_date(
            collector_key,
            market_scope,
            target_trade_date,
        )

    def _collection_target_trade_date_for_task(
        self,
        collector_key: str,
        task: ScheduledTask,
        reference_dt: datetime | None = None,
    ) -> date:
        market_scope = self._collection_validation_market_scope(collector_key)
        reference = reference_dt or self._now()
        market_date = self.market_calendar.current_market_date(market_scope, reference)
        if not self.market_calendar.is_trading_day(market_scope, market_date):
            target_trade_date = self.market_calendar.previous_trading_day(market_scope, market_date)
        elif collector_key == "margin_trading_daily":
            target_trade_date = self.market_calendar.previous_trading_day(market_scope, market_date)
        else:
            reference_local = (
                reference.replace(tzinfo=SHANGHAI_TZ)
                if reference.tzinfo is None
                else reference.astimezone(SHANGHAI_TZ)
            )
            hour, minute = self._parse_schedule_parts(task.schedule_time)
            if reference_local.time() < time(hour=hour, minute=minute):
                target_trade_date = self.market_calendar.previous_trading_day(market_scope, market_date)
            else:
                target_trade_date = market_date
        return self._collection_validation_lagged_date(
            collector_key,
            market_scope,
            target_trade_date,
        )

    def _collection_probe_snapshot(self, probe: CollectionDataProbe, target_trade_date: date) -> tuple[int, object]:
        date_column = _quoted_identifier(probe.date_column)
        if probe.distinct_count_column:
            target_count_sql = (
                "COUNT(DISTINCT CASE "
                f"WHEN {date_column} = :target_trade_date "
                f"THEN {_quoted_identifier(probe.distinct_count_column)} END)"
            )
        else:
            target_count_sql = (
                f"SUM(CASE WHEN {date_column} = :target_trade_date THEN 1 ELSE 0 END)"
            )
        sql = (
            f"SELECT "
            f"{target_count_sql} AS target_count, "
            f"MAX({date_column}) AS latest_date "
            f"FROM {_quoted_identifier(probe.table_name)} "
            f"WHERE 1 = 1 "
            f"{probe.where_sql}"
        )
        params = {**probe.params, "target_trade_date": target_trade_date}
        row = self.db.execute(text(sql), params).mappings().first()
        if row is None:
            return 0, None
        return int(row.get("target_count") or 0), row.get("latest_date")

    def _qvix_recent_gap_failure(self, target_trade_date: date, lookback_days: int = 30) -> str:
        sql = f"""
            SELECT
                COUNT(*) AS missing_date_count,
                GROUP_CONCAT(
                    CONCAT(CAST(missing_by_date.trade_date AS CHAR), ':', missing_by_date.missing_codes)
                    ORDER BY missing_by_date.trade_date
                    SEPARATOR '；'
                ) AS missing_summary
            FROM (
                SELECT
                    expected.trade_date,
                    GROUP_CONCAT(expected.index_code ORDER BY expected.index_code SEPARATOR ',') AS missing_codes
                FROM (
                    SELECT recent_calendar.trade_date, basic.index_code
                    FROM (
                        SELECT trade_date
                        FROM (
                            SELECT DISTINCT trade_date
                            FROM `{settings.index_daily_table_name}`
                            WHERE `{settings.index_daily_code_column}` = :calendar_index_code
                              AND `{settings.index_daily_date_column}` <= :target_trade_date
                            ORDER BY `{settings.index_daily_date_column}` DESC
                            LIMIT {int(lookback_days)}
                        ) AS ordered_calendar
                    ) AS recent_calendar
                    CROSS JOIN `{settings.index_qvix_basic_info_table_name}` AS basic
                ) AS expected
                LEFT JOIN `{settings.index_qvix_daily_table_name}` AS qvix
                  ON qvix.`{settings.index_qvix_daily_date_column}` = expected.trade_date
                 AND qvix.`{settings.index_qvix_daily_code_column}` = expected.index_code
                WHERE qvix.`{settings.index_qvix_daily_code_column}` IS NULL
                GROUP BY expected.trade_date
            ) AS missing_by_date
        """
        row = self.db.execute(
            text(sql),
            {
                "calendar_index_code": "sh000001",
                "target_trade_date": target_trade_date,
            },
        ).mappings().first()
        if row is None or int(row.get("missing_date_count") or 0) <= 0:
            return ""
        return (
            f"近{lookback_days}个A股交易日QVIX仍有缺口："
            f"{row.get('missing_summary') or '-'}"
        )

    def _compact_upstream_result(self, result: dict | None) -> str:
        if not isinstance(result, dict):
            return "-"
        upstream_response = result.get("upstream_response")
        if isinstance(upstream_response, dict) and "result" in upstream_response:
            raw_value = upstream_response.get("result")
        else:
            raw_value = result
        text_value = str(raw_value)
        if len(text_value) > 300:
            return f"{text_value[:300]}..."
        return text_value

    def _validate_collection_result(
        self,
        collector_key: str,
        label: str,
        result: dict | None,
        reference_dt: datetime | None = None,
        target_trade_date: date | None = None,
    ) -> str:
        probes = COLLECTION_DATA_PROBES.get(collector_key, [])
        if not probes:
            return ""

        # End the read transaction that loaded the task/run before the upstream
        # collector wrote data. MySQL's default REPEATABLE READ would otherwise
        # keep validating against a stale snapshot and report freshly inserted
        # rows as missing.
        in_transaction = getattr(self.db, "in_transaction", None)
        if callable(in_transaction) and in_transaction():
            self.db.rollback()

        target_trade_date = target_trade_date or self._collection_target_trade_date(collector_key, reference_dt)
        failures: list[str] = []
        successes: list[str] = []
        definition = COLLECTION_TASK_DEFINITIONS.get(collector_key) or {}
        try:
            latest_release_max_age_days = max(
                0,
                int(definition.get("latest_release_max_age_days") or 0),
            )
        except (TypeError, ValueError):
            latest_release_max_age_days = 0

        if latest_release_max_age_days:
            reference = reference_dt or self._now()
            reference_local = (
                reference.replace(tzinfo=SHANGHAI_TZ)
                if reference.tzinfo is None
                else reference.astimezone(SHANGHAI_TZ)
            )
            for probe in probes:
                _, latest_date = self._collection_probe_snapshot(probe, target_trade_date)
                if latest_date is None:
                    failures.append(f"{probe.label}尚无任何已发布数据")
                    continue
                normalized_latest_date = (
                    latest_date.date()
                    if isinstance(latest_date, datetime)
                    else latest_date
                )
                if not isinstance(normalized_latest_date, date):
                    normalized_latest_date = date.fromisoformat(str(latest_date))
                latest_count, _ = self._collection_probe_snapshot(probe, normalized_latest_date)
                age_days = (reference_local.date() - normalized_latest_date).days
                if latest_count < probe.minimum_rows:
                    failures.append(
                        f"{probe.label}最新发布日{normalized_latest_date.isoformat()}仅"
                        f"{latest_count}行（要求至少{probe.minimum_rows}行）"
                    )
                elif age_days > latest_release_max_age_days:
                    failures.append(
                        f"{probe.label}最新发布日{normalized_latest_date.isoformat()}，"
                        f"已超过{latest_release_max_age_days}天未更新"
                    )
                else:
                    successes.append(
                        f"{probe.label}最新月度发布"
                        f"{normalized_latest_date.isoformat()}共{latest_count}行"
                    )
            if failures:
                upstream_result = self._compact_upstream_result(result)
                raise RuntimeError(
                    f"{label}入库校验失败：{'；'.join(failures)}；"
                    f"上游返回：{upstream_result}"
                )
            return f"已确认月度源有效：{'，'.join(successes)}。"

        def collect_probe_results(validation_date: date) -> tuple[list[str], list[str]]:
            date_failures: list[str] = []
            date_successes: list[str] = []
            for probe in probes:
                target_count, latest_date = self._collection_probe_snapshot(probe, validation_date)
                if target_count < probe.minimum_rows:
                    date_failures.append(
                        f"{probe.label}目标日{validation_date.isoformat()}仅{target_count}行"
                        f"（要求至少{probe.minimum_rows}行，当前最新{latest_date or '-'}）"
                    )
                    continue
                suffix = "分钟" if probe.distinct_count_column else "行"
                success = f"{probe.label}{target_count}{suffix}"
                if probe.warning_below_rows and target_count < probe.warning_below_rows:
                    success += (
                        f"（质量告警：可计算点少于{probe.warning_below_rows}，"
                        "原始分钟完整但部分时点方差无效）"
                    )
                date_successes.append(success)
            return date_failures, date_successes

        failures, successes = collect_probe_results(target_trade_date)
        if failures and bool(definition.get("accept_previous_trading_day")):
            market_scope = self._collection_validation_market_scope(collector_key)
            previous_trade_date = self.market_calendar.previous_trading_day(
                market_scope,
                target_trade_date,
            )
            previous_failures, previous_successes = collect_probe_results(previous_trade_date)
            if not previous_failures:
                return (
                    f"目标交易日 {target_trade_date.isoformat()} 的上游数据尚未发布；"
                    f"本次实际更新并确认的是前一美股交易日 {previous_trade_date.isoformat()}："
                    f"{'，'.join(previous_successes)}。"
                )

        if collector_key == "index_qvix_daily" and not failures:
            qvix_gap_failure = self._qvix_recent_gap_failure(target_trade_date)
            if qvix_gap_failure:
                failures.append(qvix_gap_failure)

        if failures:
            upstream_result = self._compact_upstream_result(result)
            raise RuntimeError(
                f"{label}入库校验失败：目标交易日 {target_trade_date.isoformat()} 数据未完整入库；"
                f"{'；'.join(failures)}；上游返回：{upstream_result}"
            )

        return f"已确认 {target_trade_date.isoformat()} 数据入库：{'，'.join(successes)}。"

    def _execute_collection_task(
        self,
        task: ScheduledTask,
        reference_dt: datetime | None = None,
        trigger_type: str | None = None,
    ) -> str:
        config = task.config_json or {}
        collector_key = self._normalize_collector_key(
            config.get("collector_key"),
            task.market_scope,
            config.get("target_type"),
            config.get("target_code") or config.get("stock_code"),
            config.get("target_name"),
            task.name,
        )
        definition = self._get_collection_definition(collector_key)
        label = str(definition.get("label") or collector_key)
        target_code = str(config.get("target_code") or config.get("stock_code") or "").strip()
        target_name = str(config.get("target_name", "")).strip() or target_code

        if collector_key == "stock_hfq_single":
            if not target_code:
                raise ValueError("collection task is missing target_code")
            result = run_stock_hfq_collection_request(stock_code=target_code)
            upstream_status = str(result.get("upstream_status", result.get("status", "ok"))).upper()
            if upstream_status == "SUCCESS":
                return f"{target_name}（{target_code}）采集完成，已刷新数据。"
            if upstream_status == "UNCHANGED":
                return f"{target_name}（{target_code}）采集完成，但没有新数据。"
            return f"{target_name}（{target_code}）采集完成，状态：{upstream_status}。"

        explicit_target_trade_date: date | None = None
        collection_payload: dict | None = None
        if collector_key in {
            "stock_exchange_official_daily",
            "exchange_option_daily",
            "exchange_option_stats_daily",
            "option_minute_daily",
            "cn_risk_free_rate_daily",
            "cn_macro_daily",
            "margin_trading_daily",
            "fund_purchase_limit_daily",
            "quant_index_daily",
            "index_qvix_daily",
            "index_cn_market_fear_greed_daily",
            "index_cn_baifenwei_fear_greed_daily",
            "hk_index_futures_daily",
        }:
            explicit_target_trade_date = self._collection_target_trade_date_for_task(collector_key, task, reference_dt)
            if collector_key in {
                "stock_exchange_official_daily",
                "exchange_option_daily",
                "exchange_option_stats_daily",
                "option_minute_daily",
                "cn_risk_free_rate_daily",
                "cn_macro_daily",
                "margin_trading_daily",
                "fund_purchase_limit_daily",
                "index_cn_market_fear_greed_daily",
                "index_cn_baifenwei_fear_greed_daily",
                "hk_index_futures_daily",
            }:
                collection_payload = {"target_date": explicit_target_trade_date.isoformat()}
        elif collector_key == "douyin_coze_emotion_daily":
            explicit_target_trade_date = self._collection_target_trade_date(collector_key, reference_dt)
            collection_payload = {"target_date": explicit_target_trade_date.isoformat()}
            polling_window = (
                self._polling_window_for_task(task, include_internal=True)
                if trigger_type == "schedule"
                else None
            )
            if polling_window is not None:
                _start_time, end_time, _interval_minutes = polling_window
                checked_at = self._now()
                close_at = datetime.combine(checked_at.date(), end_time)
                collection_payload.update(
                    {
                        "keep_browser_open": checked_at < close_at,
                        "browser_close_at": close_at.isoformat(),
                    }
                )

        try:
            if collector_key == "index_hk_daily":
                result = run_index_daily_collection_request("hk")
            elif collector_key == "index_us_daily":
                result = run_index_daily_collection_request("us")
            else:
                endpoint = str(definition.get("endpoint") or "").strip()
                result = run_daily_collection_request(
                    collector_key=collector_key,
                    endpoint=endpoint,
                    payload=collection_payload,
                )
        except Exception as exc:  # noqa: BLE001
            error_text = str(exc)
            cme_source_blocked = (
                collector_key == "us_index_futures_official_daily"
                and any(
                    marker in error_text
                    for marker in (
                        "CME settlements official API blocked the request",
                        "SSLEOFError",
                        "UNEXPECTED_EOF_WHILE_READING",
                    )
                )
            )
            if not cme_source_blocked:
                raise
            probe = COLLECTION_DATA_PROBES[collector_key][0]
            target_date = self._collection_target_trade_date(collector_key, reference_dt)
            _, latest_date = self._collection_probe_snapshot(probe, target_date)
            raise TaskRunSkipped(
                "CME 官方结算接口拒绝当前网络请求，今日官方合约采集已跳过，"
                f"未覆盖或伪造数据；库内最近官方交易日为 {latest_date or '-'}。"
                "普通美股股指期货日更仍会按前一美股交易日更新。"
            ) from exc

        if str(result.get("status") or "").strip().lower() == "deduplicated":
            raise TaskRunSkipped(
                f"{label}已有同类型采集正在运行，本次重复请求已跳过，"
                "不会重复访问上游或重复写入数据。"
            )

        upstream_status = str(result.get("upstream_status", result.get("status", "ok"))).upper()
        upstream_payload = result.get("upstream_response") if isinstance(result, dict) else None
        upstream_task_name = str(upstream_payload.get("task_name") or "").strip() if isinstance(upstream_payload, dict) else ""
        if upstream_task_name and upstream_task_name != collector_key:
            raise RuntimeError(
                f"采集接口返回任务名不匹配：期望 {label}（{collector_key}），"
                f"实际 {upstream_task_name}。请检查采集端服务是否已重启并加载最新路由。"
            )
        result_value = upstream_payload.get("result") if isinstance(upstream_payload, dict) else None
        result_status = (
            str(result_value.get("status") or "").strip().upper()
            if isinstance(result_value, dict)
            else ""
        )
        if collector_key == "margin_trading_daily" and result_status == "SOURCE_NOT_READY":
            target_date = str(result_value.get("target_date") or explicit_target_trade_date or "-")
            latest_complete = str(result_value.get("latest_complete_date") or "-")
            available = ", ".join(result_value.get("available_exchanges") or []) or "-"
            expected = ", ".join(result_value.get("expected_exchanges") or []) or "-"
            polling_window = (
                self._polling_window_for_task(task, include_internal=True)
                if trigger_type == "schedule"
                else None
            )
            if polling_window is not None:
                _start_time, end_time, interval_minutes = polling_window
                checked_at = self._now()
                end_at = datetime.combine(checked_at.date(), end_time)
                if checked_at < end_at:
                    raise TaskRunPollingPending(
                        f"{label}官方源尚未完整：目标交易日 {target_date}，"
                        f"已发布 {available}，应有 {expected}；"
                        f"将在同一条运行记录内继续检查。",
                        countdown_seconds=interval_minutes * 60,
                    )
            raise TaskRunSkipped(
                f"{label}官方源尚未发布完整：目标交易日 {target_date}，"
                f"已发布 {available}，应有 {expected}，最近完整日期 {latest_complete}。"
            )
        if collector_key == "hk_index_futures_daily" and result_status == "SOURCE_NOT_READY":
            target_date = str(result_value.get("target_date") or explicit_target_trade_date or "-")
            available = ", ".join(result_value.get("available_products") or []) or "-"
            expected = ", ".join(result_value.get("expected_products") or []) or "HSI, HHI, HTI"
            polling_window = (
                self._polling_window_for_task(task, include_internal=True)
                if trigger_type == "schedule"
                else None
            )
            if polling_window is not None:
                _start_time, end_time, interval_minutes = polling_window
                checked_at = self._now()
                end_at = datetime.combine(checked_at.date(), end_time)
                if checked_at < end_at:
                    raise TaskRunPollingPending(
                        f"{label}港交所日市况报告尚未完整：目标交易日 {target_date}，"
                        f"已发布 {available}，应有 {expected}；"
                        f"将在同一条运行记录内继续检查。",
                        countdown_seconds=interval_minutes * 60,
                    )
            raise TaskRunSkipped(
                f"{label}截至 23:30 港交所日市况报告仍未完整：目标交易日 {target_date}，"
                f"已发布 {available}，应有 {expected}。"
            )
        douyin_processing_error = (
            str(result_value.get("error") or "").strip()
            if isinstance(result_value, dict)
            else ""
        )
        douyin_incomplete_extraction = (
            collector_key == "douyin_coze_emotion_daily"
            and result_status == "UPDATE_FOUND_FAILED"
            and any(
                marker in douyin_processing_error
                for marker in (
                    "文案缺少",
                    "图文 OCR 缺少情绪指标",
                    "情绪指标存在歧义",
                    "正式情绪表仅有",
                )
            )
        )
        if (
            collector_key == "douyin_coze_emotion_daily"
            and result_status == "UPDATE_FOUND_FAILED"
            and not douyin_incomplete_extraction
        ):
            target_date = str(result_value.get("target_date") or explicit_target_trade_date or "-")
            video_id = str(result_value.get("video_id") or "-")
            error_message = douyin_processing_error or "作品处理失败"
            raise TaskRunTerminalFailure(
                f"{DOUYIN_POLL_TERMINAL_SUMMARY_PREFIX}：日期 {target_date}，作品 {video_id}；"
                f"后续情绪提取失败：{error_message}。今日轮询已停止。"
            )
        if (
            collector_key == "douyin_coze_emotion_daily"
            and (
                result_status == "UPDATE_FOUND_RETRYABLE"
                or douyin_incomplete_extraction
            )
        ):
            target_date = str(result_value.get("target_date") or explicit_target_trade_date or "-")
            video_id = str(result_value.get("video_id") or "-")
            error_message = douyin_processing_error or "作品处理暂时失败"
            polling_window = (
                self._polling_window_for_task(task, include_internal=True)
                if trigger_type == "schedule"
                else None
            )
            if polling_window is not None:
                _start_time, end_time, interval_minutes = polling_window
                checked_at = self._now()
                end_at = datetime.combine(checked_at.date(), end_time)
                if checked_at < end_at:
                    raise TaskRunPollingPending(
                        f"已发现今日作品 {video_id}，但处理暂未完成：{error_message}；"
                        f"将在同一条运行记录内继续重试。",
                        countdown_seconds=interval_minutes * 60,
                    )
            raise TaskRunRetryableFailure(
                f"作品处理可重试：日期 {target_date}，作品 {video_id}；"
                f"本轮自动重试后仍未完成：{error_message}。下一轮将继续重试。"
            )
        if collector_key == "douyin_coze_emotion_daily" and result_status == "NO_UPDATE":
            latest_video_date = str(result_value.get("latest_video_date") or "-")
            target_date = str(result_value.get("target_date") or explicit_target_trade_date or "-")
            minimum_publish_time = str(result_value.get("minimum_publish_time") or "15:00").strip()
            polling_window = (
                self._polling_window_for_task(task, include_internal=True)
                if trigger_type == "schedule"
                else None
            )
            if polling_window is not None:
                _start_time, end_time, interval_minutes = polling_window
                checked_at = self._now()
                end_at = datetime.combine(checked_at.date(), end_time)
                scheduled_at = reference_dt or checked_at
                if checked_at >= end_at or scheduled_at.time() >= end_time:
                    raise TaskRunSkipped(
                        f"{label}截至 {end_time.strftime('%H:%M')} 仍未发现 "
                        f"{minimum_publish_time} 后发布的新作品，"
                        f"当前最新作品日期为 {latest_video_date}，今日轮询已结束。"
                    )
                next_check = min(
                    checked_at.replace(second=0, microsecond=0) + timedelta(minutes=interval_minutes),
                    end_at,
                )
                if (
                    (COLLECTION_TASK_DEFINITIONS.get(collector_key) or {}).get("poll_inside_run")
                ):
                    raise TaskRunPollingPending(
                        f"{label}已检查：目标日期 {target_date} 的 {minimum_publish_time} 后"
                        f"暂未发布新作品，当前最新作品日期为 {latest_video_date}；"
                        f"将在同一条运行记录内于 {next_check.strftime('%H:%M')} 继续检查。",
                        countdown_seconds=interval_minutes * 60,
                    )
                raise TaskRunSkipped(
                    f"{label}已检查：目标日期 {target_date} 的 {minimum_publish_time} 后"
                    f"暂未发布新作品，"
                    f"当前最新作品日期为 {latest_video_date}；"
                    f"将在 {next_check.strftime('%H:%M')} 继续检查。"
                )
            raise TaskRunSkipped(
                f"{label}已检查：目标日期 {target_date} 当天 {minimum_publish_time} 后"
                f"未发布新作品，"
                f"当前最新作品日期为 {latest_video_date}。"
            )

        validation_summary = self._validate_collection_result(
            collector_key,
            label,
            result,
            reference_dt,
            target_trade_date=explicit_target_trade_date,
        )
        if collector_key == "douyin_coze_emotion_daily":
            self.stock_service.clear_index_emotions_cache()
            self.quant_service.clear_index_dashboard_cache("cn")
        elif collector_key in {
            "index_cn_market_fear_greed_daily",
            "index_cn_baifenwei_fear_greed_daily",
        }:
            self.quant_service.clear_index_dashboard_cache("cn")

        if result_value not in (None, ""):
            if isinstance(result_value, dict):
                target_date = str(result_value.get("target_date") or explicit_target_trade_date or "-")
                video_id = str(result_value.get("video_id") or "-")
                values = result_value.get("values") if isinstance(result_value.get("values"), dict) else {}
                if collector_key == "douyin_coze_emotion_daily":
                    summary = (
                        f"{label}执行完成：日期 {target_date}，作品 {video_id}，"
                        f"上证50={values.get('sz50_emotion', '-')}，"
                        f"沪深300={values.get('hs300_emotion', '-')}，"
                        f"中证500={values.get('zz500_emotion', '-')}，"
                        f"中证1000={values.get('zz1000_emotion', '-')}。"
                    )
                else:
                    summary = f"{label}执行完成，结果：{result_value}。"
            else:
                summary = f"{label}执行完成，结果：{result_value}。"
        else:
            summary = f"{label}执行完成，状态：{upstream_status}。"
        if validation_summary:
            summary += validation_summary
        return summary

    def execute_run(self, run_id: int) -> dict:
        run = self.db.get(ScheduledTaskRun, run_id)
        if run is None:
            raise LookupError("task run not found")
        task = self.db.get(ScheduledTask, run.scheduled_task_id)
        if task is None:
            raise LookupError("scheduled task not found")

        started_at = self._now()
        self._mark_run_state(run, task, status="running", started_at=started_at)

        try:
            if task.task_type == "collection":
                summary = self._execute_collection_task(
                    task,
                    reference_dt=run.scheduled_for or started_at,
                    trigger_type=run.trigger_type,
                )
            elif task.task_type == "notification":
                summary = self._execute_notification_task(
                    task,
                    reference_dt=run.scheduled_for or started_at,
                )
            else:
                raise ValueError("unsupported task type")
        except TaskRunSkipped as exc:
            finished_at = self._now()
            summary = str(exc)
            self._mark_run_state(
                run,
                task,
                status="skipped",
                summary=summary,
                error_message="",
                finished_at=finished_at,
            )
            self.db.refresh(run)
            return self._serialize_run(run)
        except TaskRunTerminalFailure as exc:
            finished_at = self._now()
            summary = str(exc)
            self._mark_run_state(
                run,
                task,
                status="failed",
                summary=summary,
                error_message=summary,
                finished_at=finished_at,
            )
            self.db.refresh(run)
            return self._serialize_run(run)
        except TaskRunRetryableFailure as exc:
            finished_at = self._now()
            summary = str(exc)
            self._mark_run_state(
                run,
                task,
                status="failed",
                summary=summary,
                error_message=summary,
                finished_at=finished_at,
            )
            self.db.refresh(run)
            return self._serialize_run(run)
        except TaskRunPollingPending as exc:
            self._mark_run_state(
                run,
                task,
                status="running",
                summary=str(exc),
                error_message="",
            )
            raise
        except Exception as exc:
            finished_at = self._now()
            self._mark_run_state(
                run,
                task,
                status="failed",
                summary="",
                error_message=str(exc),
                finished_at=finished_at,
            )
            raise

        finished_at = self._now()
        self._mark_run_state(
            run,
            task,
            status="success",
            summary=summary,
            error_message="",
            finished_at=finished_at,
        )
        self.db.refresh(run)
        return self._serialize_run(run)
