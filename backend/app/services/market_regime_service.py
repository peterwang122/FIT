from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from app.schemas.market_regime import MarketRegimeResponse, RegimeIndex, RegimeReport

REPORT_PATH = Path(__file__).resolve().parents[3] / "runtime/reports/market_regime/report.json"


@lru_cache(maxsize=2)
def _read_report(path: str, mtime_ns: int, size: int) -> RegimeReport:
    # Atomic publication plus mtime/size keys makes regenerated snapshots visible without a restart.
    return RegimeReport.model_validate_json(Path(path).read_bytes())


def get_market_regime(
    index_code: RegimeIndex = "sh000852", start_date: date | None = None, end_date: date | None = None,
) -> MarketRegimeResponse:
    if index_code not in ("sh000852", "sh000985"):
        raise ValueError("不支持的观察指数")
    if start_date and end_date and start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    try:
        stat = REPORT_PATH.stat()
        report = _read_report(str(REPORT_PATH), stat.st_mtime_ns, stat.st_size)
    except FileNotFoundError as exc:
        raise RuntimeError("市场环境研究快照尚未生成") from exc
    except (OSError, ValidationError, ValueError) as exc:
        raise RuntimeError("市场环境研究快照读取失败，请重新生成") from exc
    series = report.series.get(index_code)
    if series is None:
        raise RuntimeError("研究快照缺少所选指数")
    points = [point for point in series.points
              if (start_date is None or point.date >= start_date)
              and (end_date is None or point.date <= end_date)]
    events = [event for event in series.events
              if points and event.end >= points[0].date and event.start <= points[-1].date]
    return MarketRegimeResponse(
        schema_version=report.schema_version, generated_at=report.generated_at,
        rule_name=report.rule_name, index_code=index_code, index_name=series.index_name,
        breadth_as_of=report.breadth_as_of, notes=report.notes,
        history_start=series.points[0].date if series.points else None,
        history_end=series.points[-1].date if series.points else None,
        latest=points[-1] if points else None, points=points, events=events,
    )
