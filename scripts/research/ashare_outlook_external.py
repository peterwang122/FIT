"""Archive public research evidence locally; never writes production tables."""

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


SOURCES = {
    "jgb_current": "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv",
    "jgb_history": "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv",
    "sp500": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500",
    "vix": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
    "sge": "https://www.sge.com.cn/sjzx/quotation_daily_new?end_date=2026-09-30&start_date=2026-09-30",
}


def parse_rows(key, content):
    if key == "sge":
        parsed = []
        for row in BeautifulSoup(content, "html.parser").select("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
            if len(cells) < 6 or cells[1] not in ("Au99.99", "Ag(T+D)"):
                continue
            try:
                day = datetime.strptime(cells[0], "%Y-%m-%d").date().isoformat()
                value = float(cells[5].replace(",", ""))
            except ValueError:
                continue
            if math.isfinite(value) and value > 0:
                parsed.append({"date": day, "contract": cells[1], "value": value,
                               "unit": "CNY/g" if cells[1] == "Au99.99" else "CNY/kg"})
        return sorted(parsed, key=lambda r: (r["date"], r["contract"]))
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig", errors="replace"))))
    parsed = []
    if key.startswith("jgb"):
        header = rows[1]
        for row in rows[2:]:
            try:
                day = datetime.strptime(row[0], "%Y/%m/%d").date().isoformat()
                values = {name: float(value) for name, value in zip(header[1:], row[1:]) if value not in ("-", "")}
            except (ValueError, IndexError):
                continue
            parsed.append({"date": day, **values})
    else:
        for row in rows[1:]:
            try:
                day = datetime.strptime(row[0], "%m/%d/%Y" if key == "vix" else "%Y-%m-%d").date().isoformat()
                value = float(row[4] if key == "vix" else row[1])
            except (ValueError, IndexError):
                continue
            parsed.append({"date": day, "value": value})
    return parsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--only", nargs="+", choices=list(SOURCES))
    args = parser.parse_args()
    output = json.loads(args.output.read_text(encoding="utf-8")) if args.only and args.output.exists() else {"as_of_at": args.as_of, "evidence": {}}
    if output["as_of_at"] != args.as_of:
        raise ValueError("Cannot merge evidence with a different cutoff")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for key, url in SOURCES.items():
        if args.only and key not in args.only:
            continue
        response = requests.get(url, timeout=45, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        rows = [r for r in parse_rows(key, response.content) if r["date"] <= args.as_of[:10]]
        if not rows:
            raise ValueError(f"No usable rows for {key}")
        if key == "sge" and {r["contract"] for r in rows} != {"Au99.99", "Ag(T+D)"}:
            raise ValueError("Missing an official gold or silver close")
        (args.output.parent / f"{key}.{'html' if key == 'sge' else 'csv'}").write_bytes(response.content)
        output["evidence"][key] = {"url": url, "sha256": hashlib.sha256(response.content).hexdigest(),
                                   "first_date": rows[0]["date"], "latest": rows[-1], "recent": rows[-30:],
                                   "fetched_at": datetime.now().astimezone().isoformat(),
                                   "availability_note": "官方行情所属日；网页未逐笔披露首次发布时间，按本次抓取已可见使用，不声称历史实时回测。"}
        print(key, rows[-1], flush=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
