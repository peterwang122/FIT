from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FIT API"
    app_env: str = "dev"
    app_debug: bool = True
    api_prefix: str = "/api/v1"

    database_url: str = "mysql+pymysql://root:865418267@127.0.0.1:3306/stock_info"
    redis_url: str = "redis://127.0.0.1:6379/0"

    # read-only existing table mapping (defaults aligned with current DB)
    stock_table_name: str = "stock_daily_data"
    stock_code_column: str = "stock_code"
    stock_prefixed_code_column: str = "prefixed_code"
    stock_name_column: str = "stock_name"
    stock_date_column: str = "trade_date"
    stock_open_column: str = "open_price"
    stock_high_column: str = "high_price"
    stock_low_column: str = "low_price"
    stock_close_column: str = "close_price"
    stock_latest_price_column: str = "latest_price"
    stock_pre_close_column: str = "pre_close_price"
    stock_change_column: str = "price_change_amount"
    stock_pct_chg_column: str = "price_change_rate"
    stock_vol_column: str = "volume"
    stock_amount_column: str = "turnover_amount"
    stock_turnover_rate_column: str = "turnover_rate"
    stock_pe_ttm_column: str = "pe_ttm"
    stock_pb_column: str = "pb"
    stock_total_market_value_column: str = "total_market_value"
    stock_circulating_market_value_column: str = "circulating_market_value"
    stock_data_source_column: str = "data_source"
    stock_hist_source_value: str = "stock_zh_a_hist_tx"
    stock_spot_source_value: str = "stock_zh_a_spot"

    stock_basic_info_table_name: str = "stock_info_all"
    stock_basic_info_code_column: str = "stock_code"
    stock_basic_info_prefixed_code_column: str = "prefixed_code"
    stock_basic_info_name_column: str = "stock_name"
    stock_basic_cache_key: str = "fit:stock_basic_info:all"
    stock_basic_cache_ttl_seconds: int = 86400

    stock_qfq_table_name: str = "stock_qfq_daily_data"
    stock_qfq_code_column: str = "stock_code"
    stock_qfq_prefixed_code_column: str = "prefixed_code"
    stock_qfq_name_column: str = "stock_name"
    stock_qfq_date_column: str = "trade_date"
    stock_qfq_open_column: str = "open_price"
    stock_qfq_high_column: str = "high_price"
    stock_qfq_low_column: str = "low_price"
    stock_qfq_close_column: str = "close_price"
    stock_qfq_change_column: str = "price_change_amount"
    stock_qfq_pct_chg_column: str = "price_change_rate"
    stock_qfq_vol_column: str = "volume"
    stock_qfq_amount_column: str = "turnover_amount"
    stock_qfq_turnover_rate_column: str = "turnover_rate"
    stock_qfq_data_source_column: str = "data_source"

    index_basic_info_table_name: str = "index_basic_info"
    index_basic_info_code_column: str = "index_code"
    index_basic_info_name_column: str = "index_name"
    index_daily_table_name: str = "index_daily_data"
    index_daily_code_column: str = "index_code"
    index_daily_date_column: str = "trade_date"
    index_daily_open_column: str = "open_price"
    index_daily_high_column: str = "high_price"
    index_daily_low_column: str = "low_price"
    index_daily_close_column: str = "close_price"
    index_daily_change_column: str = "price_change_amount"
    index_daily_pct_chg_column: str = "price_change_rate"
    index_daily_vol_column: str = "volume"
    index_daily_amount_column: str = "turnover"

    forex_basic_info_table_name: str = "forex_basic_info"
    forex_basic_info_code_column: str = "symbol_code"
    forex_basic_info_name_column: str = "symbol_name"
    forex_daily_table_name: str = "forex_daily_data"
    forex_daily_code_column: str = "symbol_code"
    forex_daily_name_column: str = "symbol_name"
    forex_daily_date_column: str = "trade_date"
    forex_daily_open_column: str = "open_price"
    forex_daily_high_column: str = "high_price"
    forex_daily_low_column: str = "low_price"
    forex_daily_close_column: str = "latest_price"

    excel_index_emotion_table_name: str = "excel_index_emotion_daily"
    excel_index_emotion_date_column: str = "emotion_date"
    excel_index_emotion_name_column: str = "index_name"
    excel_index_emotion_value_column: str = "emotion_value"

    quant_index_dashboard_table_name: str = "quant_index_dashboard_daily"
    quant_index_dashboard_date_column: str = "trade_date"
    quant_index_dashboard_code_column: str = "index_code"
    quant_index_dashboard_name_column: str = "index_name"
    quant_index_dashboard_emotion_column: str = "emotion_value"
    quant_index_dashboard_main_basis_column: str = "main_basis"
    quant_index_dashboard_month_basis_column: str = "month_basis"
    quant_index_dashboard_breadth_up_count_column: str = "breadth_up_count"
    quant_index_dashboard_breadth_total_count_column: str = "breadth_total_count"
    quant_index_dashboard_breadth_up_pct_column: str = "breadth_up_pct"

    etf_basic_info_table_name: str = "etf_basic_info_sina"
    etf_basic_info_code_column: str = "etf_code"
    etf_basic_info_name_column: str = "etf_name"
    etf_daily_table_name: str = "etf_daily_data_sina"
    etf_daily_code_column: str = "etf_code"
    etf_daily_name_column: str = "etf_name"
    etf_daily_date_column: str = "trade_date"
    etf_daily_open_column: str = "open_price"
    etf_daily_close_column: str = "close_price"
    etf_daily_high_column: str = "high_price"
    etf_daily_low_column: str = "low_price"
    etf_daily_data_source_column: str = "data_source"
    etf_daily_hist_source_value: str = "fund_etf_hist_sina"
    etf_daily_spot_source_value: str = "fund_etf_category_sina"

    futures_daily_table_name: str = "futures_daily_data"
    futures_daily_symbol_column: str = "symbol"
    futures_daily_trade_date_column: str = "trade_date"
    futures_daily_close_column: str = "close_price"
    futures_daily_data_source_column: str = "data_source"
    futures_daily_primary_source_value: str = "get_futures_daily_derived"
    futures_daily_fallback_source_value: str = "futures_hist_em"

    cffex_member_rankings_table_name: str = "cffex_member_rankings"
    cffex_trade_date_column: str = "trade_date"
    cffex_product_code_column: str = "product_code"
    cffex_contract_code_column: str = "contract_code"
    cffex_rank_no_column: str = "rank_no"
    cffex_volume_member_column: str = "volume_member"
    cffex_long_member_column: str = "long_member"
    cffex_long_open_interest_column: str = "long_open_interest"
    cffex_long_change_value_column: str = "long_change_value"
    cffex_short_member_column: str = "short_member"
    cffex_short_open_interest_column: str = "short_open_interest"
    cffex_short_change_value_column: str = "short_change_value"

    collector_base_url: str = "http://127.0.0.1:9000"
    collector_timeout_seconds: int = 30
    collector_task_soft_time_limit_seconds: int = 45
    collector_task_time_limit_seconds: int = 60
    collector_task_max_retries: int = 3
    collector_task_retry_backoff_seconds: int = 5

    stock_temp_service_base_url: str = "http://127.0.0.1:8786"
    stock_temp_service_timeout_seconds: int = 1800
    stock_temp_task_soft_time_limit_seconds: int = 1800
    stock_temp_task_time_limit_seconds: int = 2100
    stock_temp_task_max_retries: int = 5

    task_idempotency_ttl_seconds: int = 3600
    collector_dedupe_lock_ttl_seconds: int = 120

    flower_url: str = "http://127.0.0.1:5555"
    cors_allow_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # type: ignore[call-arg]
