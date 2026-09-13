from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RegimeIndex = Literal["sh000852", "sh000985"]
RegimeState = Literal["valid", "paused", "invalid", "repair", "unavailable"]
RegimeMissingReason = Literal["trend_history_short", "breadth_history_missing", "insufficient_traded", "insufficient_coverage"]


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
    pause_met: bool | None = None
    invalid_met: bool | None = None
    recover_met: bool | None = None
    full_met: bool | None = None
    pause_streak: int | None = Field(default=None, ge=0)
    invalid_streak: int | None = Field(default=None, ge=0)
    recover_streak: int | None = Field(default=None, ge=0)
    full_streak: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_point(self):
        if self.open is not None and self.high is not None and self.low is not None:
            if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close):
                raise ValueError("Invalid OHLC")
        expected = {"valid": 1, "repair": .5, "paused": 0, "invalid": 0, "unavailable": 0}
        if self.buy_multiplier != expected[self.state]:
            raise ValueError("State and candidate permission differ")
        required = (self.medium_ma, self.long_ma, self.long_slope, self.breadth_medium, self.breadth_long)
        if self.state != "unavailable" and any(value is None for value in required):
            raise ValueError("Available state needs complete evidence")
        if self.state != "unavailable" and (self.missing_reasons or
                (self.traded is not None and self.traded < 500) or
                (self.traded is not None and self.eligible is not None and self.eligible < self.traded * .6)):
            raise ValueError("Available state needs sufficient coverage")
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
    index_code: RegimeIndex
    index_name: str
    breadth_as_of: date
    strategy_evaluation_end: date | None = None
    breadth_sources: list[RegimeBreadthSource] = Field(default_factory=list)
    history_start: date | None
    history_end: date | None
    notes: list[str]
    latest: RegimePoint | None
    points: list[RegimePoint]
    events: list[RegimeEvent]
    coverage_gaps: list[RegimeGap] = Field(default_factory=list)
