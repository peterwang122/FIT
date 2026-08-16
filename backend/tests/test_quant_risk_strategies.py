from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.models.quant_strategy_config import QuantStrategyConfig
from app.services.quant_service import QuantService
from app.services.task_service import TaskRunSkipped, TaskService


def _risk_strategy(key: str = "yellow_vulnerability") -> QuantStrategyConfig:
    return QuantStrategyConfig(
        id=91,
        owner_user_id=1,
        name="中证1000风险测试",
        notes="",
        strategy_engine="risk",
        sequence_mode="single_target",
        strategy_type="index",
        target_market="cn",
        target_code="sh000852",
        target_name="中证1000",
        indicator_params={"risk_strategy": {"key": key}},
        buy_sequence_groups=[],
        sell_sequence_groups=[],
        scan_trade_config={},
        blue_filter_groups=[],
        red_filter_groups=[],
        blue_filters={},
        red_filters={},
        blue_boll_filter={},
        red_boll_filter={},
        signal_buy_color="blue",
        signal_sell_color="red",
        purple_conflict_mode="sell_first",
        buy_position_pct=0,
        sell_position_pct=0,
        execution_price_mode="next_open",
    )


def _risk_row(state=1) -> dict:
    return {
        "trade_date": date(2026, 7, 2),
        "risk_yellow_vulnerability": state,
        "risk_yellow_vulnerability_score": 100,
        "risk_red_escalation": 0,
        "risk_red_escalation_score": 33.33,
        "risk_global_shock": 0,
        "risk_global_shock_score": 25,
        "risk_global_shock_mode": None,
        "risk_strategy_components_json": {
            "yellow": {
                "components": [
                    {
                        "label": "融资净买入累计120D堆积",
                        "value": 120,
                        "matched": True,
                    }
                ]
            }
        },
    }


def _service() -> QuantService:
    return QuantService.__new__(QuantService)


def test_risk_strategy_validation_is_csi1000_only_and_has_no_trade_rules():
    service = _service()
    payload = {
        "strategy_engine": "risk",
        "strategy_type": "index",
        "target_market": "cn",
        "target_code": "sh000852",
        "target_name": "中证1000",
        "indicator_params": {"risk_strategy": {"key": "yellow_vulnerability"}},
        "buy_sequence_groups": [],
        "sell_sequence_groups": [],
        "blue_filter_groups": [],
        "red_filter_groups": [],
        "blue_filters": {},
        "red_filters": {},
    }

    service._validate_strategy_payload(payload)

    with pytest.raises(ValueError, match="仅支持中证1000"):
        service._validate_strategy_payload({**payload, "target_code": "sh000300", "target_name": "沪深300"})
    with pytest.raises(ValueError, match="不能包含买卖规则"):
        service._validate_strategy_payload(
            {
                **payload,
                "blue_filter_groups": [{"conditions": [{"field": "rsi"}]}],
            }
        )


def test_risk_highlight_uses_strategy_color_and_carries_daily_details():
    service = _service()
    strategy = _risk_strategy()
    service._load_precomputed_index_indicator_rows = lambda *_args: [_risk_row()]

    highlights = service._build_strategy_highlight_bands(strategy, [])

    assert highlights[0]["tradeDate"] == "2026-07-02"
    assert highlights[0]["color"] == "amber"
    assert highlights[0]["riskDetails"]["yellow_vulnerability"] is True


def test_risk_strategy_rejects_trade_backtest():
    service = _service()
    strategy = _risk_strategy()
    service._get_owned_strategy = lambda *_args: strategy

    with pytest.raises(ValueError, match="不产生买卖交易"):
        service.calculate_equity_curve(strategy.id, 1)
    with pytest.raises(ValueError, match="不产生期权交易"):
        service.calculate_research_option_trades(strategy.id, 1)


def test_risk_notification_uses_risk_state_instead_of_no_operation():
    strategy = _risk_strategy()

    class Query:
        def filter(self, *_args):
            return self

        def all(self):
            return [strategy]

    class Session:
        def query(self, *_args):
            return Query()

    service = _service()
    service.db = Session()
    service._load_precomputed_index_indicator_rows = lambda *_args: [_risk_row()]

    summaries = service._list_strategy_notification_summaries_fixed(
        [strategy.id],
        strategy.owner_user_id,
        basis_trade_date=date(2026, 7, 2),
    )

    assert summaries[0]["is_risk"] is True
    assert summaries[0]["risk_state"] is True
    assert summaries[0]["signal_text"] == "风险命中"
    assert "融资净买入累计120D堆积" in summaries[0]["note"]


def test_risk_notification_task_skips_when_all_three_states_are_inactive():
    service = TaskService.__new__(TaskService)
    service._now = lambda: datetime(2026, 7, 2, 22, 40)
    service.quant_service = SimpleNamespace(
        list_strategy_notification_summaries=lambda *_args, **_kwargs: [
            {
                "strategy_name": name,
                "target_name": "中证1000",
                "latest_trade_date": "2026-07-02",
                "signal_text": "风险解除",
                "note": "当日条件不满足，风险状态已立即解除",
                "is_risk": True,
                "risk_state": False,
            }
            for name in ("黄色脆弱期", "红色风险升级", "全球冲击")
        ]
    )
    task = SimpleNamespace(
        name="中证1000风险状态每日通知",
        config_json={"strategy_ids": [1, 2, 3]},
    )
    owner = SimpleNamespace(id=1, nickname="Root", username="root")

    with pytest.raises(TaskRunSkipped, match="均未命中"):
        service._build_notification_email(task, owner, date(2026, 7, 2))
