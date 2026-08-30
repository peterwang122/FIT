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


def test_overall_score_requires_all_three_scores_and_uses_unified_weights():
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

    assert complete["overall_score"] == 60
    assert complete["composite_score"] == 60
    assert complete["domestic_vulnerability_contribution"] == 28
    assert complete["domestic_deterioration_contribution"] == 14
    assert complete["global_contribution"] == 18
    assert complete["risk_level"] == "red"
    assert complete["display_state"] == "red_global"
    assert complete["risk_level_label"] == "红色+全球"
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

    assert service._risk_level_payload(39.999) == ("stable", "平稳")
    assert service._risk_level_payload(40) == ("yellow", "黄色")
    assert service._risk_level_payload(49.999) == ("yellow", "黄色")
    assert service._risk_level_payload(50) == ("yellow", "黄色")
    assert service._risk_level_payload(50.001) == ("red", "红色")
    assert service._risk_level_payload(None) == (None, None)


def test_dashboard_colors_follow_overall_score_instead_of_stored_legacy_state():
    service = _service()

    point = service._build_risk_dashboard_point_payload(
        {
            "trade_date": date(2026, 7, 2),
            "risk_yellow_vulnerability": 0,
            "risk_yellow_vulnerability_score": 70,
            "risk_red_escalation": 1,
            "risk_red_escalation_score": 50,
            "risk_global_shock": 0,
            "risk_global_shock_score": 45,
            "risk_overall_score": 45.5,
            "risk_base_state": "red",
            "risk_display_state": "red",
            "risk_strategy_components_json": {"base_state": "red", "display_state": "red"},
        }
    )

    assert point["overall_score"] == 45.5
    assert point["base_state"] == "yellow"
    assert point["display_state"] == "yellow"
    assert point["risk_level_label"] == "黄色"


def test_v8_dashboard_exposes_leading_confirmation_and_decision_audit_fields():
    service = _service()
    point = service._build_risk_dashboard_point_payload(
        {
            "trade_date": date(2025, 3, 31),
            "risk_yellow_vulnerability_score": 60,
            "risk_red_escalation_score": 40,
            "risk_global_shock": 0,
            "risk_global_shock_score": 30,
            "risk_global_raw_leading": 1,
            "risk_global_raw_leading_mode": "volatility_repricing",
            "risk_global_leading": 1,
            "risk_global_leading_score": 100,
            "risk_global_leading_mode": "volatility_repricing",
            "risk_global_score": 75,
            "risk_overall_score": 57.5,
            "risk_base_state": "red",
            "risk_display_state": "red_global",
            "risk_as_of_at": "2025-03-31 22:30:00",
            "risk_decision_trade_date": date(2025, 4, 1),
            "risk_strategy_components_json": {
                "version": "v8",
                "as_of_at": "2025-03-31T22:30:00+08:00",
                "decision_trade_date": "2025-04-01",
                "display_state": "red_global",
                "global": {
                    "score": 75,
                    "leading": {
                        "active": True,
                        "score": 100,
                        "mode": "volatility_repricing",
                        "trigger_date": "2025-03-31",
                        "valid_through": "2025-04-08",
                    },
                    "confirmation": {"score": 30},
                },
            },
        }
    )

    assert point["global_leading"] is True
    assert point["global_raw_leading"] is True
    assert point["global_raw_leading_score"] == 100
    assert point["global_raw_leading_mode"] == "volatility_repricing"
    assert point["global_leading_score"] == 100
    assert point["global_confirmation_score"] == 30
    assert point["global_score"] == 75
    assert point["global_leading_trigger_date"] == date(2025, 3, 31)
    assert point["global_leading_valid_through"] == date(2025, 4, 8)
    assert point["as_of_at"] == "2025-03-31T22:30:00+08:00"
    assert point["decision_trade_date"] == date(2025, 4, 1)
    assert point["display_state"] == "red_global"


def test_hs300_flat_point_uses_stored_total_without_grouped_score_fallback():
    service = _service()
    point = service._build_risk_dashboard_point_payload(
        {
            "trade_date": date(2026, 6, 22),
            "risk_yellow_vulnerability_score": None,
            "risk_red_escalation_score": None,
            "risk_global_shock": 1,
            "risk_global_shock_score": 75,
            "risk_global_score": 75,
            "risk_overall_score": 52.5,
            "risk_base_state": "red",
            "risk_display_state": "red_global",
            "risk_strategy_components_json": {
                "version": "hs300-flat-v1",
                "model_version": "hs300-flat-v1",
                "scoring_mode": "flat",
                "overall_score": 52.5,
                "base_state": "red",
                "display_state": "red_global",
                "global": {
                    "score": 75,
                    "active": True,
                    "confirmation": {"score": 75, "active": True},
                    "leading": {"raw_active": True, "score": 100, "active": None},
                },
            },
        }
    )

    assert point["scoring_mode"] == "flat"
    assert point["model_version"] == "hs300-flat-v1"
    assert point["overall_score"] == 52.5
    assert point["domestic_vulnerability_score"] is None
    assert point["domestic_deterioration_score"] is None
    assert point["global_contribution"] == 22.5
    assert point["display_state"] == "red_global"
    assert point["data_complete"] is True


def test_hs300_effective_leading_is_exposed_without_changing_score_or_color():
    service = _service()
    point = service._build_risk_dashboard_point_payload(
        {
            "trade_date": date(2026, 6, 24),
            "risk_global_shock": 0,
            "risk_global_shock_score": 20,
            "risk_global_raw_leading": 1,
            "risk_global_leading": 1,
            "risk_global_leading_score": 100,
            "risk_global_leading_mode": "asia_em_transmission",
            "risk_global_score": 20,
            "risk_overall_score": 35,
            "risk_base_state": "stable",
            "risk_display_state": "stable",
            "risk_strategy_components_json": {
                "version": "hs300-flat-v2",
                "model_version": "hs300-flat-v2",
                "scoring_mode": "flat",
                "overall_score": 35,
                "base_state": "stable",
                "display_state": "stable",
                "global": {
                    "score": 20,
                    "confirmation": {"score": 20, "active": False},
                    "leading": {
                        "raw_active": True,
                        "raw_mode": "asia_em_transmission",
                        "active": True,
                        "score": 100,
                        "mode": "asia_em_transmission",
                        "trigger_date": "2026-06-24",
                        "valid_through": "2026-07-01",
                        "domestic_gate_score": 42.8571,
                        "trigger_threshold": 40,
                        "release_threshold": 30,
                    },
                },
            },
        }
    )

    assert point["model_version"] == "hs300-flat-v2"
    assert point["global_raw_leading"] is True
    assert point["global_leading"] is True
    assert point["global_leading_gate_score"] == 42.8571
    assert point["global_leading_trigger_threshold"] == 40
    assert point["global_leading_release_threshold"] == 30
    assert point["global_leading_valid_through"] == date(2026, 7, 1)
    assert point["global_score"] == 20
    assert point["overall_score"] == 35
    assert point["display_state"] == "stable"


def test_hs300_empty_latest_row_keeps_flat_page_layout():
    service = _service()
    point = service._build_risk_dashboard_point_payload(
        {
            "trade_date": date(2026, 8, 26),
            "risk_strategy_components_json": {},
        },
        default_scoring_mode="flat",
    )

    assert point["scoring_mode"] == "flat"
    assert point["model_version"] == ""
    assert point["display_state"] == "incomplete"


def test_raw_global_leading_does_not_change_a_share_display_state_without_gate():
    service = _service()
    point = service._build_risk_dashboard_point_payload(
        {
            "trade_date": date(2024, 1, 18),
            "risk_yellow_vulnerability_score": 20,
            "risk_red_escalation_score": 20,
            "risk_global_shock": 0,
            "risk_global_shock_score": 20,
            "risk_global_raw_leading": 1,
            "risk_global_raw_leading_mode": "asia_em_transmission",
            "risk_global_leading": 0,
            "risk_global_leading_score": 75,
            "risk_global_score": 20,
            "risk_overall_score": 20,
            "risk_base_state": "stable",
            "risk_display_state": "stable",
            "risk_strategy_components_json": {
                "version": "v8",
                "display_state": "stable",
                "global": {
                    "leading": {
                        "raw_active": True,
                        "raw_mode": "asia_em_transmission",
                        "active": False,
                        "score": 75,
                    },
                    "confirmation": {"score": 20},
                },
            },
        }
    )

    assert point["global_raw_leading"] is True
    assert point["global_raw_leading_score"] == 75
    assert point["global_leading"] is False
    assert point["display_state"] == "stable"


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
    assert [span["display_state"] for span in events[0]["state_spans"]] == [
        "yellow",
        "red",
    ]
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


def test_evidence_flattening_uses_unified_groups_and_excludes_tech_inputs():
    service = _service()
    components = {
        "version": "v8",
        "domestic_vulnerability": {
            "components": [
                {
                    "label": "融资净买入累计120D",
                    "value": 10,
                    "percentile": 70,
                    "absolute_threshold": 0,
                    "percentile_threshold": 80,
                    "matched": False,
                },
                {"label": "A股成交额前5%集中度MA5", "matched": False},
            ],
        },
        "domestic_deterioration": {
            "components": [
                {"label": "融资净买入累计5D", "matched": False},
            ],
        },
        "global": {
            "modules": {
                "equities": {
                    "components": [{"label": "全球股票ACWI 10D", "matched": True}]
                },
                "vix": {"components": [{"label": "VIX收盘", "matched": True}]},
                "usd_rates": {"components": [{"label": "美元指数10D变化", "matched": False}]},
            },
            "leading": {
                "routes": {
                    "volatility_repricing": {
                        "components": [
                            {
                                "label": "VIX9D/VIX3M",
                                "value": 1.05,
                                "percentile": 85,
                                "matched": True,
                            }
                        ],
                        "market_components": [
                            {
                                "label": "标普500短线压力",
                                "matched": True,
                                "components": [
                                    {"label": "标普500 3D跌幅", "value": -3.2, "matched": True}
                                ],
                            }
                        ],
                    },
                    "asia_em_transmission": {
                        "components": [
                            {"label": "亚洲/新兴市场命中数量", "value": 2, "matched": True}
                        ]
                    },
                }
            },
        },
    }

    entries = service._flatten_risk_components(components)
    section_keys = {entry["section_key"] for entry in entries}
    yellow_component = entries[0]["component"]
    direction = service._risk_component_direction(yellow_component)

    assert {
        "domestic_vulnerability",
        "domestic_deterioration",
        "equities",
        "vix",
        "usd_rates",
        "leading_volatility_repricing",
        "leading_asia_em_transmission",
    }.issubset(section_keys)
    assert "tech_markets" not in section_keys
    assert all("SOX" not in entry["label"] for entry in entries)
    assert any(entry["label"] == "VIX9D/VIX3M" for entry in entries)
    assert any(entry["label"] == "标普500 3D跌幅" for entry in entries)
    assert direction == "high"
    assert service._risk_component_is_partial(yellow_component, direction) is True


def test_hs300_evidence_flattening_returns_only_seven_scoring_rows():
    service = _service()
    factors = [
        {
            "key": f"factor_{index}",
            "label": f"因子{index}",
            "value": float(index),
            "score": 50.0,
            "weight": 0.1,
            "contribution": 5.0,
            "matched": False,
        }
        for index in range(6)
    ]
    factors.append(
        {
            "key": "global_confirmation",
            "label": "全球冲击确认分",
            "value": 75.0,
            "score": 75.0,
            "weight": 0.3,
            "contribution": 22.5,
            "matched": True,
            "components": {"vix": {"score": 100}},
        }
    )

    entries = service._flatten_risk_components(
        {"scoring_mode": "flat", "factors": factors, "global": {"modules": {}}}
    )

    assert len(entries) == 7
    assert {entry["strategy_key"] for entry in entries} == {"flat_score"}
    assert {entry["section_key"] for entry in entries} == {"flat_factors"}
    assert [entry["label"] for entry in entries][-1] == "全球冲击确认分"


def test_risk_index_profiles_support_hs300_and_default_to_csi1000():
    service = _service()

    assert service._risk_index_profile(None)[0] == "sh000852"
    code, profile = service._risk_index_profile("000300")
    assert code == "sh000300"
    assert profile["name"] == "沪深300"
    assert profile["scoring_mode"] == "flat"
