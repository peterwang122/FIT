from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RegimeIndex = Literal["sh000852", "sh000985"]
RegimeState = Literal["valid", "paused", "invalid", "repair", "unavailable"]


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
        return self


class RegimeEvent(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    start: date
    end: date
    days: int = Field(gt=0)
    closed: bool
    end_reason: str | None = None
    drawdown_20d_pct: float | None = None
    upside_20d_pct: float | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end < self.start:
            raise ValueError("Invalid event dates")
        return self


class RegimeSeries(BaseModel):
    index_name: str
    points: list[RegimePoint]
    events: list[RegimeEvent]

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
    history_start: date | None
    history_end: date | None
    notes: list[str]
    latest: RegimePoint | None
    points: list[RegimePoint]
    events: list[RegimeEvent]
