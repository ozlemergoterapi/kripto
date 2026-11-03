from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class Candle:
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def valid(self):
        return (self.open_time < self.close_time and
                all(isfinite(v) and v > 0 for v in (self.open, self.high, self.low, self.close)) and
                isfinite(self.volume) and self.volume >= 0 and
                self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high)


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    observed_at: float

    @property
    def mid(self):
        return (self.ask + self.bid) / 2

    @property
    def spread(self):
        return (self.ask - self.bid) / self.mid

    def valid(self):
        return all(isfinite(v) for v in (self.bid, self.ask, self.observed_at)) and 0 < self.bid <= self.ask


@dataclass(frozen=True)
class Signal:
    id: str
    symbol: str
    side: str
    score: int
    timeframe: str
    created_at: float
    expires_at: float
    entry: float
    stop: float
    tp1: float
    tp2: float
    reason: str
    version: str
    atr: float

    def record(self):
        return asdict(self)
