"""Resumable observed evidence with explicit providers; no production writes."""

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

import requests
from sqlalchemy import text

from ashare_outlook_snapshot import encode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.db.session import SessionLocal

FOLDER = ROOT / "runtime/reports/ashare_outlook/2026-10-04/gap_backfill"
CSI = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
SSE = "https://query.sse.com.cn/commonQuery.do"
SECTORS = {"000988": "全指工业", "000990": "全指消费", "000994": "全指通信", "000995": "全指公用", "931775": "全指房地产"}
FULL_SECTORS = dict(zip([str(c) for c in range(932077, 932087)],
    ("能源", "原材料", "工业", "可选消费", "主要消费", "医药卫生", "金融", "信息技术", "通信服务", "公用事业")))
FULL_SECTORS["931775"] = "房地产"


def number(value):
    if value is None or str(value).strip() in ("", "-", "--", "None"):
        return None
    result = float(str(value).replace(",", ""))
    return result if math.isfinite(result) else None


def save(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=encode, ensure_ascii=False, allow_nan=False))


def fetch(key, url, params=None, referer=None):
    path = FOLDER / "raw" / f"{key}.json"
    if path.exists():
        return json.loads(path.read_bytes())
    session = requests.Session()
    session.trust_env = False
    response = session.get(url, params=params, timeout=50, headers={
        "User-Agent": "Mozilla/5.0", "Referer": referer or url,
        "Accept": "application/json, text/plain, */*"})
    response.raise_for_status()
    raw = response.content
    payload = {"url": response.url, "retrieved_at": datetime.now().isoformat(),
               "sha256": hashlib.sha256(raw).hexdigest(), "text": response.text}
    save(path, payload)
    return payload


def parse_csi(payload, code, start, end):
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("CSI data is not a list")
    # Official API sometimes labels the preceding session as the requested boundary.
    if len(rows) > 1 and rows[0].get("tradeDate") == start.replace("-", "") and all(
            rows[0].get(k) == rows[1].get(k) for k in ("open", "close", "high", "low", "tradingValue")):
        rows = rows[1:]
    result = []
    for r in rows:
        day = datetime.strptime(str(r["tradeDate"]), "%Y%m%d").date().isoformat()
        if not start <= day <= end:
            continue
        values = {k + "_price": number(r.get(k)) for k in ("open", "high", "low", "close")}
        if any(v is None or v <= 0 for v in values.values()):
            continue
        if not values["low_price"] <= min(values["open_price"], values["close_price"]) <= max(values["open_price"], values["close_price"]) <= values["high_price"]:
            raise ValueError(f"Invalid official OHLC {code} {day}")
        value = number(r.get("tradingValue"))
        result.append({"index_code": "sh" + code, "index_name": SECTORS[code], "trade_date": day,
                       **values, "turnover": value * 1e8 if value is not None else None,
                       "data_source": "csindex_official_index_perf", "source_url": CSI,
                       "historical_first_publication_verified": False})
    return result


def collect_sectors():
    results, errors = [], []
    for code in SECTORS:
        for year in range(2005, 2027):
            start, end = f"{year}-01-01", min(f"{year}-12-31", "2026-09-30")
            try:
                r = fetch(f"csi-{code}-{year}", CSI, {
                    "indexCode": code, "startDate": start.replace("-", ""), "endDate": end.replace("-", "")}, "https://www.csindex.com.cn/")
                parsed = parse_csi(json.loads(r["text"]), code, start, end)
                results.extend(parsed)
                print(f"CSI {code} {year}: {len(parsed)}", flush=True)
            except Exception as exc:
                errors.append({"code": code, "year": year, "error": str(exc)})
                print(f"CSI {code} {year}: {exc}", flush=True)
                if isinstance(exc, requests.HTTPError) and exc.response.status_code in (403, 429):
                    save(FOLDER / "sectors.json", {"rows": results, "errors": errors})
                    return
                if year == 2005:
                    break
            time.sleep(.5)
    save(FOLDER / "sectors.json", {"rows": results, "errors": errors})


def collect_etf_probe():
    dates = ("2010-12-31", "2013-12-31", "2020-03-23", "2021-02-10", "2024-09-18", "2026-09-30")
    for day in dates:
        try:
            r = fetch("etf-" + day, SSE, {"sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L",
                "STAT_DATE": day, "isPagination": "true", "pageHelp.pageSize": "2000", "pageHelp.pageNo": "1"},
                "https://www.sse.com.cn/market/funddata/volumn/etfvolumn/")
            payload = json.loads(r["text"])
            print(day, str(payload)[:1800], flush=True)
        except Exception as exc:
            print(day, str(exc), flush=True)


def inspect_db():
    queries = {
        "tables": "SHOW TABLES",
        "tools": "SELECT * FROM cn_pbc_liquidity_tool_monthly WHERE published_at<='2026-10-04 04:00:00' ORDER BY period_end,tool_name",
        "margin": "SELECT * FROM margin_trading_daily_data WHERE trade_date BETWEEN '2026-09-28' AND '2026-09-30' ORDER BY trade_date,exchange",
        "concentration": "SELECT * FROM a_share_turnover_concentration_daily WHERE trade_date BETWEEN '2026-09-01' AND '2026-09-30' ORDER BY trade_date",
        "emotion": "SELECT * FROM douyin_index_emotion_daily",
        "excel_emotion": "SELECT * FROM excel_index_emotion_daily ORDER BY emotion_date,index_name",
        "omo": "SELECT * FROM cn_pbc_open_market_operation WHERE published_at<='2026-10-04 04:00:00' ORDER BY operation_date,tool_type",
    }
    data = {}
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        for key, query in queries.items():
            try:
                data[key] = [dict(r) for r in db.execute(text(query)).mappings()]
                print(key, len(data[key]), json.dumps(data[key][:2], default=encode, ensure_ascii=False)[:1500], flush=True)
            except Exception as exc:
                data[key] = {"error": str(exc)}
                print(key, str(exc), flush=True)
    save(FOLDER / "local.json", data)


def collect_etf():
    snapshot = json.loads((FOLDER.parent / "snapshot.json").read_bytes())
    calendar = sorted({r["trade_date"] for r in snapshot["data"]["indexes"] if r["index_code"] == "sh000985"
                       and "2013-01-01" <= r["trade_date"] <= "2026-09-30"})
    # Long history is sampled at official month ends; all 2026 sessions are daily.
    months = {}
    for day in calendar:
        months[day[:7]] = day
    dates = sorted(set(months.values()) | {d for d in calendar if d >= "2026-01-01"}
                   | {"2020-03-23", "2021-02-10", "2021-03-09", "2022-04-26", "2024-02-05", "2024-09-18"})
    result, errors = [], []
    for i, day in enumerate(dates):
        try:
            r = fetch("etf-" + day, SSE, {"sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L",
                "STAT_DATE": day, "isPagination": "true", "pageHelp.pageSize": "2000", "pageHelp.pageNo": "1"},
                "https://www.sse.com.cn/market/funddata/volumn/etfvolumn/")
            payload = json.loads(r["text"])
            rows = payload.get("result", [])
            if int(payload.get("pageHelp", {}).get("total", 0)) != len(rows):
                raise ValueError("Incomplete ETF page")
            for row in rows:
                if row.get("SEC_CODE") not in ("510050", "510300", "510500", "512100"):
                    continue
                if row.get("STAT_DATE") != day or number(row.get("TOT_VOL")) is None:
                    raise ValueError("ETF date/value mismatch")
                result.append({"code": row["SEC_CODE"], "name": row["SEC_NAME"], "date": day,
                               "shares_10k": number(row["TOT_VOL"]), "source_url": r["url"],
                               "first_published_at": None, "raw_sha256": r["sha256"]})
            print(f"ETF {i+1}/{len(dates)} {day}: {len(rows)}", flush=True)
        except Exception as exc:
            errors.append({"date": day, "error": str(exc)})
            print(day, str(exc), flush=True)
            if isinstance(exc, requests.HTTPError) and exc.response.status_code in (403, 429):
                break
        save(FOLDER / "etf.json", {"rows": result, "requested_dates": dates, "errors": errors,
                                  "sampling": "2013-2025 month-end plus research anchors; 2026 daily"})
        time.sleep(.8)


def collect_misc():
    from ashare_outlook_external import parse_rows
    jgb_rows = parse_rows("jgb_history", (FOLDER.parent / "jgb_history.csv").read_bytes())
    jgb_rows += parse_rows("jgb_current", (FOLDER.parent / "jgb_current.csv").read_bytes())
    jgb_rows = list({r["date"]: r for r in jgb_rows if r["date"] <= "2026-10-02"}.values())
    save(FOLDER / "jgb.json", {"rows": sorted(jgb_rows, key=lambda r: r["date"]), "source_url":
        "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv"})
    directory = fetch("hsi-directory", "https://origin-www.hsi.com.hk/data/eng/index-series/directory.json")
    series = next(s for s in json.loads(directory["text"])["indexSeriesList"] if s["seriesCode"] == "ahpremium")
    save(FOLDER / "hsi_directory.json", series)
    print("HSI directory", series.get("indexList"), flush=True)
    for item in series["indexList"]:
        code = item["indexCode"]
        try:
            r = fetch("hsi-chart-" + code, "https://origin-www.hsi.com.hk/api/wsit-hsil-hiip-ea-public-proxy/v1/dataretrieval/e/dailyClose/v1",
                      {"language": "eng", "indexCode": code, "startDate": "1970-01-01", "endDate": "2026-09-30", "interval": "daily"})
            print("HSI chart", code, r["text"][:1400], flush=True)
        except Exception as exc:
            print("HSI chart", code, str(exc), flush=True)


def collect_sina_sectors():
    import akshare as ak
    result, errors = [], []
    for code in ("000994", "000995", "931775"):
        try:
            frame = ak.stock_zh_index_daily(symbol="sh" + code)
            source = frame.to_dict("records")
            save(FOLDER / "raw" / f"sina-{code}.json", {"symbol": "sh" + code, "rows": source,
                 "retrieved_at": datetime.now().isoformat(), "provider": "Sina public index daily"})
            for r in source:
                day = str(r["date"])
                if day > "2026-09-30":
                    continue
                values = {k + "_price": number(r.get(k)) for k in ("open", "high", "low", "close")}
                if any(v is None or v <= 0 for v in values.values()):
                    continue
                result.append({"index_code": "sh" + code, "index_name": SECTORS[code], "trade_date": day,
                               **values, "turnover": None, "data_source": "sina_public_index_daily",
                               "source_url": "https://finance.sina.com.cn/realstock/company/sh" + code + "/nc.shtml",
                               "historical_first_publication_verified": False})
            print("Sina", code, len(frame), flush=True)
        except Exception as exc:
            errors.append({"code": code, "error": str(exc)})
            print("Sina", code, str(exc), flush=True)
        time.sleep(2)
    save(FOLDER / "sina_sectors.json", {"rows": result, "errors": errors})


def collect_full_sectors():
    results, errors = [], []
    for code, name in FULL_SECTORS.items():
        try:
            r = fetch("full-sector-" + code, "https://push2his.eastmoney.com/api/qt/stock/kline/get", {
                "secid": "2." + code, "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57",
                "klt": "101", "fqt": "0", "beg": "20050101", "end": "20260930"}, "https://quote.eastmoney.com/")
            data = json.loads(r["text"]).get("data")
            if not data or data.get("code") != code or not data.get("klines"):
                raise ValueError("Missing or wrong index code")
            for line in data["klines"]:
                day, op, close, hi, low, vol, amount = line.split(",")
                values = [number(v) for v in (op, close, hi, low)]
                if not day <= "2026-09-30" or any(v is None or v <= 0 for v in values):
                    raise ValueError("Invalid date or OHLC")
                if not values[3] <= min(values[:2]) <= max(values[:2]) <= values[2]:
                    raise ValueError("OHLC bounds violated")
                results.append({"index_code": "csi" + code, "index_name": name, "trade_date": day,
                    "open_price": values[0], "close_price": values[1], "high_price": values[2], "low_price": values[3],
                    "turnover": number(amount), "data_source": "eastmoney_public_index_daily",
                    "source_url": "https://quote.eastmoney.com/zs" + code + ".html", "raw_sha256": r["sha256"]})
            print("Full sector", code, data["name"], len(data["klines"]), flush=True)
        except Exception as exc:
            errors.append({"code": code, "error": str(exc)})
            print(code, str(exc), flush=True)
            if isinstance(exc, requests.HTTPError) and exc.response.status_code in (403, 429):
                break
        time.sleep(1)
    save(FOLDER / "full_sectors.json", {"rows": results, "errors": errors,
         "methodology_url": "https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H30199_Index_Methodology_cn.pdf"})


def collect_margin():
    sse = fetch("margin-sse-sep30", "https://query.sse.com.cn/marketdata/tradedata/queryMargin.do", {
        "isPagination": "true", "beginDate": "20260929", "endDate": "20260930", "tabType": "", "stockCode": "",
        "pageHelp.pageSize": "2000", "pageHelp.pageNo": "1"}, "https://www.sse.com.cn/")
    szse = fetch("margin-szse-sep30", "https://www.szse.cn/api/report/ShowReport/data", {
        "SHOWTYPE": "JSON", "CATALOGID": "1837_xxpl", "txtDate": "2026-09-30", "tab1PAGENO": "1"}, "https://www.szse.cn/")
    result = {"SSE": json.loads(sse["text"]), "SZSE": json.loads(szse["text"])}
    save(FOLDER / "margin_official.json", result)
    print("SSE", len(result["SSE"].get("result", [])), "SZSE", len(result["SZSE"][0].get("data", [])), flush=True)


def freeze_cutoff():
    save(FOLDER / "cutoff.json", {"as_of_at": datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None).isoformat(timespec="seconds"),
         "timezone": "Asia/Shanghai", "note": "Research review cutoff; original 04:00 snapshots remain immutable"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("sectors", "sina-sectors", "full-sectors", "etf-probe", "etf", "inspect", "misc", "margin", "freeze"))
    args = parser.parse_args()
    {"sectors": collect_sectors, "etf-probe": collect_etf_probe, "etf": collect_etf,
     "inspect": inspect_db, "misc": collect_misc, "margin": collect_margin,
     "sina-sectors": collect_sina_sectors, "full-sectors": collect_full_sectors, "freeze": freeze_cutoff}[args.action]()
