from datetime import date

from app.services.stock_service import (
    CITIC_CUSTOMER_MEMBER_NAME,
    GUOTAI_CUSTOMER_MEMBER_NAME,
    StockService,
)


def _service() -> StockService:
    return StockService.__new__(StockService)


def test_customer_member_names_follow_historical_cffex_labels():
    service = _service()

    assert service._resolve_member_name_for_trade_date(CITIC_CUSTOMER_MEMBER_NAME, date(2024, 2, 23)) == "中信期货"
    assert service._resolve_member_name_for_trade_date(CITIC_CUSTOMER_MEMBER_NAME, date(2024, 2, 26)) == "中信期货(经纪)"
    assert service._resolve_member_name_for_trade_date(CITIC_CUSTOMER_MEMBER_NAME, date(2024, 4, 29)) == "中信期货(代客)"
    assert service._resolve_member_name_for_trade_date(GUOTAI_CUSTOMER_MEMBER_NAME, date(2024, 2, 23)) == "国泰君安"
    assert service._resolve_member_name_for_trade_date(GUOTAI_CUSTOMER_MEMBER_NAME, date(2024, 2, 26)) == "国泰君安(经纪)"
    assert service._resolve_member_name_for_trade_date(GUOTAI_CUSTOMER_MEMBER_NAME, date(2024, 4, 29)) == "国泰君安(代客)"


def test_guotai_series_query_matches_all_historical_names():
    service = _service()

    member_sql = service._member_match_sql("short_member", "`trade_date`", GUOTAI_CUSTOMER_MEMBER_NAME)
    params = service._member_match_params(GUOTAI_CUSTOMER_MEMBER_NAME)

    assert "`trade_date` < :member_start_1" in member_sql
    assert "`trade_date` >= :member_start_1" in member_sql
    assert "`trade_date` < :member_start_2" in member_sql
    assert "`trade_date` >= :member_start_2" in member_sql
    assert params == {
        "member_name_0": "国泰君安",
        "member_name_1": "国泰君安(经纪)",
        "member_start_1": date(2024, 2, 26),
        "member_name_2": "国泰君安(代客)",
        "member_start_2": date(2024, 4, 29),
    }


def test_net_position_series_contains_citic_and_guotai_groups():
    service = _service()
    requested_members: list[str] = []
    service._cache_get_json = lambda _cache_key: None
    service._cache_set_json = lambda _cache_key, _value: None
    service._query_member_open_interest_series_rows = (
        lambda member_name, start_date=None, end_date=None: requested_members.append(member_name) or []
    )
    service._query_top20_open_interest_series_rows = lambda start_date=None, end_date=None: []

    result = service.get_cffex_net_position_series()

    assert requested_members == [CITIC_CUSTOMER_MEMBER_NAME, GUOTAI_CUSTOMER_MEMBER_NAME]
    assert result["citic_customer"]["member_label"] == CITIC_CUSTOMER_MEMBER_NAME
    assert result["guotai_customer"]["member_label"] == GUOTAI_CUSTOMER_MEMBER_NAME
    assert result["top20_institutions"]["member_label"] == "前20机构"
