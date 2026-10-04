"""T-1 financing evidence for a dated study, never a production dashboard rewrite."""

from collections import defaultdict
from datetime import datetime
from math import isfinite
from zoneinfo import ZoneInfo


def local_time(value):
    timestamp = datetime.fromisoformat(value)
    return timestamp.astimezone(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None) if timestamp.tzinfo else timestamp


def strict_financing(rows, calendar, as_of=None):
    calendar = sorted(set(calendar))
    reference = calendar[-1] if calendar else None
    target = calendar[-2] if len(calendar) > 1 else None
    result = {"reference_trade_date": reference, "expected_source_date": target,
              "source_date": None, "windows": [], "latest_target_missing": True,
              "status": "data_incomplete", "lag_trade_days": None,
              "availability_policy": "previous_cn_trade_date", "available_at": None,
              "availability_basis": "conservative_next_cn_open", "first_publication_times_verified": False}
    if target is None:
        return result
    cutoff = local_time(as_of) if as_of else None
    if cutoff and cutoff.date().isoformat() < reference:
        raise ValueError("Financing reference date is after cutoff")
    next_days = dict(zip(calendar[:-1], calendar[1:]))
    lookup = defaultdict(dict)
    publication = {}
    for row in rows:
        day, exchange = row["trade_date"], row["exchange"]
        if day not in next_days or day > target or exchange not in ("SSE", "SZSE"):
            continue
        # Without a saved timestamp, next-session open is a conservative bound, not an invented first release.
        available = local_time(row["available_at"]) if row.get("available_at") else datetime.fromisoformat(next_days[day] + "T09:30:00")
        if cutoff and available > cutoff:
            continue
        existing = lookup[day].get(exchange)
        if existing and any(existing.get(key) != row.get(key) for key in ("financing_balance", "financing_net_buy_amount")):
            raise ValueError("Conflicting financing exchange date")
        lookup[day][exchange] = row
        publication[day, exchange] = available

    def complete(day):
        return all((value := lookup[day].get(exchange, {}).get(key)) is not None and isfinite(float(value))
                   and (key != "financing_balance" or float(value) >= 0)
                   for exchange in ("SSE", "SZSE") for key in ("financing_balance", "financing_net_buy_amount"))

    days = [day for day in calendar if day <= target and complete(day)]
    if not days:
        return result
    last = days[-1]
    i = calendar.index(last)
    balance = sum(float(lookup[last][e]["financing_balance"]) for e in ("SSE", "SZSE"))
    result.update(source_date=last, balance_cny=balance,
                  net_buy_cny=sum(float(lookup[last][e]["financing_net_buy_amount"]) for e in ("SSE", "SZSE")),
                  latest_target_missing=not complete(target), lag_trade_days=calendar.index(reference) - i,
                  available_at=max(publication[last, e] for e in ("SSE", "SZSE")).isoformat(),
                  status="available_lagged" if last == target else "data_incomplete")
    for n in (5, 20):
        window = calendar[max(0, i - n + 1):i + 1]
        missing = [day for day in window if not complete(day)]
        value = sum(float(lookup[day][e]["financing_net_buy_amount"]) for day in window for e in ("SSE", "SZSE")) if len(window) == n and not missing else None
        result["windows"].append({"sessions": n, "start": window[0], "end": last, "net_buy_cny": value, "missing_dates": missing})
    recent = [day for day in calendar[max(0, i - 119):i + 1] if complete(day)]
    peak_day = max(recent, key=lambda day: sum(float(lookup[day][e]["financing_balance"]) for e in ("SSE", "SZSE")))
    peak = sum(float(lookup[peak_day][e]["financing_balance"]) for e in ("SSE", "SZSE"))
    result.update(peak_day=peak_day, observed_peak_cny=peak,
                  balance_change_from_observed_peak_pct=(balance / peak - 1) * 100 if peak else None,
                  valid_sessions=len(recent), required_sessions=min(120, i + 1),
                  consecutive_windows_verified=all(w["net_buy_cny"] is not None for w in result["windows"]),
                  note="T使用T-1两所同日数据；5/20日窗口截至来源日，窗口断档保持空，不将正常发布滞后当漏采。")
    return result
