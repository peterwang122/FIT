"""Emit selected-field registries for review and apply_patch, never all trials."""
import json
import re

from csi500_swing import OUT

NAMES = {"sh000012": "国债指数", "sh000142": "上证380稳定", "sz399296": "创成长",
         "sz399416": "大数据300", "sz399997": "中证白酒", "sz980092": "国证自由现金流"}


def registries():
    report = json.loads((OUT / "report.json").read_text())
    assert all(m["paired_selection"]["sell_first_ranked"] for m in report["models"].values())
    catalog = json.loads((OUT / "catalog.json").read_text())
    backend, frontend = {}, []
    for key in report["selected_fields"]:
        meta = catalog[key]
        recipe = None
        plot = meta["transform"] != "availability"
        if not plot:
            label, unit = "国证自由现金流成交量分位数据已预热", "0/1"
        elif key.startswith("csi500-index-daily-data-"):
            match = re.fullmatch(r"csi500-index-daily-data-(.+)-(close-price|volume)(?:-pct)?", key)
            assert match, key
            code, column = match.group(1), match.group(2).replace("-", "_")
            percentile = meta["transform"] == "prior-percentile"
            label = NAMES[code] + ("成交量" if column == "volume" else "收盘") + ("历史分位" if percentile else "点位") + "（跨指数）"
            unit = "%" if percentile else "点"
            recipe = {"kind": "daily", "table": "index_daily_data", "where": "index_code=:code", "params": {"code": code},
                      "column": column, "date_column": "trade_date", "source_key": "index:" + code + ":" + column,
                      "key": key.removeprefix("csi500-").removesuffix("-pct"), "label": label,
                      "family": meta["family"], "source": meta["source"], "unit": "点" if column == "close_price" else "源成交量单位"}
        elif key.startswith("csi500-index-qvix-daily-data-"):
            assert key == "csi500-index-qvix-daily-data-300etf-qvix-open-price-pct"
            label, unit = "300ETF QVIX开盘历史分位（跨指数）", "%"
            recipe = {"kind": "daily", "table": "index_qvix_daily_data", "where": "index_code=:code",
                      "params": {"code": "300ETF_QVIX"}, "column": "open_price", "date_column": "trade_date", "source_key": "qvix:300ETF_QVIX:open_price",
                      "key": key.removeprefix("csi500-").removesuffix("-pct"), "label": label,
                      "family": meta["family"], "source": meta["source"], "unit": "波动率点"}
        else:
            assert key in {"csi500-position-120d-pct", "csi500-return-1d"}, key
            label, unit = meta["label"], "%"
            recipe = {"kind": "price"}
        backend[key] = {"label": label, "unit": unit, "plot": plot,
                        "first_available_date": meta["first_available_date"], "publication": meta["publication"]}
        if recipe:
            backend[key]["recipe"] = recipe
        else:
            backend[key]["base_field"] = meta["base_field"]
        frontend.append({"key": key, "label": label, "unit": unit, "plot": plot})
    return backend, frontend


if __name__ == "__main__":
    backend, frontend = registries()
    print(json.dumps({"backend": backend, "frontend": frontend}, ensure_ascii=False, indent=2))
