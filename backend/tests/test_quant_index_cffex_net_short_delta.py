from datetime import date, timedelta

from app.services.quant_service import BASIS_DELTA_FILTER_KEYS, CFFEX_NET_SHORT_DELTA_FILTER_KEYS, QuantService


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def _candle(trade_date: str, close: float) -> dict:
    return {
        "trade_date": trade_date,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
    }


def _series(product_codes: list[str], days: int = 35) -> dict:
    start = date(2026, 1, 1)
    result = {
        "top20_institutions": {"series": {code: [] for code in product_codes}},
        "citic_customer": {"series": {code: [] for code in product_codes}},
    }
    for index in range(days):
        trade_date = start + timedelta(days=index)
        for product_index, product_code in enumerate(product_codes):
            base = (product_index + 1) * 1000 + index * 10
            result["top20_institutions"]["series"][product_code].append(
                {"trade_date": trade_date, "net_position": base}
            )
            result["citic_customer"]["series"][product_code].append(
                {"trade_date": trade_date, "net_position": base + index}
            )
    return result


def test_cffex_net_short_delta_uses_trading_day_window():
    service = _service()

    rows = service._calculate_cffex_net_short_delta_points(_series(["IF"]), ["IF"])

    day_5 = next(item for item in rows if item["trade_date"] == "2026-01-06")
    day_7 = next(item for item in rows if item["trade_date"] == "2026-01-08")
    day_14 = next(item for item in rows if item["trade_date"] == "2026-01-15")
    day_20 = next(item for item in rows if item["trade_date"] == "2026-01-21")
    day_30 = next(item for item in rows if item["trade_date"] == "2026-01-31")
    assert day_5["top20_delta_5d"] == 50
    assert day_7["top20_delta_7d"] == 70
    assert day_14["top20_delta_14d"] == 140
    assert day_20["top20_delta_20d"] == 200
    assert day_7["top20_delta_30d"] is None
    assert day_30["top20_delta_30d"] == 300
    assert day_30["citic_delta_30d"] == 330


def test_cffex_net_short_delta_shared_indexes_sum_four_products():
    service = _service()

    rows = service._calculate_cffex_net_short_delta_points(
        _series(["IH", "IF", "IC", "IM"]),
        ["IH", "IF", "IC", "IM"],
    )

    day_7 = next(item for item in rows if item["trade_date"] == "2026-01-08")
    day_30 = next(item for item in rows if item["trade_date"] == "2026-01-31")
    assert day_7["top20_delta_7d"] == 280
    assert day_7["citic_delta_7d"] == 308
    assert day_30["top20_delta_30d"] == 1200


def test_cffex_net_short_delta_shared_indexes_sum_available_products():
    service = _service()

    rows = service._calculate_cffex_net_short_delta_points(
        _series(["IF"], days=10),
        ["IH", "IF", "IC", "IM"],
    )

    day_7 = next(item for item in rows if item["trade_date"] == "2026-01-08")
    assert day_7["top20_delta_7d"] == 70
    assert day_7["citic_delta_7d"] == 77


def test_cffex_net_short_delta_filter_keys_allowed_for_cn_indexes():
    service = _service()

    hs300_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000300", "沪深300")
    csi500_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000905", "中证500")

    assert set(CFFEX_NET_SHORT_DELTA_FILTER_KEYS).issubset(hs300_keys)
    assert set(CFFEX_NET_SHORT_DELTA_FILTER_KEYS).issubset(csi500_keys)


def test_basis_delta_filter_keys_allowed_for_cn_indexes():
    service = _service()

    hs300_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000300", "沪深300")
    sse_keys = service._allowed_snapshot_filter_keys("index", "cn", "sh000001", "上证指数")

    assert set(BASIS_DELTA_FILTER_KEYS).issubset(hs300_keys)
    assert set(BASIS_DELTA_FILTER_KEYS).issubset(sse_keys)


def test_index_snapshots_include_cffex_net_short_delta_values():
    service = _service()
    service._load_precomputed_index_indicator_rows = lambda symbol_name: [
        {
            "trade_date": date(2026, 4, 30),
            "emotion_value": 60,
            "main_basis": -20,
            "month_basis": -5,
            "up_ratio_pct": 55,
            "cffex_top20_net_short_delta_5d": 100,
            "cffex_top20_net_short_delta_7d": 123,
            "cffex_top20_net_short_delta_14d": 234,
            "cffex_top20_net_short_delta_20d": 345,
            "cffex_top20_net_short_delta_30d": 456,
            "cffex_top20_net_short_delta_60d": 567,
            "cffex_top20_net_short_delta_120d": 678,
            "cffex_citic_net_short_delta_5d": -5,
            "cffex_citic_net_short_delta_7d": -12,
            "cffex_citic_net_short_delta_14d": -14,
            "cffex_citic_net_short_delta_20d": -20,
            "cffex_citic_net_short_delta_30d": -34,
            "cffex_citic_net_short_delta_60d": -60,
            "cffex_citic_net_short_delta_120d": -120,
            "basis_main_delta_5d": 5,
            "basis_main_delta_7d": 7,
            "basis_main_delta_14d": 14,
            "basis_main_delta_20d": 20,
            "basis_main_delta_30d": 30,
            "basis_main_delta_60d": 60,
            "basis_main_delta_120d": 120,
            "basis_month_delta_5d": -5,
            "basis_month_delta_7d": -7,
            "basis_month_delta_14d": -14,
            "basis_month_delta_20d": -20,
            "basis_month_delta_30d": -30,
            "basis_month_delta_60d": -60,
            "basis_month_delta_120d": -120,
        }
    ]

    snapshots = service._build_index_snapshots("sh000001", "上证指数", {}, [_candle("2026-04-30", 3000)])

    values = snapshots[0]["values"]
    assert values["cffex-net-short-top20-delta-5d"] == 100
    assert values["cffex-net-short-top20-delta-7d"] == 123
    assert values["cffex-net-short-top20-delta-14d"] == 234
    assert values["cffex-net-short-top20-delta-20d"] == 345
    assert values["cffex-net-short-top20-delta-30d"] == 456
    assert values["cffex-net-short-top20-delta-60d"] == 567
    assert values["cffex-net-short-top20-delta-120d"] == 678
    assert values["cffex-net-short-citic-delta-5d"] == -5
    assert values["cffex-net-short-citic-delta-7d"] == -12
    assert values["cffex-net-short-citic-delta-14d"] == -14
    assert values["cffex-net-short-citic-delta-20d"] == -20
    assert values["cffex-net-short-citic-delta-30d"] == -34
    assert values["cffex-net-short-citic-delta-60d"] == -60
    assert values["cffex-net-short-citic-delta-120d"] == -120
    assert values["basis-main-delta-5d"] == 5
    assert values["basis-main-delta-7d"] == 7
    assert values["basis-main-delta-14d"] == 14
    assert values["basis-main-delta-20d"] == 20
    assert values["basis-main-delta-30d"] == 30
    assert values["basis-main-delta-60d"] == 60
    assert values["basis-main-delta-120d"] == 120
    assert values["basis-month-delta-5d"] == -5
    assert values["basis-month-delta-7d"] == -7
    assert values["basis-month-delta-14d"] == -14
    assert values["basis-month-delta-20d"] == -20
    assert values["basis-month-delta-30d"] == -30
    assert values["basis-month-delta-60d"] == -60
    assert values["basis-month-delta-120d"] == -120
