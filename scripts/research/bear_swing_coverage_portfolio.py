"""Declared second-stage portfolio comparison of the unchanged coverage pool."""
import json
from datetime import datetime

import numpy as np
import pandas as pd

from bear_swing_coverage import OUT, POLICY, bottom_rows, markdown, matches, title
from bear_swing_v2_features import save_json
from csi1000_bear_swing import episodes, turning_points
from csi1000_bear_swing_v2 import all_outcomes, stats
from app.db.session import SessionLocal
from app.services.quant_service import QuantService
from market_regime import evaluate_signals

PROTOCOL = {
    "reason": "Coverage-complete signal candidates require complete buy/sell comparison, as requested by user; no thresholds expanded.",
    "disclosure": "Declared after seeing signal-stage winners and their portfolio results. This is retrospective model selection, not a new independent validation.",
    "rank": "max min(full-period Calmar, bear-period Calmar); Calmar=annualized return / max(max drawdown,5); ties lower full MDD then fewer conditions",
    "bear_period": "saved start through 2024-09-18; full period ends at frozen snapshot",
    "execution": "existing blue rules, red buy 50%, blue sell100%, next open, sell first; zero cost for engine parity; stress10bp separately reported",
}


def main():
    manifest = OUT/"portfolio_protocol.json"
    if manifest.exists():
        assert json.loads(manifest.read_text())["protocol"] == PROTOCOL
    else:
        save_json(manifest, {"declared_at": datetime.now().astimezone().isoformat(), "protocol": PROTOCOL})
    report = json.loads((OUT/"report.json").read_text())
    if not (OUT/"signal_stage_report.json").exists():
        save_json(OUT/"signal_stage_report.json", report)
    attempts = json.loads((OUT/"attempts.json").read_text())
    f = pd.read_json(OUT/"features.json", orient="table")
    f.index = f.index.astype(str)
    if (OUT/"etf_prices.json").exists():
        prices = json.loads((OUT/"etf_prices.json").read_text())
    else:
        with SessionLocal() as db:
            rows = QuantService(db)._load_etf_price_rows("512100")
        prices = [{"date": str(r["trade_date"]), **{k: float(r[k]) for k in ("open", "high", "low", "close")}}
                  for r in rows if str(r["trade_date"]) <= report["as_of"]]
        save_json(OUT/"etf_prices.json", prices)
    pivot, outcomes = turning_points(f), all_outcomes(f, "low")
    results = []
    for model, original in report["models"].items():
        blue, _ = matches(f, original["blue_rule"])
        start = original["start_date"]
        eligible = [r for r in attempts if r["model"] == model and not r["rejected"]]
        for candidate in eligible:
            red, _ = matches(f, candidate["rule"])
            signals = {d: "blue" if b else "red" for d,r,b in zip(f.index,red,blue) if (r or b) and d>=start}
            bt = {}
            for period,end in (("full",report["as_of"]),("bear","2024-09-18")):
                window = [p for p in prices if start<=p["date"]<=end]
                result = evaluate_signals(window,signals,buy=.5,sell=1,cost=0)
                years = (pd.Timestamp(window[-1]["date"])-pd.Timestamp(window[0]["date"])).days/365.25
                annualized = ((1+result["return_pct"]/100)**(1/years)-1)*100
                bt[period] = {"return_pct":result["return_pct"],"mdd_pct":result["mdd_pct"],
                              "annualized_pct":annualized,"calmar":annualized/max(5,result["mdd_pct"])}
            results.append({"id":candidate["id"],"model":model,"backtests":bt,
                            "portfolio_score":min(v["calmar"] for v in bt.values()),
                            "complexity":candidate["complexity"]})
        ranked = sorted([r for r in results if r["model"]==model],
                        key=lambda r:(-r["portfolio_score"],r["backtests"]["full"]["mdd_pct"],r["complexity"],r["id"]))
        selected = ranked[0]
        chosen = dict(next(r for r in attempts if r["id"]==selected["id"]))
        chosen.update({k:original[k] for k in ("strategy_id","start_date","old_rule","blue_rule","eligible_count","old_bottoms")})
        chosen["portfolio_selection"] = selected
        red,known = matches(f,chosen["rule"])
        active = f.index.to_numpy() >= start
        chosen["bottoms"] = bottom_rows(f,red,blue,report["labels"],start)
        chosen["periods"] = {}
        for version,rule in (("old",chosen["old_rule"]),("new",chosen["rule"])):
            mask,present = matches(f,rule)
            chosen["periods"][version] = {str(y):stats(f,mask & ~blue & active,present,outcomes,pivot,"low",max(start,f"{y}-01-01"),f"{y}-12-31")
                                         for y in range(max(2022,int(start[:4])),2027)}
        events=episodes(f,pd.Series(red & ~blue & active,index=f.index),"low")
        pd.DataFrame(events).to_csv(OUT/f"{model}_low_events.csv",index=False)
        daily=f[["open","high","low","close","wr","rsi","bear-position60-pct","bear-mo-vix-pct"]].copy()
        daily["red"],daily["blue"],daily["known"]=red & active,blue & active,known
        daily["as_of_at"]=daily.index+"T22:30:00+08:00"
        daily.to_csv(OUT/f"{model}_daily.csv",index_label="date")
        for version,rule in (("old",chosen["old_rule"]),("new",chosen["rule"])):
            mask,_=matches(f,rule)
            sig={d:"blue" if b else "red" for d,r,b in zip(f.index,mask,blue) if (r or b) and d>=start}
            stress=evaluate_signals([p for p in prices if p["date"]>=start],sig,buy=.5,sell=1,cost=.001)
            chosen[version+"_stress_10bp"]={k:stress[k] for k in ("return_pct","mdd_pct")}
        report["models"][model]=chosen
        print(model,chosen["id"],title(chosen["rule"]),selected,flush=True)
    report["portfolio_protocol"] = PROTOCOL
    save_json(OUT/"portfolio_attempts.json",results)
    save_json(OUT/"report.json",report)
    markdown(report)


if __name__=="__main__":
    main()
