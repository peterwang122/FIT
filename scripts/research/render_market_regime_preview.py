import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runtime/research/market-regime-20260906"
STUDY = OUT / "legacy-hfq-study"

points = json.loads((STUDY / "preview-data.json").read_text())
events = {}
for index in points:
    with (STUDY / f"{index}_balanced-events.csv").open() as file:
        events[index] = []
        for row in csv.DictReader(file):
            for key in ("drawdown_20d_pct", "upside_20d_pct"):
                row[key] = float(row[key]) if row[key] else None
            events[index].append(row)
template = (Path(__file__).parent / "market_regime_preview.html").read_text()
data = json.dumps({"points": points, "events": events}, ensure_ascii=False).replace("</", "<\\/")
(OUT / "market-regime-preview.html").write_text(template.replace("__DATA__", data), encoding="utf-8")
print(OUT / "market-regime-preview.html")
