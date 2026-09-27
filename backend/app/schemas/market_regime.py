from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RegimeIndex = Literal["sh000852", "sh000985", "sh000300"]
RegimeState = Literal["valid", "adjustment", "warning", "paused", "invalid", "repair", "unavailable"]
RegimeMissingReason = Literal["trend_history_short", "breadth_history_missing", "insufficient_traded", "insufficient_coverage", "index_history_incomplete"]
RegimeEvidenceMode = Literal["stock_breadth", "index_proxy"]


class RegimePoint(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    date: date
    open: float | None = Field(default=None, gt=0)
    high: float | None = Field(default=None, gt=0)
    low: float | None = Field(default=None, gt=0)
    close: float = Field(gt=0)
    medium_ma: float | None = None
    long_ma: float | None = None
    long_slope: float | None = None
    breadth_medium: float | None = Field(default=None, ge=0, le=100)
    breadth_long: float | None = Field(default=None, ge=0, le=100)
    observed: int | None = Field(default=None, ge=0)
    traded: int | None = Field(default=None, ge=0)
    eligible: int | None = Field(default=None, ge=0)
    state: RegimeState
    buy_multiplier: Literal[0.0, 0.5, 1.0]
    reason: str | None = None
    coverage_pct: float | None = Field(default=None, ge=0, le=100)
    missing_reasons: list[RegimeMissingReason] = Field(default_factory=list)
    evidence_mode: RegimeEvidenceMode = "stock_breadth"
    pause_met: bool | None = None
    invalid_met: bool | None = None
    recover_met: bool | None = None
    full_met: bool | None = None
    pause_streak: int | None = Field(default=None, ge=0)
    invalid_streak: int | None = Field(default=None, ge=0)
    recover_streak: int | None = Field(default=None, ge=0)
    full_streak: int | None = Field(default=None, ge=0)
    annual_ma: float | None = None
    annual_slope_pct: float | None = None
    breadth_annual: float | None = None
    drawdown_250d_pct: float | None = None
    return_20d_pct: float | None = None
    model_version: str | None = None
    state_since: date | None = None
    trigger_rule: str | None = None
    macro_status: str | None = None
    macro_complete: bool = False
    macro_support_count: int = 0
    macro_adverse_count: int = 0
    macro_evidence_date: date | None = None
    macro_applied: bool = False
    rules: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_point(self):
        if self.open is not None and self.high is not None and self.low is not None:
            if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close):
                raise ValueError("Invalid OHLC")
        expected = {"valid": 1, "adjustment": 1, "warning": .5, "repair": .5, "paused": 0, "invalid": 0, "unavailable": 0}
        if self.buy_multiplier != expected[self.state]:
            raise ValueError("State and candidate permission differ")
        required = (self.medium_ma, self.long_ma, self.long_slope, self.breadth_medium, self.breadth_long)
        if self.state != "unavailable" and any(value is None for value in required):
            raise ValueError("Available state needs complete evidence")
        if self.state != "unavailable":
            if self.missing_reasons:
                raise ValueError("Available state needs sufficient coverage")
            if self.evidence_mode == "stock_breadth" and (
                    (self.traded is not None and self.traded < 500) or
                    (self.traded is not None and self.eligible is not None
                     and self.eligible < self.traded * .6)):
                raise ValueError("Available stock breadth needs sufficient coverage")
            if self.evidence_mode == "index_proxy" and (
                    self.traded != 3 or self.eligible != 3 or self.coverage_pct != 100):
                raise ValueError("Available index proxy needs all three proxy indexes")
        return self


class RegimeEvent(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    start: date
    end: date
    days: int = Field(gt=0)
    closed: bool
    end_reason: str | None = None
    resumed_date: date | None = None
    states: list[RegimeState] = Field(default_factory=list)
    drawdown_5d_pct: float | None = None
    upside_5d_pct: float | None = None
    drawdown_10d_pct: float | None = None
    upside_10d_pct: float | None = None
    drawdown_20d_pct: float | None = None
    upside_20d_pct: float | None = None
    drawdown_60d_pct: float | None = None
    upside_60d_pct: float | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end < self.start:
            raise ValueError("Invalid event dates")
        if self.resumed_date is not None and (not self.closed or self.resumed_date <= self.end):
            raise ValueError("Invalid resumption date")
        return self


class RegimeGap(BaseModel):
    start: date
    end: date
    days: int = Field(gt=0)
    min_coverage_pct: float | None = Field(default=None, ge=0, le=100)
    max_coverage_pct: float | None = Field(default=None, ge=0, le=100)
    reasons: list[RegimeMissingReason] = Field(default_factory=list)


class RegimeBreadthSource(BaseModel):
    table: str
    start: date
    end: date
    note: str


class RegimeSeries(BaseModel):
    index_name: str
    points: list[RegimePoint]
    events: list[RegimeEvent]
    coverage_gaps: list[RegimeGap] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_order(self):
        dates = [point.date for point in self.points]
        if dates != sorted(set(dates)):
            raise ValueError("Dates must be unique and ordered")
        return self


class RegimeReport(BaseModel):
    schema_version: Literal["market-regime-research-v1"]
    generated_at: datetime
    research_only: Literal[True]
    model_approved: Literal[False]
    rule_name: Literal["balanced"]
    breadth_as_of: date
    strategy_evaluation_end: date | None = None
    breadth_sources: list[RegimeBreadthSource] = Field(default_factory=list)
    notes: list[str]
    series: dict[RegimeIndex, RegimeSeries]


class MarketRegimeResponse(BaseModel):
    schema_version: str
    generated_at: datetime
    research_only: Literal[True] = True
    model_approved: Literal[False] = False
    rule_name: str
    model_rules: dict[str, str] = Field(default_factory=dict)
    index_code: RegimeIndex
    index_name: str
    breadth_as_of: date
    daily_as_of: date | None = None
    daily_update_mode: RegimeEvidenceMode = "stock_breadth"
    strategy_evaluation_end: date | None = None
    breadth_sources: list[RegimeBreadthSource] = Field(default_factory=list)
    history_start: date | None
    history_end: date | None
    notes: list[str]
    latest: RegimePoint | None
    points: list[RegimePoint]
    events: list[RegimeEvent]
    coverage_gaps: list[RegimeGap] = Field(default_factory=list)
    lightweight_research: dict | None = None
    strategy_comparison: dict | None = None
