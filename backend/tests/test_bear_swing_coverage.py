"""Coverage-first conditions stay causal and explicit about missing data."""
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/research"))
from bear_swing_coverage import bottom_rows, candidates, cond, groups, matches


def test_alternative_price_branch_can_match_without_imputing_iv():
    rule=groups([cond("rsi","lte",20),cond("position","lte",30)],
                [cond("rsi","lte",35),cond("position","lte",30),cond("iv","gte",50)])
    f=pd.DataFrame({"rsi":[17,34,40,34],"position":[4,7,7,7],"iv":[np.nan,np.nan,np.nan,50.]})
    hit,known=matches(f,rule)
    assert hit.tolist()==[True,False,False,True]
    assert known.tolist()==[True,False,True,True]
    assert f.iv.isna().sum()==3


def test_threshold_is_inclusive_and_future_append_cannot_change_past_signal():
    f=pd.DataFrame({"rsi":[45.,45.1,np.nan,20.,90.]})
    rule=groups([cond("rsi","lte",45)])
    a,ak=matches(f.iloc[:3],rule)
    b,bk=matches(f,rule)
    assert a.tolist()==[True,False,False]
    np.testing.assert_array_equal(a,b[:3])
    np.testing.assert_array_equal(ak,bk[:3])


def test_extreme_hit_requires_red_without_sell_conflict():
    f=pd.DataFrame({"open":[100.,99,90],"low":[98.,89,85]},index=["2024-01-01","2024-01-02","2024-01-03"])
    labels=[{"index":2,"date":f.index[2],"low":85.}]
    result=bottom_rows(f,np.ones(3,bool),np.array([False,False,True]),labels,f.index[0])
    assert result[0]["hit"] is False
    result=bottom_rows(f,np.ones(3,bool),np.zeros(3,bool),labels,f.index[0])
    assert result[0]["hit"] is True and result[0]["lead_sessions"]==2
    assert result[0]["first_signal"]==f.index[0]


def test_grid_only_uses_existing_public_fields_and_at_most_three_unique_inputs():
    for model,expected in (("basic",821),("enhanced",625)):
        rules=list(candidates(model))
        assert len(rules)==expected
        for rule in rules:
            fields={c["field"] for g in rule for c in g["conditions"]}
            assert len(fields)<=3
            assert fields<={"wr","rsi","bear-position60-pct","bear-mo-vix-pct"}
            assert len(rule)<=2
