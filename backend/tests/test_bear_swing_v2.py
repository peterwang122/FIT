"""Research safety checks: causality, complete inputs, and fail-closed admission."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/research"))
import bear_swing_v2_features as bf
import csi1000_bear_swing_v2 as study
import audit_bear_swing_v2 as audit


def raw_data(n=650):
    # Intentional non-weekend gaps ensure shifting uses supplied sessions.
    dates = pd.bdate_range("2016-01-01", periods=n+2).delete([31, 32])[:n]
    rng = np.random.default_rng(731)
    price = 100*np.exp(np.cumsum(rng.normal(0, .01, n)))
    candles = [{"trade_date":str(d.date()),"open":float(v),"high":float(v*1.02),
                "low":float(v*.98),"close":float(v)} for d,v in zip(dates,price)]
    margin = [{"trade_date":row["trade_date"],"exchange":exchange,
               "financing_balance":1e11+i*1e7,"financing_net_buy_amount":float((i%17-8)*1e7)}
              for i,row in enumerate(candles) for exchange in ("SSE","SZSE")]
    return {"candles":candles,"dashboard":[],"bank":[],"global":[],"margin":margin}


def test_margin_uses_previous_actual_session_and_core_has_no_same_day_lookahead():
    raw=raw_data()
    original=bf.features(raw)
    last=raw["candles"][-1]["trade_date"]
    for row in raw["margin"]:
        if row["trade_date"]==last:
            row["financing_net_buy_amount"] *= 10000
    changed=bf.features(raw)
    pd.testing.assert_frame_equal(original,changed)
    assert original.iloc[32].finance_source_date==raw["candles"][31]["trade_date"]
    flows=pd.DataFrame(raw["margin"]).groupby("trade_date").financing_net_buy_amount.sum()
    assert original.iloc[-1].finance30 == pytest.approx(flows.iloc[-31:-1].sum()/1e8)


def test_missing_exchange_breaks_financing_and_core_instead_of_renormalizing():
    raw=raw_data()
    missing=raw["candles"][-4]["trade_date"]
    raw["margin"]=[r for r in raw["margin"] if not(r["trade_date"]==missing and r["exchange"]=="SZSE")]
    frame=bf.features(raw)
    assert pd.isna(frame.iloc[-1].finance30)
    assert pd.isna(frame.iloc[-1].core_known)


def test_future_append_preserves_features():
    raw=raw_data()
    prefix={**raw,"candles":raw["candles"][:600],"margin":raw["margin"][:1200]}
    pd.testing.assert_frame_equal(bf.features(prefix),bf.features(raw).iloc[:600])


def test_future_append_preserves_candidate_signals_and_missing_state():
    raw=raw_data()
    prefix={**raw,"candles":raw["candles"][:600],"margin":raw["margin"][:1200]}
    past,full=bf.features(prefix),bf.features(raw)
    for side in ("low","high"):
        for spec in study.specs("basic",side):
            if spec["extra"] and spec["extra"][0].startswith("bear-"):
                continue
            a,ak=study.signals(past,spec)
            b,bk=study.signals(full,spec)
            np.testing.assert_array_equal(a,b[:600])
            np.testing.assert_array_equal(ak,bk[:600])


def test_recent_setup_requires_complete_window_and_allows_rebound_confirmation():
    f=pd.DataFrame({"wr":[95.,96,97,98,85,84,np.nan,96,97,98,80],
                    "return1":[-1,-1,-1,-1,1,1,1,1,1,1,1]})
    spec={"setup":"wr","operator":"ge","threshold":95,"lookback":5,
          "confirmation":"return1","side":"low","extra":None}
    mask,known=study.signals(f,spec)
    assert mask[4] and mask[5]
    assert not known[3]
    assert not known[6:].any()


def test_old_best_of_bad_rules_cannot_pass_admission():
    old={"evaluated":30,"known_pct":100,"favorable_first_pct":30,
         "adverse_first_pct":60,"pivot_coverage_pct":58.8,"median_mae20":4,
         "median_return20":1}
    reasons=study.rejection(old,"train")
    assert any("favorable_first" in r for r in reasons)
    assert any("adverse_first" in r for r in reasons)


def test_all_outcomes_equals_individual_independent_episodes():
    f=bf.features(raw_data(90))
    for side in ("low","high"):
        all_rows=study.all_outcomes(f,side)
        for i in (0,1,25,70,89):
            mask=pd.Series(False,index=f.index);mask.iloc[i]=True
            expected=study.episodes(f,mask,side)[0]
            actual=all_rows.loc[i]
            for key in ("return_20d","mfe_20d","mae_20d"):
                assert pd.isna(actual[key]) if expected[key] is None else actual[key]==pytest.approx(expected[key])
            assert actual.first_touch==expected["first_touch"]


def test_split_boundary_purges_forward_outcome():
    f=bf.features(raw_data(90))
    out=study.all_outcomes(f,"low")
    mask=np.zeros(90,bool);mask[15]=True
    m=study.stats(f,mask,np.ones(90,bool),out,[],"low",f.index[0],f.index[25])
    assert m["events"]==1 and m["evaluated"]==0


def test_bottom_in_active_region_is_not_reported_as_a_new_entry():
    f=bf.features(raw_data(90))
    mask=np.zeros(90,bool);mask[10:31]=True
    row=audit.neighborhood(f,mask,np.ones(90,bool),f.index[30])
    assert row["signal"] and row["onsets"]==[]
    assert row["active_episode_start"]==f.index[10]
    assert row["active_entry_date"]==f.index[11]
    assert row["entry_to_diagnostic_low_pct"]==pytest.approx((f.low.iloc[30]/f.open.iloc[11]-1)*100)


def test_selection_cannot_read_evaluation_and_grid_avoids_duplicate_financing():
    row={"selection_score":10,"spec":{"factors":2},"id":"x"}
    assert study.selection_key(row)==study.selection_key({**row,"evaluation":{"return":-999999}})
    for model in ("basic","enhanced"):
        for side in ("low","high"):
            for spec in study.specs(model,side):
                assert 1<=spec["factors"]<=3
                if spec["setup"].startswith("finance") or spec["setup"]=="core_known_pct":
                    assert not(spec["extra"] and spec["extra"][0].startswith("finance"))
