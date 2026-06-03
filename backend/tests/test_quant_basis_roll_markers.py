from datetime import date

from app.services.quant_service import (
    _build_cn_basis_contract_roll_markers,
    _build_hk_basis_contract_roll_markers,
    _parse_cn_index_futures_contract_month,
)


def test_parse_cn_index_futures_contract_month():
    assert _parse_cn_index_futures_contract_month("IF2604", "IF") == (2026, 4)
    assert _parse_cn_index_futures_contract_month("IH9912", "IH") == (1999, 12)
    assert _parse_cn_index_futures_contract_month("IFM0", "IF") is None
    assert _parse_cn_index_futures_contract_month("IF2613", "IF") is None


def test_cn_roll_markers_filter_unfinished_current_contract():
    rows = [
        {"variety": "IF", "contract_code": "IF2604", "last_trade_date": date(2026, 4, 17)},
        {"variety": "IF", "contract_code": "IF2605", "last_trade_date": date(2026, 5, 6)},
    ]

    markers = _build_cn_basis_contract_roll_markers(
        rows,
        {"IF"},
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
    )

    assert markers == {"2026-04-17": ["IF2604"]}


def test_cn_roll_markers_allow_current_contract_after_third_friday():
    rows = [
        {"variety": "IF", "contract_code": "IF2605", "last_trade_date": date(2026, 5, 15)},
    ]

    markers = _build_cn_basis_contract_roll_markers(
        rows,
        {"IF"},
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )

    assert markers == {"2026-05-15": ["IF2605"]}


def test_cn_roll_markers_merge_multiple_contracts_on_same_day():
    rows = [
        {"variety": "IF", "contract_code": "IF2604", "last_trade_date": "2026-04-17"},
        {"variety": "IH", "contract_code": "IH2604", "last_trade_date": "2026-04-17"},
        {"variety": "IC", "contract_code": "IC2604", "last_trade_date": "2026-04-17"},
    ]

    markers = _build_cn_basis_contract_roll_markers(
        rows,
        {"IF", "IH"},
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
    )

    assert markers == {"2026-04-17": ["IF2604", "IH2604"]}


def test_hk_roll_markers_filter_unfinished_contract_month():
    rows = [
        {
            "source_contract_code": "HSIJ26",
            "contract_month": "2026-04",
            "last_trade_date": date(2026, 4, 29),
        },
        {
            "source_contract_code": "HSIK26",
            "contract_month": "2026-05",
            "last_trade_date": date(2026, 4, 29),
        },
    ]

    markers = _build_hk_basis_contract_roll_markers(
        rows,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
    )

    assert markers == {"2026-04-29": ["HSIJ26"]}


def test_hk_roll_markers_respect_dashboard_window():
    rows = [
        {
            "source_contract_code": "HSIH26",
            "contract_month": "2026-03",
            "last_trade_date": date(2026, 3, 30),
        },
        {
            "source_contract_code": "HSIJ26",
            "contract_month": "2026-04",
            "last_trade_date": date(2026, 4, 29),
        },
    ]

    markers = _build_hk_basis_contract_roll_markers(
        rows,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
    )

    assert markers == {"2026-04-29": ["HSIJ26"]}
