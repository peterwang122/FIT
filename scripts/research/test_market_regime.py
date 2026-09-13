import unittest

import numpy as np
import pandas as pd

from market_regime import Rule, episodes, evaluate_signals, regime_points, stock_breadth_parts


def fixture():
    dates = pd.bdate_range("2010-01-01", periods=440).strftime("%Y-%m-%d")
    close = np.r_[np.linspace(100, 200, 200), np.linspace(190, 60, 100), np.linspace(60, 220, 140)]
    prices = pd.DataFrame({"date": dates, "open": close, "close": close,
                           "high": close * 1.01, "low": close * .99})
    breadth = pd.DataFrame(index=dates)
    breadth["observed"] = breadth["traded"] = 1000
    for w in (40, 60, 80, 120):
        breadth[f"valid{w}"] = 900
        breadth[f"breadth{w}"] = np.r_[np.repeat(80, 200), np.repeat(15, 100), np.repeat(80, 140)]
    return prices, breadth


class TestMarketRegime(unittest.TestCase):
    def test_prefix_invariance(self):
        prices, breadth = fixture()
        full = regime_points(prices, breadth, Rule("test"))
        for n in (180, 250, 320, 400):
            part = regime_points(prices.iloc[:n], breadth.iloc[:n], Rule("test"))
            self.assertEqual([(p["state"], p["buy_multiplier"]) for p in part],
                             [(p["state"], p["buy_multiplier"]) for p in full[:n]])

    def test_pause_invalidation_recovery(self):
        prices, breadth = fixture()
        points = regime_points(prices, breadth, Rule("test"))
        states = [r["state"] for r in points]
        self.assertIn("valid", states[:200])
        self.assertIn("paused", states[200:250])
        self.assertIn("invalid", states[250:300])
        self.assertEqual("valid", states[-1])
        first_invalid = states.index("invalid")
        self.assertNotIn("paused", states[first_invalid:300])

    def test_missing_is_not_release(self):
        prices, breadth = fixture()
        breadth.iloc[270, breadth.columns.get_loc("breadth120")] = np.nan
        points = regime_points(prices, breadth, Rule("test"))
        self.assertEqual("unavailable", points[270]["state"])
        self.assertEqual(0, points[270]["buy_multiplier"])
        self.assertEqual("invalid", points[271]["state"])

    def test_insufficient_coverage_is_missing(self):
        prices, breadth = fixture()
        breadth["valid120"] = 400
        self.assertTrue(all(p["state"] == "unavailable" for p in regime_points(prices, breadth, Rule("test"))))

    def test_coverage_boundary_and_explanations(self):
        prices, breadth = fixture()
        breadth["valid120"] = 600
        points = regime_points(prices, breadth, Rule("test"))
        self.assertEqual(60, points[180]["coverage_pct"])
        self.assertEqual([], points[180]["missing_reasons"])
        self.assertEqual("valid", points[180]["state"])
        breadth.loc[prices.iloc[180].date, "valid120"] = 599
        points = regime_points(prices, breadth, Rule("test"))
        self.assertEqual(["insufficient_coverage"], points[180]["missing_reasons"])
        self.assertIsNone(points[180]["pause_met"])
        self.assertEqual(0, points[180]["full_streak"])

    def test_exact_confirmation_days_and_gap_resets(self):
        prices, breadth = fixture()
        points = regime_points(prices, breadth, Rule("test"))
        paused = next(i for i, row in enumerate(points) if row["state"] == "paused")
        self.assertEqual([1, 2, 3], [r["pause_streak"] for r in points[paused - 2:paused + 1]])
        self.assertNotEqual("paused", points[paused - 1]["state"])
        invalid = next(i for i, row in enumerate(points) if row["state"] == "invalid")
        self.assertEqual(10, points[invalid]["invalid_streak"])
        self.assertNotEqual("invalid", points[invalid - 1]["state"])
        breadth.loc[prices.iloc[paused - 1].date, "breadth120"] = np.nan
        changed = regime_points(prices, breadth, Rule("test"))
        self.assertEqual(1, changed[paused]["pause_streak"])
        self.assertNotEqual("paused", changed[paused]["state"])
        self.assertEqual("paused", changed[paused + 2]["state"])

    def test_full_recovery_is_stricter_than_half_allowance(self):
        prices, breadth = fixture()
        breadth["breadth120"] = 45
        points = regime_points(prices, breadth, Rule("test"))
        self.assertEqual("repair", points[-1]["state"])
        self.assertEqual(.5, points[-1]["buy_multiplier"])
        self.assertTrue(points[-1]["recover_met"])
        self.assertFalse(points[-1]["full_met"])

    def test_no_future_stock_or_stale_suspension(self):
        dates = pd.bdate_range("2020-01-01", periods=150).strftime("%Y-%m-%d")
        frame = pd.DataFrame({"trade_date": dates, "prefixed_code": "sh600000",
                              "close_price": np.arange(150) + 100, "volume": 100})
        part = stock_breadth_parts(frame, pd.Index(dates))
        self.assertEqual(0, part.iloc[118].valid120)
        self.assertEqual(1, part.iloc[119].above120)
        frame.loc[125, "volume"] = 0
        frame.loc[130, "close_price"] = np.nan
        changed = stock_breadth_parts(frame, pd.Index(dates))
        self.assertEqual(0, changed.iloc[125].valid120)
        self.assertEqual(0, changed.iloc[131].valid120)
        pd.testing.assert_frame_equal(part.iloc[:100], stock_breadth_parts(frame.iloc[:100], pd.Index(dates[:100])))

    def test_gate_only_restricts_buys_and_signal_date(self):
        prices = [{"date": str(i), "open": 10, "close": 10, "low": 9, "high": 11} for i in range(6)]
        result = evaluate_signals(prices, {"0": "red", "2": "red", "4": "blue"},
                                  {"0": 1, "1": 0, "2": 0, "3": 1, "4": 0}, sell=1)
        self.assertEqual([(r["date"], r["side"]) for r in result["trades"]], [("1", "buy"), ("5", "sell")])
        self.assertEqual(result["points"][3]["position_pct"], 50)

    def test_purple_sells_and_costs(self):
        prices = [{"date": str(i), "open": 10, "close": 10, "low": 9, "high": 11} for i in range(4)]
        result = evaluate_signals(prices, {"0": "red", "2": "purple"}, sell=1, cost=.001)
        self.assertEqual([r["side"] for r in result["trades"]], ["buy", "sell"])
        self.assertAlmostEqual(-.1, result["return_pct"])

    def test_future_window_excludes_trigger_day_and_missing_breaks(self):
        prices = [{"date": str(i), "close": 100, "high": 105, "low": 90 if i else 1} for i in range(8)]
        pts = [{"date": str(i), "state": "paused" if i in (0, 1, 3, 4) else "unavailable"} for i in range(8)]
        events = episodes(pts, prices)
        self.assertEqual(len(events), 2)
        self.assertFalse(events[0]["closed"])
        self.assertAlmostEqual(-10, events[0]["drawdown_5d_pct"])
        self.assertIsNone(events[1]["drawdown_5d_pct"])

    def test_event_resumption_and_unknown_price_window(self):
        prices = [{"date": str(i), "close": 100, "low": 90, "high": 105} for i in range(8)]
        pts = [{"date": str(i), "state": "paused" if i < 2 else "repair"} for i in range(8)]
        event = episodes(pts, prices)[0]
        self.assertEqual("2", event["resumed_date"])
        self.assertEqual(["paused"], event["states"])
        self.assertEqual(2, event["days"])
        prices[4]["low"] = None
        event = episodes(pts, prices)[0]
        self.assertIsNone(event["drawdown_5d_pct"])
        self.assertIsNone(event["upside_5d_pct"])

    def test_breadth_date_comes_from_observations_not_strategy(self):
        from run_market_regime import breadth_end
        _, breadth = fixture()
        self.assertEqual(str(breadth.index[-1]), breadth_end(breadth))
        breadth.iloc[-1, breadth.columns.get_loc("traded")] = 0
        self.assertEqual(str(breadth.index[-2]), breadth_end(breadth))


if __name__ == "__main__":
    unittest.main()
