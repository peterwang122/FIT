from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FIT API"
    app_env: str = "dev"
    app_debug: bool = True
    api_prefix: str = "/api/v1"

    database_url: str = "mysql+pymysql://root:865418267@127.0.0.1:3306/stock_info"
    redis_url: str = "redis://127.0.0.1:6379/0"
    auth_session_cookie_name: str = "fit_session"
    auth_session_ttl_seconds: int = 604800
    auth_cookie_secure: bool = False
    auth_cookie_samesite: str = "lax"
    auth_sms_code_ttl_seconds: int = 300
    auth_sms_resend_cooldown_seconds: int = 60
    auth_sms_daily_limit: int = 10
    auth_sms_max_attempts: int = 5
    root_username: str = "root"
    root_password: str = "root123456"
    guest_username: str = "guest"
    guest_password: str = "guest123456"
    alibaba_cloud_access_key_id: str = ""
    alibaba_cloud_access_key_secret: str = ""
    aliyun_sms_access_key_id: str = ""
    aliyun_sms_access_key_secret: str = ""
    aliyun_sms_sign_name: str = ""
    aliyun_sms_template_code: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_from_email: str = ""
    smtp_from_name: str = "FIT 股票量化系统"
    github_token: str = ""
    github_api_base_url: str = "https://api.github.com"
    github_request_timeout_seconds: int = 30

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
    stock_basic_info_board_column: str = "board"
    stock_basic_cache_key: str = "fit:stock_basic_info:all"
    stock_basic_cache_ttl_seconds: int = 86400

    stock_hfq_table_name: str = "stock_hfq_daily_data"
    stock_hfq_code_column: str = "stock_code"
    stock_hfq_prefixed_code_column: str = "prefixed_code"
    stock_hfq_name_column: str = "stock_name"
    stock_hfq_date_column: str = "trade_date"
    stock_hfq_open_column: str = "open_price"
    stock_hfq_high_column: str = "high_price"
    stock_hfq_low_column: str = "low_price"
    stock_hfq_close_column: str = "close_price"
    stock_hfq_change_column: str = "price_change_amount"
    stock_hfq_pct_chg_column: str = "price_change_rate"
    stock_hfq_vol_column: str = "volume"
    stock_hfq_amount_column: str = "turnover_amount"
    stock_hfq_turnover_rate_column: str = "turnover_rate"
    stock_hfq_data_source_column: str = "data_source"

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

    index_us_basic_info_table_name: str = "index_us_basic_info"
    index_us_basic_info_code_column: str = "index_code"
    index_us_basic_info_name_column: str = "index_name"
    index_us_daily_table_name: str = "index_us_daily_data"
    index_us_daily_code_column: str = "index_code"
    index_us_daily_date_column: str = "trade_date"
    index_us_daily_open_column: str = "open_price"
    index_us_daily_high_column: str = "high_price"
    index_us_daily_low_column: str = "low_price"
    index_us_daily_close_column: str = "close_price"
    index_us_daily_change_column: str = "price_change_amount"
    index_us_daily_pct_chg_column: str = "price_change_rate"
    index_us_daily_vol_column: str = "volume"
    index_us_daily_amount_column: str = "turnover"

    index_hk_basic_info_table_name: str = "index_hk_basic_info"
    index_hk_basic_info_code_column: str = "index_code"
    index_hk_basic_info_name_column: str = "index_name"
    index_hk_daily_table_name: str = "index_hk_daily_data"
    index_hk_daily_code_column: str = "index_code"
    index_hk_daily_date_column: str = "trade_date"
    index_hk_daily_open_column: str = "open_price"
    index_hk_daily_high_column: str = "high_price"
    index_hk_daily_low_column: str = "low_price"
    index_hk_daily_close_column: str = "close_price"
    index_hk_daily_change_column: str = "price_change_amount"
    index_hk_daily_pct_chg_column: str = "price_change_rate"
    index_hk_daily_vol_column: str = "volume"
    index_hk_daily_amount_column: str = "turnover"

    index_qvix_basic_info_table_name: str = "index_qvix_basic_info"
    index_qvix_basic_info_code_column: str = "index_code"
    index_qvix_basic_info_name_column: str = "index_name"
    index_qvix_daily_table_name: str = "index_qvix_daily_data"
    index_qvix_daily_code_column: str = "index_code"
    index_qvix_daily_date_column: str = "trade_date"
    index_qvix_daily_open_column: str = "open_price"
    index_qvix_daily_high_column: str = "high_price"
    index_qvix_daily_low_column: str = "low_price"
    index_qvix_daily_close_column: str = "close_price"

    index_us_vix_daily_table_name: str = "index_us_vix_daily"
    index_us_vix_daily_date_column: str = "trade_date"
    index_us_vix_daily_open_column: str = "open_value"
    index_us_vix_daily_high_column: str = "high_value"
    index_us_vix_daily_low_column: str = "low_value"
    index_us_vix_daily_close_column: str = "close_value"

    index_us_fear_greed_daily_table_name: str = "index_us_fear_greed_daily"
    index_us_fear_greed_daily_date_column: str = "trade_date"
    index_us_fear_greed_daily_value_column: str = "fear_greed_value"
    index_us_fear_greed_daily_label_column: str = "sentiment_label"

    index_us_hedge_proxy_table_name: str = "index_us_hedge_fund_ls_proxy"
    index_us_hedge_proxy_report_date_column: str = "report_date"
    index_us_hedge_proxy_scope_column: str = "contract_scope"
    index_us_hedge_proxy_long_column: str = "long_value"
    index_us_hedge_proxy_short_column: str = "short_value"
    index_us_hedge_proxy_ratio_column: str = "ratio_value"
    index_us_hedge_proxy_release_date_column: str = "release_date"

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
    stock_temp_daily_service_timeout_seconds: int = 7200
    stock_temp_daily_task_soft_time_limit_seconds: int = 7200
    stock_temp_daily_task_time_limit_seconds: int = 7500
    stock_temp_daily_task_max_retries: int = 3

    task_idempotency_ttl_seconds: int = 3600
    collector_dedupe_lock_ttl_seconds: int = 120

    flower_url: str = "http://127.0.0.1:5555"
    cors_allow_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()  # type: ignore[call-arg]
