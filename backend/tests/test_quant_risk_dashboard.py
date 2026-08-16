from datetime import date, timedelta

from app.services.quant_service import QuantService


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def _risk_point(
    trade_date: date,
    yellow: bool | None,
    red: bool | None,
    global_shock: bool | None,
) -> dict:
    return {
        "trade_date": trade_date,
        "yellow_vulnerability": yellow,
        "red_escalation": red,
        "global_shock": global_shock,
        "global_mode": "broad_risk_off" if global_shock else None,
        "components": {
            "yellow": {
                "components": [
                    {"label": "融资净买入累计120D", "matched": yellow is True}
                ]
            },
            "red": {
                "components": [
                    {"label": "融资净买入累计5D", "matched": red is True}
                ]
            },
            "global": {
                "broad_risk_off": {
                    "modules": {
                        "vix": {
                            "components": [
                                {"label": "VIX收盘", "matched": global_shock is True}
                            ]
                        }
                    }
                }
            },
        },
    }


def _candle(trade_date: date, close: float = 100.0, low: float = 99.0) -> dict:
    return {
        "trade_date": trade_date,
        "open": close,
        "high": close + 1,
        "low": low,
        "close": close,
    }


def test_composite_score_requires_all_three_scores_and_uses_fixed_weights():
    service = _service()
    complete = service._build_risk_dashboard_point_payload(
        {
            "trade_date": date(2026, 7, 2),
            "risk_yellow_vulnerability": 1,
            "risk_yellow_vulnerability_score": 80,
            "risk_red_escalation": 0,
            "risk_red_escalation_score": 40,
            "risk_global_shock": 1,
            "risk_global_shock_score": 60,
            "risk_global_shock_mode": "broad_risk_off",
            "risk_strategy_components_json": {},
        }
    )

    assert complete["composite_score"] == 56
    assert complete["risk_level"] == "high"
    assert complete["risk_level_label"] == "高风险"
    assert complete["data_complete"] is True

    incomplete = service._build_risk_dashboard_point_payload(
        {
            "trade_date": date(2026, 7, 3),
            "risk_yellow_vulnerability_score": None,
            "risk_red_escalation_score": 40,
            "risk_global_shock_score": 60,
            "risk_strategy_components_json": {},
        }
    )
    assert incomplete["composite_score"] is None
    assert incomplete["risk_level"] is None
    assert incomplete["data_complete"] is False


def test_risk_level_boundaries_are_stable():
    service = _service()

    assert service._risk_level_payload(24.999) == ("stable", "平稳")
    assert service._risk_level_payload(25) == ("vulnerable", "脆弱")
    assert service._risk_level_payload(50) == ("high", "高风险")
    assert service._risk_level_payload(75) == ("severe", "严重")
    assert service._risk_level_payload(None) == (None, None)


def test_risk_events_release_on_all_false_and_break_on_data_gap():
    service = _service()
    start = date(2026, 1, 1)
    dates = [start + timedelta(days=index) for index in range(8)]
    points = [
        _risk_point(dates[0], False, False, False),
        _risk_point(dates[1], True, False, False),
        _risk_point(dates[2], True, True, False),
        _risk_point(dates[3], False, True, False),
        _risk_point(dates[4], False, False, False),
        _risk_point(dates[5], False, False, True),
        _risk_point(dates[6], None, False, None),
        _risk_point(dates[7], False, False, True),
    ]
    candles = [_candle(item) for item in dates]

    events = service._build_risk_events(points, candles)

    assert len(events) == 3
    assert events[0]["start_date"] == dates[1]
    assert events[0]["end_date"] == dates[3]
    assert events[0]["release_date"] == dates[4]
    assert events[0]["end_reason"] == "released"
    assert events[0]["duration_trade_days"] == 3
    assert [span["strategy_key"] for span in events[0]["strategy_spans"]] == [
        "yellow_vulnerability",
        "red_escalation",
    ]
    assert events[1]["end_reason"] == "data_gap"
    assert events[1]["release_date"] is None
    assert events[2]["end_reason"] == "open"
    assert events[2]["is_open"] is True


def test_drawdown_uses_trigger_close_and_future_intraday_low():
    service = _service()
    start = date(2026, 1, 1)
    candles = [_candle(start, close=100, low=99)]
    for index in range(1, 22):
        low = 94 if index == 4 else 98
        candles.append(_candle(start + timedelta(days=index), close=100, low=low))

    drawdowns = service._build_risk_event_drawdowns(start, candles)

    assert drawdowns[0]["value_pct"] == -6
    assert drawdowns[0]["trough_date"] == start + timedelta(days=4)
    assert drawdowns[0]["days_to_trough"] == 4
    assert drawdowns[2]["status"] == "complete"


def test_evidence_flattening_keeps_global_modules_separate_and_marks_partial():
    service = _service()
    components = {
        "yellow": {
            "components": [
                {
                    "label": "融资净买入累计120D",
                    "value": 10,
                    "percentile": 70,
                    "absolute_threshold": 0,
                    "percentile_threshold": 80,
                    "matched": False,
                }
            ],
            "observations": {
                "turnover_concentration": {
                    "label": "A股成交拥挤观察",
                    "components": [
                        {"label": "A股成交额前5%集中度MA5", "matched": False}
                    ],
                }
            },
        },
        "global": {
            "broad_risk_off": {
                "modules": {
                    "global_equities": {
                        "components": [{"label": "标普500 10D", "matched": True}]
                    },
                    "vix": {"components": [{"label": "VIX收盘", "matched": True}]},
                }
            },
            "tech_deleveraging": {
                "market_components": [{"label": "SOX 10D", "matched": False}],
            },
        },
    }

    entries = service._flatten_risk_components(components)
    section_keys = {entry["section_key"] for entry in entries}
    yellow_component = entries[0]["component"]
    direction = service._risk_component_direction(yellow_component)

    assert {"yellow", "turnover_concentration", "global_equities", "vix", "tech_markets"}.issubset(
        section_keys
    )
    assert "tech_concentration" not in section_keys
    assert direction == "high"
    assert service._risk_component_is_partial(yellow_component, direction) is True
